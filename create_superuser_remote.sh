#!/bin/bash

# Простой скрипт для создания суперпользователя на удаленном сервере
# Запустите этот скрипт на сервере или скопируйте команды

SERVER="${1:-user@victor.kiselev.lol}"
REMOTE_PATH="${2:-/opt/lunch_order}"

echo "Подключение к серверу и создание суперпользователя..."
echo ""
echo "Выполните следующие команды на сервере:"
echo ""
echo "cd $REMOTE_PATH"
echo "DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose exec web python manage.py createsuperuser"
echo ""
echo "Или выполните эту команду для автоматического создания:"
echo ""
echo "ssh -t $SERVER 'cd $REMOTE_PATH && DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose exec web python manage.py createsuperuser'"
echo ""

# Пытаемся выполнить автоматически
read -p "Выполнить автоматически? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ssh -t "$SERVER" "cd $REMOTE_PATH && DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose exec web python manage.py createsuperuser"
fi

