#!/bin/bash

# Скрипт для деплоя на сервер
# Использование: ./deploy.sh [user@host] [remote_path]

set -e

# Параметры по умолчанию
SERVER="${1:-user@victor.kiselev.lol}"
REMOTE_PATH="${2:-/opt/lunch_order}"

echo "🚀 Начинаем деплой на сервер..."
echo "Сервер: $SERVER"
echo "Путь: $REMOTE_PATH"
echo ""

# Список файлов и директорий для исключения
EXCLUDE_FILE=$(mktemp)
cat > "$EXCLUDE_FILE" << EOF
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info/
dist/
build/
.venv/
venv/
env/
ENV/
.env
*.log
*.sqlite3
db.sqlite3
celerybeat-schedule
celerybeat.pid
*.tar.gz
.git/
.gitignore
.DS_Store
*.swp
*.swo
*~
.vscode/
.idea/
staticfiles/
media/
EOF

echo "📦 Копирование файлов на сервер..."
rsync -avz --progress \
    --exclude-from="$EXCLUDE_FILE" \
    --exclude='.git' \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='venv' \
    --exclude='.env' \
    --exclude='db.sqlite3' \
    --exclude='staticfiles' \
    ./ "$SERVER:$REMOTE_PATH/"

rm "$EXCLUDE_FILE"

echo ""
echo "🔄 Перезапуск сервисов на сервере..."
echo "⚠️  ВАЖНО: Используется COMPOSE_PROJECT_NAME=lunch_order для изоляции от других проектов"
ssh "$SERVER" << EOF
    set -e
    cd $REMOTE_PATH
    
    echo "📋 Проверка текущих контейнеров lunch_order..."
    DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose ps || echo "Контейнеры еще не запущены"
    
    echo ""
    echo "🛑 Остановка старых контейнеров (только lunch_order)..."
    DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose down || true
    
    echo ""
    echo "🔨 Сборка и запуск новых контейнеров..."
    DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose up -d --build
    
    echo ""
    echo "⏳ Ожидание запуска контейнеров (10 секунд)..."
    sleep 10
    
    echo ""
    echo "📊 Применение миграций..."
    DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose exec -T web python manage.py migrate --noinput || true
    
    echo ""
    echo "📦 Сбор статики..."
    DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose exec -T web python manage.py collectstatic --noinput || true
    
    echo ""
    echo "✅ Проверка статуса сервисов lunch_order..."
    DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose ps
    
    echo ""
    echo "📋 Список всех контейнеров (для проверки, что другие проекты не затронуты):"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAMES|lunch_order" || echo "Только контейнеры lunch_order"
EOF

echo ""
echo "✅ Деплой завершен!"
echo ""
echo "Для просмотра логов на сервере:"
echo "  ssh $SERVER 'cd $REMOTE_PATH && docker compose logs -f'"
echo ""
echo "Для просмотра логов бота:"
echo "  ssh $SERVER 'cd $REMOTE_PATH && docker compose logs -f telegram-bot'"

