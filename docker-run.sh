#!/bin/bash

# Скрипт для запуска Docker Compose
# Обходит проблему с кириллицей в пути

# Получаем абсолютный путь к директории проекта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Переходим в директорию проекта
cd "$SCRIPT_DIR"

# Устанавливаем имя проекта
export COMPOSE_PROJECT_NAME=lunch_order

# Запускаем docker compose
docker compose up -d --build

echo ""
echo "Сервисы запущены!"
echo "Django доступен на http://localhost:8000"
echo "Админ панель: http://localhost:8000/admin/"
echo ""
echo "Для просмотра логов: docker compose logs -f"
echo "Для остановки: docker compose down"

