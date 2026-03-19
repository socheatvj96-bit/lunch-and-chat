import ast
import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional, Tuple

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from orders.models import MenuItem, MenuItemGroup


class Command(BaseCommand):
    help = (
        "Ищет изображения товаров на vkusvill.ru по названию блюда и "
        "сохраняет ссылку в MenuItem.image_url."
    )

    BASE_URL = "https://www.vkusvill.ru"
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--restaurant",
            type=str,
            default="ВкусВилл",
            help='Название ресторана (по умолчанию: "ВкусВилл").',
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            default=True,
            help="Обрабатывать только блюда без image_url (по умолчанию: включено).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Перезаписывать image_url даже если он уже заполнен.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Ограничить количество блюд (0 = без лимита).",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.4,
            help="Пауза между запросами в секундах (по умолчанию: 0.4).",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=20.0,
            help="Timeout HTTP-запроса в секундах (по умолчанию: 20).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, что будет обновлено, без сохранения.",
        )
        parser.add_argument(
            "--menu-date",
            type=str,
            default="",
            help="Ограничить блюда меню на конкретную дату (формат YYYY-MM-DD).",
        )

    def handle(self, *args, **options):
        restaurant_name = options["restaurant"].strip()
        force = bool(options["force"])
        only_missing = bool(options["only_missing"]) and not force
        limit = int(options["limit"] or 0)
        delay = float(options["delay"])
        timeout = float(options["timeout"])
        dry_run = bool(options["dry_run"])
        menu_date_raw = (options.get("menu_date") or "").strip()

        qs = MenuItem.objects.filter(restaurant__name=restaurant_name, is_available=True)
        if menu_date_raw:
            try:
                target_date = timezone.datetime.strptime(menu_date_raw, "%Y-%m-%d").date()
            except ValueError:
                self.stdout.write(self.style.ERROR("Неверный формат --menu-date, ожидается YYYY-MM-DD"))
                return
            groups = MenuItemGroup.objects.filter(
                is_active=True,
                period_start__lte=target_date,
                period_end__gte=target_date,
            ).values_list("id", flat=True)
            qs = qs.filter(group_id__in=list(groups))

        if only_missing:
            qs = qs.filter(image_url__isnull=True) | qs.filter(image_url="")

        items = list(qs.order_by("id"))
        if limit > 0:
            items = items[:limit]

        total = len(items)
        self.stdout.write(
            f"Сканирование блюд: {total} | ресторан: {restaurant_name} | "
            f"dry_run={dry_run} | force={force}"
        )
        if total == 0:
            self.stdout.write(self.style.WARNING("Нет блюд для обработки."))
            return

        updated = 0
        not_found = 0
        errors = 0

        for idx, item in enumerate(items, start=1):
            try:
                image_url, source_page = self.find_image_for_name(item.name, timeout=timeout)
                if image_url:
                    updated += 1
                    if not dry_run:
                        with transaction.atomic():
                            item.image_url = image_url
                            item.save(update_fields=["image_url"])
                    self.stdout.write(
                        f"[{idx}/{total}] OK: {item.name} -> {image_url} "
                        f"(source: {source_page})"
                    )
                else:
                    not_found += 1
                    self.stdout.write(f"[{idx}/{total}] MISS: {item.name}")
            except Exception as exc:
                errors += 1
                self.stdout.write(self.style.ERROR(f"[{idx}/{total}] ERR: {item.name} -> {exc}"))

            if delay > 0:
                time.sleep(delay)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Готово. Обновлено: {updated}"))
        self.stdout.write(f"Не найдено: {not_found}")
        self.stdout.write(f"Ошибок: {errors}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: изменения не сохранены."))

    def find_image_for_name(self, product_name: str, timeout: float) -> Tuple[Optional[str], Optional[str]]:
        query_candidates = self.build_query_candidates(product_name)
        if not query_candidates:
            return None, None

        best = None
        for query in query_candidates:
            search_url = f"{self.BASE_URL}/search/?q={urllib.parse.quote(query)}"
            search_html = self.fetch_text(search_url, timeout=timeout)
            if not search_html:
                continue

            links = self.extract_product_links(search_html)
            if not links:
                continue

            for link in links[:8]:
                page_html = self.fetch_text(link, timeout=timeout)
                if not page_html:
                    continue
                img = self.extract_og_image(page_html) or self.extract_json_ld_image(page_html)
                if not img:
                    continue

                title = self.extract_og_title(page_html) or ""
                score = self.score_candidate(product_name, title, link, query)
                if best is None or score > best[0]:
                    best = (score, img, link)

            # Если уже нашли уверенное совпадение, дальше не ищем.
            if best is not None and best[0] >= 12:
                break

        if best:
            return best[1], best[2]
        return None, None

    def fetch_text(self, url: str, timeout: float) -> Optional[str]:
        req = urllib.request.Request(url, headers=self.DEFAULT_HEADERS, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read()
            # Ожидаем html
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                return None
            return raw.decode("utf-8", errors="ignore")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return None

    def extract_product_links(self, html_text: str) -> List[str]:
        # Ссылки вида /goods/... (основной паттерн каталога ВВ)
        rel_links = re.findall(r'href=["\'](/goods/[^"\']+)["\']', html_text, flags=re.IGNORECASE)
        seen = set()
        out: List[str] = []
        for rel in rel_links:
            rel = rel.split("#", 1)[0]
            rel = rel.split("?", 1)[0]
            full = urllib.parse.urljoin(self.BASE_URL, rel)
            if full in seen:
                continue
            seen.add(full)
            out.append(full)

        # Дополнительный fallback: иногда ссылки лежат в JSON как https://www.vkusvill.ru/goods/...
        abs_links = re.findall(r'https://www\.vkusvill\.ru/goods/[^"\'\s<>]+', html_text, flags=re.IGNORECASE)
        for full in abs_links:
            full = full.split("#", 1)[0]
            full = full.split("?", 1)[0]
            if full in seen:
                continue
            seen.add(full)
            out.append(full)
        return out

    def extract_og_image(self, html_text: str) -> Optional[str]:
        # meta property="og:image" content="..."
        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html_text,
            flags=re.IGNORECASE,
        )
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                html_text,
                flags=re.IGNORECASE,
            )
        if not m:
            return None
        value = html.unescape(m.group(1).strip())
        if value.startswith("//"):
            value = "https:" + value
        if value.startswith("/"):
            value = urllib.parse.urljoin(self.BASE_URL, value)
        if not value.startswith("http"):
            return None
        return value

    def extract_og_title(self, html_text: str) -> Optional[str]:
        m = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            html_text,
            flags=re.IGNORECASE,
        )
        if m:
            return html.unescape(m.group(1).strip())
        return None

    def extract_json_ld_image(self, html_text: str) -> Optional[str]:
        # Ищем JSON-LD Product и поле image.
        scripts = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for raw in scripts:
            txt = html.unescape(raw.strip())
            if not txt:
                continue
            # Попытка как JSON-подобная структура.
            candidates = []
            try:
                # Иногда JSON-LD содержит несколько объектов.
                obj = ast.literal_eval(txt) if txt.startswith("{'") else None
                if obj is not None:
                    candidates.append(obj)
            except Exception:
                pass
            if not candidates:
                try:
                    import json
                    parsed = json.loads(txt)
                    if isinstance(parsed, list):
                        candidates.extend(parsed)
                    else:
                        candidates.append(parsed)
                except Exception:
                    continue

            for item in candidates:
                if not isinstance(item, dict):
                    continue
                img = item.get("image")
                if isinstance(img, list) and img:
                    img = img[0]
                if isinstance(img, str) and img.startswith("http"):
                    return img
        return None

    def score_candidate(self, name: str, title: str, link: str, used_query: str = "") -> int:
        name_norm = self.normalize_text(name)
        title_norm = self.normalize_text(title)
        score = 0
        if name_norm and title_norm and name_norm in title_norm:
            score += 10

        name_tokens = set(name_norm.split())
        title_tokens = set(title_norm.split())
        if name_tokens and title_tokens:
            score += len(name_tokens & title_tokens)

        link_norm = self.normalize_text(link.replace("-", " ").replace("/", " "))
        if name_norm and link_norm and any(t in link_norm for t in name_tokens if len(t) > 3):
            score += 2
        query_norm = self.normalize_text(used_query)
        if query_norm and title_norm and query_norm in title_norm:
            score += 3
        return score

    def build_query_candidates(self, product_name: str) -> List[str]:
        raw = (product_name or "").strip()
        if not raw:
            return []
        candidates = [raw]

        # Убираем размеры/вес (г, кг, мл, л, шт) и служебные хвосты.
        cleaned = re.sub(r"\b\d+(?:[.,]\d+)?\s*(г|кг|мл|л|шт)\b", " ", raw, flags=re.IGNORECASE)
        cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_,.")
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

        # Короткий вариант: первые значимые слова.
        norm = self.normalize_text(cleaned or raw)
        tokens = [t for t in norm.split() if len(t) > 2]
        if tokens:
            short = " ".join(tokens[:5]).strip()
            if short and short not in candidates:
                candidates.append(short)
            # Еще более узкий вариант, часто хорошо матчится у ВВ.
            short2 = " ".join(tokens[:3]).strip()
            if short2 and short2 not in candidates:
                candidates.append(short2)

        return candidates

    def normalize_text(self, value: str) -> str:
        value = (value or "").lower()
        value = value.replace("ё", "е")
        value = re.sub(r"[^a-zа-я0-9\s]+", " ", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+", " ", value).strip()
        return value
