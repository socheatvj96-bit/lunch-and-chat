# Запуск в Docker

## Быстрый старт

```bash
# Запуск всех сервисов
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose up -d

# Или используйте скрипт
./docker-run.sh
```

## Создание суперпользователя

```bash
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose exec web python manage.py createsuperuser
```

## Просмотр логов

```bash
# Все сервисы
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose logs -f

# Конкретный сервис
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose logs -f web
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose logs -f telegram-bot
```

## Остановка

```bash
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose down
```

## Пересоздание с нуля

```bash
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose down -v
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose up -d --build
```

## Доступ

- Django API: http://localhost:8080
- Админ панель: http://localhost:8080/admin/
- API endpoints: http://localhost:8080/api/

## Сервисы

- **web** - Django приложение (порт 8080)
- **db** - PostgreSQL база данных
- **redis** - Redis для Celery
- **celery** - Celery worker
- **celery-beat** - Celery beat (планировщик)
- **telegram-bot** - Telegram бот

## Тестовые данные

Тестовые данные загружаются автоматически при первом запуске web сервиса.

Создано:
- 5 сотрудников (с Telegram ID и без)
- 3 ресторана (ВкусВилл, Теремок, Якитория)
- 13 блюд

## Примечания

- Из-за кириллицы в пути используется `DOCKER_BUILDKIT=0`
- Порт изменен на 8080 (вместо 8000) из-за возможных конфликтов
- Для работы Telegram бота нужен токен в переменных окружения

