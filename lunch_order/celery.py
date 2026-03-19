import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lunch_order.settings')

app = Celery('lunch_order')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

