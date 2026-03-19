#!/bin/bash

# Скрипт для получения SSL сертификата после настройки DNS
# Использование: ./get_ssl_certificate.sh

set -e

SERVER="root@155.212.166.158"
PASSWORD="SSH_PASSWORD_REMOVED"

echo "🔒 Получение SSL сертификата для pm.obed.pro..."
echo "⚠️  Убедитесь, что домен pm.obed.pro указывает на IP 155.212.166.158"
echo ""

# Проверка DNS
echo "🔍 Проверка DNS..."
DNS_IP=$(dig +short pm.obed.pro @8.8.8.8 | tail -1)
if [ "$DNS_IP" = "155.212.166.158" ]; then
    echo "✅ DNS настроен правильно: pm.obed.pro -> $DNS_IP"
else
    echo "⚠️  DNS не настроен или указывает на другой IP: $DNS_IP"
    echo "Продолжаем попытку получения сертификата..."
fi

echo ""

# Получение сертификата через nginx плагин
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER" << 'SSL_EOF'
    set -e
    
    # Останавливаем nginx временно для standalone режима
    echo "⏸️  Временная остановка nginx..."
    systemctl stop nginx
    
    # Получение сертификата
    echo "🔒 Получение сертификата..."
    certbot certonly --standalone -d pm.obed.pro --non-interactive --agree-tos --email admin@pm.obed.pro --preferred-challenges http || {
        echo "⚠️  Не удалось получить сертификат. Проверьте DNS настройки."
        systemctl start nginx
        exit 1
    }
    
    # Запускаем nginx обратно
    echo "▶️  Запуск nginx..."
    systemctl start nginx
    
    echo "✅ Сертификат получен!"
SSL_EOF

# Обновление конфигурации nginx для HTTPS
echo ""
echo "🔄 Обновление конфигурации nginx для HTTPS..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER" << 'UPDATE_HTTPS_EOF'
    set -e
    
    if [ -f /etc/letsencrypt/live/pm.obed.pro/fullchain.pem ]; then
        # Создаем полную конфигурацию с HTTPS
        cat > /etc/nginx/sites-available/pm.obed.pro << 'NGINX_HTTPS_CONFIG'
server {
    listen 80;
    server_name pm.obed.pro;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name pm.obed.pro;
    
    ssl_certificate /etc/letsencrypt/live/pm.obed.pro/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pm.obed.pro/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Увеличение размера загрузки файлов (до 200MB для админки)
    client_max_body_size 200M;
    
    location / {
        proxy_pass http://localhost:8082;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        
        # Для WebSocket если нужно
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    location /static/ {
        alias /opt/lunch_order/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
    
    location /media/ {
        alias /opt/lunch_order/media/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }
}
NGINX_HTTPS_CONFIG
        
        nginx -t
        systemctl reload nginx
        echo "✅ HTTPS конфигурация применена"
    else
        echo "❌ Сертификат не найден"
        exit 1
    fi
UPDATE_HTTPS_EOF

echo ""
echo "✅ SSL сертификат настроен!"
echo ""
echo "Сайт доступен по адресу: https://pm.obed.pro"
echo ""
echo "Для автоматического обновления сертификата:"
echo "  certbot renew --dry-run"
