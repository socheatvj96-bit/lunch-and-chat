#!/bin/bash

# Финальный деплой с обновлением настроек
# Использование: ./final_deploy.sh

set -e

SERVER="root@155.212.166.158"
PASSWORD="SSH_PASSWORD_REMOVED"

echo "🚀 Финальный деплой проекта..."

# Деплой обновленных файлов
cd /home/n36/3/обед
./deploy_sshpass.sh

# Перезапуск веб-сервера для применения новых настроек
echo ""
echo "🔄 Перезапуск веб-сервера..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER" << 'RESTART_EOF'
    cd /opt/lunch_order
    DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose restart web
    sleep 5
RESTART_EOF

# Проверка доступности
echo ""
echo "✅ Проверка доступности..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER" << 'CHECK_EOF'
    echo "Проверка статики:"
    curl -I http://localhost/static/admin/css/base.css 2>&1 | head -3
    
    echo ""
    echo "Проверка главной страницы:"
    curl -I http://localhost/ 2>&1 | head -5
    
    echo ""
    echo "Проверка админки:"
    curl -I http://localhost/admin/ 2>&1 | head -5
    
    echo ""
    echo "Статус контейнеров:"
    cd /opt/lunch_order
    DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose ps
CHECK_EOF

echo ""
echo "✅ Деплой завершен!"
echo ""
echo "Следующие шаги:"
echo "  1. Настройте DNS: pm.obed.pro -> 155.212.166.158"
echo "  2. Запустите: ./get_ssl_certificate.sh"
echo ""
echo "Проверьте доступность:"
echo "  - HTTP: http://pm.obed.pro (или http://155.212.166.158)"
echo "  - Статика: http://pm.obed.pro/static/admin/css/base.css"
echo "  - Админка: http://pm.obed.pro/admin/"
