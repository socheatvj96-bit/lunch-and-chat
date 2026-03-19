# Деплой изменений от 04.12.2025

## Что сделано

### 1. Парсинг меню с nam-nyam.ru
- ✅ Создан парсер `parse_nam_nyam.py`
- ✅ Собраны данные за 05.12.2025 - 14.12.2025
- ✅ Сохранено в JSON и CSV форматах
- ✅ Загружено ~1700+ изображений товаров

### 2. Расширение модели MenuItem
Добавлены необязательные поля:
- `weight` (CharField) - вес/объем
- `calories` (IntegerField) - калорийность
- `protein` (DecimalField) - белки
- `fat` (DecimalField) - жиры
- `carbohydrates` (DecimalField) - углеводы
- `composition` (TextField) - состав
- `source_url` (URLField) - ссылка на источник

### 3. Создана миграция
- `orders/migrations/0007_menuitem_calories_menuitem_carbohydrates_and_more.py`

### 4. Импорт данных
- Создан скрипт `import_menu.py`
- Импортировано ~1500+ товаров
- Загружены изображения в `media/menu_items/`

### 5. Обновлен API
Обновлены endpoints для возврата новых полей:
- `/app/menu/` (get_menu)
- `/app/menu/week/` (get_week_menu)

### 6. Улучшен UI
- Добавлено отображение веса и калорий
- Добавлено отображение БЖУ (белки/жиры/углеводы)
- Добавлено отображение состава (первые 80 символов)
- Улучшена визуальная иерархия информации

## Файлы для деплоя

1. `orders/models.py`
2. `orders/user_views.py`
3. `orders/templates/orders/user_app.html`
4. `orders/migrations/0007_*.py`

## Команды для деплоя на сервере

```bash
# 1. Подключиться к серверу
ssh root@91.84.124.245

# 2. Перейти в папку проекта
cd /root/lunch_order

# 3. Пересобрать контейнеры
docker-compose down
docker-compose build
docker-compose up -d

# 4. Применить миграции
docker-compose exec web python manage.py migrate

# 5. Проверить статус
docker-compose ps
docker-compose logs -f web
```

## Проверка

После деплоя проверить:
1. https://victor.kiselev.lol/app - главная страница работает
2. Товары отображают КБЖУ и вес
3. Меню на разные дни загружается

## Примечания

- Создан ресторан "Нам-Ням" в БД
- Группы товаров созданы с привязкой к датам (например "Комплексные обеды (05.12.2025)")
- Это позволяет иметь разное меню на каждый день
- Изображения хранятся в `media/menu_items/`
