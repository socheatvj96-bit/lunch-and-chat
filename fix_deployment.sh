#!/bin/bash
set -e

echo "Stopping native service..."
systemctl stop lunch_order || true
systemctl disable lunch_order || true
rm -f /etc/systemd/system/lunch_order.service
systemctl daemon-reload

echo "Starting Docker Compose..."
cd /opt/lunch_order

# Ensure .env exists if needed?
# settings.py uses os.getenv.
# docker-compose.yml sets some envs: SECRET_KEY, TELEGRAM_BOT_TOKEN, DATABASE_URL.
# So .env is not strictly required for these, but maybe for others.
# I'll invoke docker compose.

docker compose down
docker compose up -d --build

echo "Reloading Nginx..."
systemctl reload nginx

echo "Docker Setup Complete"
