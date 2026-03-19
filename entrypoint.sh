#!/bin/bash
set -e

# Wait for the database to be ready (simple loop)
while ! python manage.py migrate --check 2>/dev/null; do
  echo "⏳ Waiting for database..."
  sleep 2
done

# Apply migrations
echo "🚀 Applying migrations..."
python manage.py migrate --noinput

# Create superuser if it does not exist
echo "🔐 Ensuring superuser exists..."
python - <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lunch_order.settings')
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='victor').exists():
    User.objects.create_superuser('victor', 'victor@example.com', 'ponedelnik')
    print('✅ Superuser created: victor / ponedelnik')
else:
    print('✅ Superuser already exists')
PY

# Execute the original command passed to the container
exec "$@"
