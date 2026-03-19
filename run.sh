#!/bin/bash

# Скрипт для запуска всех компонентов системы

echo "Запуск системы заказа обедов..."

# Активация виртуального окружения (если используется)
# source venv/bin/activate

# Запуск миграций
echo "Применение миграций..."
python manage.py migrate

# Запуск Django сервера в фоне
echo "Запуск Django сервера..."
python manage.py runserver &
DJANGO_PID=$!

# Запуск Telegram бота в фоне
echo "Запуск Telegram бота..."
python manage.py run_bot &
BOT_PID=$!

# Запуск Celery worker в фоне
echo "Запуск Celery worker..."
celery -A lunch_order worker -l info &
WORKER_PID=$!

# Запуск Celery beat в фоне
echo "Запуск Celery beat..."
celery -A lunch_order beat -l info &
BEAT_PID=$!

echo "Все компоненты запущены!"
echo "Django: PID $DJANGO_PID"
echo "Telegram Bot: PID $BOT_PID"
echo "Celery Worker: PID $WORKER_PID"
echo "Celery Beat: PID $BEAT_PID"
echo ""
echo "Для остановки используйте: kill $DJANGO_PID $BOT_PID $WORKER_PID $BEAT_PID"

# Ожидание завершения
wait

