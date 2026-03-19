"""
Django settings for lunch_order project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['pm.obed.pro', '155.212.166.158', 'localhost', '127.0.0.1']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'orders',
    'telegram_bot',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'lunch_order.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'lunch_order.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

import dj_database_url

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (User uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Лимиты загрузки: тело запроса до 200MB (админка, медиа). Файлы > 5MB пишем во временный файл, не в RAM.
DATA_UPLOAD_MAX_MEMORY_SIZE = 209715200  # 200MB — макс. размер запроса
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880    # 5MB — выше этого файл идёт в temp file
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000  # Увеличиваем лимит полей формы (для массового удаления)

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_ADMIN_CHAT_ID = os.getenv('TELEGRAM_ADMIN_CHAT_ID', '')  # ID чата для уведомлений админу

# Group support LLM integration (Telegram bot in group chat)
SUPPORT_LLM_API_URL = os.getenv('SUPPORT_LLM_API_URL', 'https://r-ai.business-pad.com/api/ai_request/')
SUPPORT_LLM_AUTH_HEADER = os.getenv('SUPPORT_LLM_AUTH_HEADER', '')
SUPPORT_LLM_REFERER = os.getenv('SUPPORT_LLM_REFERER', 'https://core.business-pad.com/')
SUPPORT_LLM_MODEL = os.getenv('SUPPORT_LLM_MODEL', 'gpt-4.1-mini')
SUPPORT_LLM_SCHEMA_TTL_SECONDS = int(os.getenv('SUPPORT_LLM_SCHEMA_TTL_SECONDS', '600'))
SUPPORT_LLM_DB_ROW_LIMIT = int(os.getenv('SUPPORT_LLM_DB_ROW_LIMIT', '50'))
SUPPORT_LLM_CHAT_MEMORY_MESSAGES = int(os.getenv('SUPPORT_LLM_CHAT_MEMORY_MESSAGES', '14'))

# Integration API Basic Auth
INTEGRATION_API_BASIC_USER = os.getenv('INTEGRATION_API_BASIC_USER', '')
INTEGRATION_API_BASIC_PASSWORD = os.getenv('INTEGRATION_API_BASIC_PASSWORD', '')

# Email settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)

# Celery Configuration
from celery.schedules import crontab

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'daily-balance-accrual': {
        'task': 'orders.tasks.daily_balance_accrual',
        'schedule': crontab(hour=9, minute=0),  # 9:00 каждый день
    },
    'auto-backfill-balance-accrual': {
        'task': 'orders.tasks.auto_backfill_balance_accrual',
        'schedule': crontab(hour=9, minute=30),  # 9:30 каждый день: добираем пропуски
    },
    'send-menu-notifications': {
        'task': 'orders.tasks.send_menu_notifications',
        'schedule': crontab(hour=10, minute=0),  # 10:00 каждый день
    },
}

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}

# CORS
CORS_ALLOW_ALL_ORIGINS = True

# CSRF
CSRF_TRUSTED_ORIGINS = [
    'https://pm.obed.pro',
    'http://pm.obed.pro',
    'https://victor.kiselev.lol',
    'http://localhost:8000',
    'http://localhost:8080',
    'http://155.212.166.158:8082',
]

# Login settings
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'admin_products'
LOGOUT_REDIRECT_URL = 'login'

# Supabase (chat)
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# Cache (Redis)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0'),
        'KEY_PREFIX': 'lunch_cache',
    }
}

# Telegram bot username (for link generation)
TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME', 'proektnoe_mishlenie_bot')

# Web Push (VAPID)
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'admin@pm.obed.pro')

