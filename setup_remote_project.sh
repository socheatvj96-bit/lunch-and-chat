#!/bin/bash
set -e

# 1. Install dependencies
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-venv python3-pip python3-dev libpq-dev postgresql postgresql-contrib nginx certbot python3-certbot-nginx redis-server

# 2. Setup directory
mkdir -p /opt/lunch_order
# Clear old if exists to be clean? Or just overwrite.
# tar overwrite is default.
tar -xzf /opt/project_deploy_files.tar.gz -C /opt/lunch_order

# 3. Setup Venv
cd /opt/lunch_order
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Migrations and Static
python3 manage.py migrate
python3 manage.py collectstatic --noinput

# 5. Config Nginx
# First, ensure we don't have conflicting defaults
rm -f /etc/nginx/sites-enabled/default

# Copy config
cp nginx.conf /etc/nginx/sites-available/pm.obed.pro
ln -sf /etc/nginx/sites-available/pm.obed.pro /etc/nginx/sites-enabled/

# Reload Nginx to start serving HTTP (needed for certbot)
nginx -t
systemctl reload nginx

# 6. Run Certbot
# This modifies the nginx conf to add SSL
certbot --nginx -d pm.obed.pro -m admin@pm.obed.pro --agree-tos --non-interactive --redirect

# 7. Setup Systemd Service for Gunicorn
cat > /etc/systemd/system/lunch_order.service <<EOF
[Unit]
Description=Lunch Order Gunicorn Daemon
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/opt/lunch_order
ExecStart=/opt/lunch_order/venv/bin/gunicorn --access-logfile - --workers 3 --bind 0.0.0.0:8082 lunch_order.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable lunch_order
systemctl restart lunch_order

# Restart Nginx to be sure
systemctl restart nginx

echo "Setup Complete"
