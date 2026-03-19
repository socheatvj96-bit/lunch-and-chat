import os
import django
import json
import requests
import re
from django.core.files.base import ContentFile
from datetime import datetime
from urllib.parse import urlparse

# Настройка Django окружения
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lunch_order.settings')
django.setup()

from orders.models import Restaurant, MenuItemGroup, MenuItem, MenuItemImage

def clean_price(price_str):
    if not price_str:
        return 0
    # Оставляем только цифры и точку
    clean = re.sub(r'[^\d.]', '', str(price_str))
    try:
        return float(clean)
    except ValueError:
        return 0

def import_menu(json_file_path):
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Создаем или получаем ресторан
    restaurant, created = Restaurant.objects.get_or_create(
        name="Нам-Ням",
        defaults={'is_active': True}
    )
    if created:
        print(f"Создан ресторан: {restaurant.name}")

    for day_data in data:
        for category_data in day_data:
            category_name = category_data['category']
            
            # Получаем дату из первого элемента (если есть)
            items = category_data.get('items', [])
            if not items:
                continue
                
            date_str = items[0].get('date')
            if not date_str:
                continue
                
            target_date = datetime.strptime(date_str, "%d.%m.%Y").date()
            
            group_name_with_date = f"{category_name} ({date_str})"
            group, created = MenuItemGroup.objects.get_or_create(
                name=group_name_with_date,
                defaults={
                    'is_active': True,
                    'period_start': target_date,
                    'period_end': target_date,
                    'description': f"Меню на {date_str}"
                }
            )
            
            for item_data in items:
                # Создаем/обновляем блюдо
                menu_item, created = MenuItem.objects.update_or_create(
                    restaurant=restaurant,
                    group=group,
                    name=item_data['name'],
                    defaults={
                        'price': clean_price(item_data.get('price')),
                        'weight': item_data.get('weight') or '',
                        'calories': int(item_data['calories']) if item_data.get('calories') else None,
                        'protein': float(item_data['protein'].replace(',', '.')) if item_data.get('protein') else None,
                        'fat': float(item_data['fat'].replace(',', '.')) if item_data.get('fat') else None,
                        'carbohydrates': float(item_data['carbohydrates'].replace(',', '.')) if item_data.get('carbohydrates') else None,
                        'composition': item_data.get('composition') or '',
                        'source_url': item_data.get('source_url'),
                        'is_available': True
                    }
                )
                
                # Загрузка изображения
                image_url = item_data.get('image')
                if image_url and not menu_item.images.exists():
                    try:
                        print(f"Загружаю изображение для {menu_item.name}: {image_url}")
                        response = requests.get(image_url, timeout=10)
                        if response.status_code == 200:
                            file_name = os.path.basename(urlparse(image_url).path)
                            if not file_name:
                                file_name = f"image_{menu_item.id}.jpg"
                                
                            img_obj = MenuItemImage(menu_item=menu_item, is_primary=True)
                            img_obj.image.save(file_name, ContentFile(response.content), save=True)
                    except Exception as e:
                        print(f"Ошибка загрузки изображения: {e}")

if __name__ == "__main__":
    import_menu('nam_nyam_full_menu.json')
