#!/bin/bash

# Скрипт для создания суперпользователя на сервере
# Использование: ./create_superuser.sh [user@host] [remote_path]

set -e

# Параметры по умолчанию
SERVER="${1:-user@victor.kiselev.lol}"
REMOTE_PATH="${2:-/opt/lunch_order}"

echo "👤 Создание суперпользователя на сервере..."
echo "Сервер: $SERVER"
echo "Путь: $REMOTE_PATH"
echo ""

# Проверяем, переданы ли данные для неинтерактивного создания
if [ -n "$SUPERUSER_USERNAME" ] && [ -n "$SUPERUSER_EMAIL" ] && [ -n "$SUPERUSER_PASSWORD" ]; then
    echo "Создание суперпользователя в неинтерактивном режиме..."
    ssh "$SERVER" << EOF
        set -e
        cd $REMOTE_PATH
        
        DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose exec -T web python manage.py shell << PYTHON
from django.contrib.auth import get_user_model
User = get_user_model()

username = "$SUPERUSER_USERNAME"
email = "$SUPERUSER_EMAIL"
password = "$SUPERUSER_PASSWORD"

if User.objects.filter(username=username).exists():
    print(f"Пользователь {username} уже существует!")
    user = User.objects.get(username=username)
    user.set_password(password)
    user.email = email
    user.is_superuser = True
    user.is_staff = True
    user.save()
    print(f"Пароль для {username} обновлен!")
else:
    User.objects.create_superuser(username, email, password)
    print(f"Суперпользователь {username} создан!")
PYTHON
EOF
else
    echo "Интерактивное создание суперпользователя..."
    echo "Введите данные для суперпользователя:"
    ssh -t "$SERVER" "cd $REMOTE_PATH && DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose exec web python manage.py createsuperuser"
fi

echo ""
echo "✅ Готово!"

