#!/bin/bash
cd /root/lunch_order
echo "Распаковка архива..."
tar -xzf /root/lunch_order_deploy.tar.gz
echo "Остановка контейнеров..."
docker-compose down
echo "Запуск контейнеров..."
docker-compose up -d --build
echo "Ожидание запуска..."
sleep 10
echo "Применение миграций..."
docker-compose exec -T web python manage.py makemigrations
docker-compose exec -T web python manage.py migrate
echo "Сбор статики..."
docker-compose exec -T web python manage.py collectstatic --noinput
echo "Создание медиа директории..."
docker-compose exec -T web mkdir -p /app/media
docker-compose exec -T web chmod 755 /app/media
echo "Статус сервисов:"
docker-compose ps
echo "✅ Деплой завершен!"
