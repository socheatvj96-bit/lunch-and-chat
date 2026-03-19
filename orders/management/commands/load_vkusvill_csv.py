import csv
import re
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from orders.models import Restaurant, MenuItem, MenuItemGroup


class Command(BaseCommand):
    help = 'Загрузка каталога ВкуссВилл из CSV файла'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Путь к CSV файлу')
        parser.add_argument(
            '--restaurant-name',
            type=str,
            default='ВкуссВилл',
            help='Название ресторана (по умолчанию: ВкуссВилл)'
        )
        parser.add_argument(
            '--group-name',
            type=str,
            default='ВкуссВилл',
            help='Название группы товаров (по умолчанию: ВкуссВилл)'
        )

    def parse_price(self, price_str):
        """Парсинг цены из строки вида '280 руб /шт'"""
        if not price_str:
            return None
        
        # Удаляем все пробелы и переносы строк
        price_str = re.sub(r'\s+', '', price_str)
        
        # Ищем число в начале строки
        match = re.search(r'(\d+(?:[.,]\d+)?)', price_str)
        if match:
            try:
                price_value = match.group(1).replace(',', '.')
                return Decimal(price_value)
            except (ValueError, InvalidOperation):
                pass
        
        return None

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        restaurant_name = options['restaurant_name']
        group_name = options['group_name']

        self.stdout.write(f'Загрузка каталога из файла: {csv_file}')
        self.stdout.write(f'Ресторан: {restaurant_name}')
        self.stdout.write(f'Группа: {group_name}')

        # Создаем или получаем ресторан
        restaurant, created = Restaurant.objects.get_or_create(
            name=restaurant_name,
            defaults={
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'  Создан ресторан: {restaurant_name}'))
        else:
            self.stdout.write(f'  Используется существующий ресторан: {restaurant_name}')

        # Создаем или получаем группу
        group, created = MenuItemGroup.objects.get_or_create(
            name=group_name,
            defaults={
                'is_active': True,
                'order': 0,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'  Создана группа: {group_name}'))
        else:
            self.stdout.write(f'  Используется существующая группа: {group_name}')

        # Читаем CSV файл
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                created_count = 0
                updated_count = 0
                skipped_count = 0
                error_count = 0

                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Получаем название товара
                        name = row.get('ProductCard__link', '').strip()
                        if not name:
                            skipped_count += 1
                            continue

                        # Парсим цену
                        price_str = row.get('Price', '')
                        price = self.parse_price(price_str)
                        
                        # Получаем описание (вес)
                        weight = row.get('ProductCard__weight', '').strip()
                        description = f'Вес: {weight}' if weight else ''
                        
                        # Получаем ссылку на изображение
                        image_url = row.get('ProductCard__imageImg src', '').strip()

                        # Создаем или обновляем товар (избегаем дублей по restaurant + name)
                        menu_item, created = MenuItem.objects.get_or_create(
                            restaurant=restaurant,
                            name=name,
                            defaults={
                                'group': group,
                                'description': description,
                                'price': price,
                                'is_available': True,
                            }
                        )

                        if not created:
                            # Обновляем существующий товар
                            menu_item.group = group
                            menu_item.description = description
                            if price:
                                menu_item.price = price
                            menu_item.is_available = True
                            menu_item.save()
                            updated_count += 1
                        else:
                            created_count += 1

                        if row_num % 100 == 0:
                            self.stdout.write(f'  Обработано строк: {row_num}...')

                    except Exception as e:
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(f'  Ошибка в строке {row_num}: {str(e)}')
                        )
                        continue

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'Файл не найден: {csv_file}'))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при чтении файла: {str(e)}'))
            return

        self.stdout.write(self.style.SUCCESS('\nЗагрузка завершена!'))
        self.stdout.write(f'  Создано товаров: {created_count}')
        self.stdout.write(f'  Обновлено товаров: {updated_count}')
        self.stdout.write(f'  Пропущено строк: {skipped_count}')
        if error_count > 0:
            self.stdout.write(self.style.WARNING(f'  Ошибок: {error_count}'))
        self.stdout.write(f'  Всего товаров в каталоге: {MenuItem.objects.filter(restaurant=restaurant).count()}')


