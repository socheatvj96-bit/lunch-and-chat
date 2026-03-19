# Быстрый старт

## 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

## 2. Настройка окружения
Создайте файл `.env`:
```bash
SECRET_KEY=django-insecure-change-this-in-production
TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN_REMOVED
```

## 3. Миграции и суперпользователь
```bash
python manage.py migrate
python manage.py createsuperuser
```

## 4. Запуск

### Вариант 1: По отдельности (для разработки)
```bash
# Терминал 1 - Django
python manage.py runserver

# Терминал 2 - Telegram бот
python manage.py run_bot

# Терминал 3 - Celery worker
celery -A lunch_order worker -l info

# Терминал 4 - Celery beat
celery -A lunch_order beat -l info
```

### Вариант 2: Скрипт (все сразу)
```bash
./run.sh
```

## 5. Первые шаги

1. Откройте админ панель: http://localhost:8000/admin/
2. Создайте сотрудника с Telegram ID
3. Создайте ресторан и добавьте блюда
4. Настройте период доступности ресторана
5. Найдите бота в Telegram: @proektnoe_mishlenie_bot
6. Отправьте `/start` боту

## Примечания

- Для работы Celery нужен Redis (по умолчанию localhost:6379)
- Email рассылка требует настройки SMTP в `.env`
- Начисление баланса происходит в 9:00, рассылка меню в 10:00

