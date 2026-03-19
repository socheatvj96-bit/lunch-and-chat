import requests
from bs4 import BeautifulSoup
import json
import csv
import re
from urllib.parse import urljoin
from datetime import datetime, timedelta
import time
import os

def clean_text(text):
    if not text:
        return None
    return re.sub(r'\s+', ' ', text).strip()

def parse_nam_nyam(date_str):
    base_url = "https://www.nam-nyam.ru"
    url = f"{base_url}/menu-na-nedelu/?curDay={date_str}"
    
    print(f"Загружаю страницу: {url}")
    try:
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        response.raise_for_status()
    except Exception as e:
        print(f"Ошибка при загрузке страницы: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    menu_data = []

    # 1. Парсинг комплексных обедов
    complex_blocks = soup.find_all('div', class_='catalog__complex')
    if complex_blocks:
        complex_category = {
            "category": "Комплексные обеды",
            "items": []
        }
        
        for block in complex_blocks:
            name_tag = block.find('div', class_='catalog__complex__name')
            price_tag = block.find('p', class_='catalog__complex-price')
            
            item = {
                "name": clean_text(name_tag.text) if name_tag else "Без названия",
                "price": clean_text(price_tag.text) if price_tag else None,
                "type": "complex",
                "date": date_str,
                "source_url": url,
                "components": []
            }
            
            # Состав комплекса (слайды)
            slides = block.find_all('li', class_='complex_item')
            for slide in slides:
                comp_name = slide.find('div', class_='card__name')
                comp_weight = slide.find('p', class_='card__weight')
                comp_img = slide.find('img', class_='card__image')
                
                # Парсинг веса и калорий из строки вида "Вес: 300 г. , 94 ккал"
                weight_val = None
                kcal_val = None
                if comp_weight:
                    weight_text = clean_text(comp_weight.text)
                    weight_match = re.search(r'Вес:\s*([\d,.]+)\s*г', weight_text)
                    kcal_match = re.search(r'(\d+)\s*ккал', weight_text)
                    if weight_match:
                        weight_val = weight_match.group(1)
                    if kcal_match:
                        kcal_val = kcal_match.group(1)

                component = {
                    "name": clean_text(comp_name.text) if comp_name else None,
                    "weight": weight_val,
                    "calories": kcal_val,
                    "image": urljoin(base_url, comp_img['src']) if comp_img and comp_img.get('src') else None
                }
                item['components'].append(component)
            
            complex_category['items'].append(item)
        
        menu_data.append(complex_category)

    # 2. Парсинг обычных категорий
    category_titles = soup.find_all('h2', class_='catalog__food-title')
    
    for title in category_titles:
        category_name = clean_text(title.text)
        
        if "Комплексные обеды" in category_name:
            continue

        parent_box = title.find_parent('div', class_='catalog__name-box')
        if not parent_box:
            continue
            
        view_box = parent_box.find_next_sibling('div', class_='catalog__view-box')
        if not view_box:
            continue
            
        items_list = view_box.find('ul', class_='cards-list')
        if not items_list:
            continue
            
        category_data = {
            "category": category_name,
            "items": []
        }
        
        cards = items_list.find_all('li', class_='card')
        for card in cards:
            name = card.find('div', class_='card__name')
            price = card.find('p', class_='card__price') or card.find('meta', itemprop='price')
            weight_tag = card.find('p', class_='card__weight')
            composition = card.find('p', class_='card__composition')
            cpfc = card.find('p', class_='card__cpfc') # БЖУ
            img = card.find('img', class_='card__image')
            
            price_val = None
            if price:
                if price.name == 'meta':
                    price_val = price.get('content')
                else:
                    price_text = clean_text(price.text)
                    price_match = re.search(r'(\d+)', price_text)
                    if price_match:
                        price_val = price_match.group(1)

            # Парсинг веса и калорий
            weight_val = None
            kcal_val = None
            if weight_tag:
                weight_text = clean_text(weight_tag.text)
                weight_match = re.search(r'Вес:\s*([\d,.]+)\s*г', weight_text)
                kcal_match = re.search(r'(\d+)\s*ккал', weight_text)
                if weight_match:
                    weight_val = weight_match.group(1)
                if kcal_match:
                    kcal_val = kcal_match.group(1)

            # Парсинг БЖУ: "БЖУ: 14/7/16"
            protein = None
            fat = None
            carbs = None
            if cpfc:
                cpfc_text = clean_text(cpfc.text).replace('БЖУ:', '').strip()
                parts = cpfc_text.split('/')
                if len(parts) == 3:
                    protein = parts[0].strip()
                    fat = parts[1].strip()
                    carbs = parts[2].strip()

            item = {
                "name": clean_text(name.text) if name else None,
                "price": price_val,
                "weight": weight_val,
                "calories": kcal_val,
                "protein": protein,
                "fat": fat,
                "carbohydrates": carbs,
                "composition": clean_text(composition.text).replace('Состав: ', '') if composition else None,
                "image": urljoin(base_url, img['src']) if img and img.get('src') else None,
                "type": "dish",
                "date": date_str,
                "source_url": url
            }
            category_data['items'].append(item)
            
        if category_data['items']:
            menu_data.append(category_data)

    return menu_data

def save_to_csv(all_data, filename="nam_nyam_menu.csv"):
    # Собираем все поля, которые могут быть
    fieldnames = ['date', 'category', 'type', 'name', 'price', 'weight', 'calories', 
                  'protein', 'fat', 'carbohydrates', 'composition', 'image', 'source_url', 'components']
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for day_data in all_data:
            for category in day_data:
                for item in category['items']:
                    row = {
                        'date': item.get('date'),
                        'category': category['category'],
                        'type': item.get('type'),
                        'name': item.get('name'),
                        'price': item.get('price'),
                        'weight': item.get('weight'),
                        'calories': item.get('calories'),
                        'protein': item.get('protein'),
                        'fat': item.get('fat'),
                        'carbohydrates': item.get('carbohydrates'),
                        'composition': item.get('composition'),
                        'image': item.get('image'),
                        'source_url': item.get('source_url'),
                        'components': json.dumps(item.get('components', []), ensure_ascii=False) if item.get('components') else None
                    }
                    writer.writerow(row)

if __name__ == "__main__":
    start_date = datetime.strptime("05.12.2025", "%d.%m.%Y")
    end_date = datetime.strptime("14.12.2025", "%d.%m.%Y")
    
    all_parsed_data = []
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%d.%m.%Y")
        print(f"\n--- Парсинг данных за {date_str} ---")
        
        day_menu = parse_nam_nyam(date_str)
        if day_menu:
            all_parsed_data.append(day_menu)
            print(f"Найдено {len(day_menu)} категорий")
        else:
            print("Меню не найдено или ошибка")
            
        current_date += timedelta(days=1)
        time.sleep(1) # Пауза чтобы не нагружать сервер
        
    # Сохраняем в JSON (плоская структура по дням)
    with open("nam_nyam_full_menu.json", "w", encoding="utf-8") as f:
        json.dump(all_parsed_data, f, ensure_ascii=False, indent=2)
        
    # Сохраняем в CSV
    # Нужно развернуть структуру: List[List[Dict]] -> List[Dict] для CSV функции
    flat_data_for_csv = []
    for day_data in all_parsed_data:
        flat_data_for_csv.append(day_data)
        
    save_to_csv(flat_data_for_csv, "nam_nyam_full_menu.csv")
    
    print(f"\nГотово! Данные сохранены в nam_nyam_full_menu.json и nam_nyam_full_menu.csv")
