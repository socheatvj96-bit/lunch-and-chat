# Статус развертывания

## ✅ Система успешно запущена в Docker!

### Запущенные сервисы:
- ✅ **web** - Django приложение (порт 8080)
- ✅ **db** - PostgreSQL база данных
- ✅ **redis** - Redis для Celery
- ⚠️ **celery** - Celery worker (запускается автоматически)
- ⚠️ **celery-beat** - Celery beat (запускается автоматически)
- ⚠️ **telegram-bot** - Telegram бот (запускается автоматически)

### Тестовые данные загружены:

**Сотрудники (5):**
1. Иван Иванов (telegram_id: 123456789, баланс: 500₽)
2. Мария Петрова (telegram_id: 987654321, баланс: 300₽)
3. Алексей Сидоров (без Telegram, email: alex@example.com, баланс: 450₽)
4. Елена Козлова (telegram_id: 555666777, баланс: 200₽)
5. Дмитрий Волков (без Telegram, email: dmitry@example.com, баланс: 600₽)

**Рестораны (3):**
1. **ВкусВилл** - доступен на текущей неделе
2. **Теремок** - доступен на следующей неделе
3. **Якитория** - доступен всегда

**Блюда (13):**
- ВкусВилл: Салат Цезарь, Борщ с мясом, Котлета по-киевски, Плов, Пицца Маргарита
- Теремок: Блины с мясом, Борщ, Пельмени, Оливье
- Якитория: Ролл Филадельфия, Ролл Калифорния, Суши сет, Лапша Удон

### Доступ:

- **API**: http://localhost:8080/api/
- **Админ панель**: http://localhost:8080/admin/
  - Логин: `admin`
  - Пароль: (установите через `createsuperuser`)

### API Endpoints:

- `GET /api/employees/` - Список сотрудников
- `GET /api/restaurants/available_today/` - Доступные рестораны
- `GET /api/menu-items/available_today/` - Доступные блюда
- `POST /api/orders/create_order/` - Создание заказа

### Команды управления:

```bash
# Просмотр статуса
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose ps

# Просмотр логов
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose logs -f

# Остановка
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose down

# Перезапуск
DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose restart
```

### Следующие шаги:

1. Установите пароль для суперпользователя:
   ```bash
   DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME=lunch_order docker compose exec web python manage.py changepassword admin
   ```

2. Проверьте работу Telegram бота (токен уже настроен)

3. Настройте email для рассылки (если нужно) в `.env` или переменных окружения

4. Проверьте работу Celery задач (начисление баланса в 9:00, рассылка меню в 10:00)

