# Безопасный деплой на сервер

## ⚠️ Важные меры безопасности

Скрипт `deploy.sh` использует следующие меры для изоляции проекта:

1. **COMPOSE_PROJECT_NAME=lunch_order** - все контейнеры имеют префикс `lunch_order-`, что изолирует их от других проектов
2. **Работа только в `/opt/lunch_order`** - не затрагивает другие директории
3. **Безопасная остановка** - `docker compose down || true` не прервет скрипт при ошибках
4. **Изолированные сети и volumes** - каждый проект имеет свои сети и volumes

## 🚀 Запуск деплоя

### Автоматический деплой (рекомендуется)

```bash
./deploy.sh
```

Или с указанием параметров:

```bash
./deploy.sh user@victor.kiselev.lol /opt/lunch_order
```

### Что делает скрипт:

1. ✅ Копирует файлы через rsync (исключая ненужные)
2. ✅ Останавливает **только** контейнеры `lunch_order-*`
3. ✅ Собирает и запускает новые контейнеры
4. ✅ Применяет миграции БД
5. ✅ Собирает статические файлы
6. ✅ Показывает статус сервисов

### Ручной деплой (если нужен больший контроль)

```bash
# 1. Копирование файлов
rsync -avz --exclude='__pycache__' --exclude='*.pyc' --exclude='venv' \
    --exclude='.env' --exclude='staticfiles' --exclude='media' \
    ./ user@victor.kiselev.lol:/opt/lunch_order/

# 2. Подключение к серверу
ssh user@victor.kiselev.lol

# 3. На сервере
cd /opt/lunch_order

# 4. Остановка (только lunch_order)
COMPOSE_PROJECT_NAME=lunch_order docker compose down

# 5. Запуск
COMPOSE_PROJECT_NAME=lunch_order docker compose up -d --build

# 6. Миграции
COMPOSE_PROJECT_NAME=lunch_order docker compose exec web python manage.py migrate

# 7. Статика
COMPOSE_PROJECT_NAME=lunch_order docker compose exec web python manage.py collectstatic --noinput
```

## 🔍 Проверка после деплоя

```bash
# Статус контейнеров lunch_order
ssh user@victor.kiselev.lol 'cd /opt/lunch_order && COMPOSE_PROJECT_NAME=lunch_order docker compose ps'

# Логи
ssh user@victor.kiselev.lol 'cd /opt/lunch_order && COMPOSE_PROJECT_NAME=lunch_order docker compose logs -f web'

# Проверка, что другие проекты не затронуты
ssh user@victor.kiselev.lol 'docker ps | grep -v lunch_order'
```

## ⚡ Быстрая проверка безопасности

Перед деплоем можно проверить:

```bash
# Какие контейнеры будут затронуты
ssh user@victor.kiselev.lol 'docker ps --format "{{.Names}}" | grep lunch_order'

# Какие сети используются
ssh user@victor.kiselev.lol 'docker network ls | grep lunch_order'
```

## 🛡️ Гарантии безопасности

- ✅ Используется `COMPOSE_PROJECT_NAME` - полная изоляция
- ✅ Работа только в указанной директории
- ✅ Не затрагивает другие docker-compose проекты
- ✅ Не удаляет данные других проектов
- ✅ Безопасная остановка с `|| true`

