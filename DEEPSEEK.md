```mermaid
gantt
    title Диаграмма Ганта: Разработка системы (ускоренный план)
    dateFormat  YYYY-MM-DD
    axisFormat  %d.%m
    tickInterval 7day

    section Бэкенд (2 недели)
    Проектирование API            :done,    api_design, 2024-01-01, 3d
    Модели БД и миграции          :active,  db_models, after api_design, 4d
    API: сотрудники и баланс      :         api_users, after db_models, 5d
    API: меню и заказы            :         api_menu, after db_models, 5d
    Сервис уведомлений            :         notif_service, after api_users, 3d

    section Админка (2.5 недели)
    Базовый каркас админки        :         admin_base, after api_design, 3d
    Модуль сотрудников            :         admin_users_module, after api_users, 4d
    Модуль балансов               :         admin_balance_module, after api_users, 3d
    Модуль групп товаров          :         admin_groups_module, after api_menu, 5d
    Отчеты и закрытие выбора      :         admin_reports_module, after admin_groups_module, 3d

    section Telegram-бот (2 недели)
    Настройка бота                :         bot_setup, after api_design, 2d
    Регистрация и привязка        :         bot_auth, after api_users, 3d
    Просмотр меню и заказ         :         bot_ordering, after api_menu, 5d
    Уведомления в боте            :         bot_notify, after notif_service, 2d

    section Интеграции (1 неделя)
    Автоначисление баланса        :         auto_balance, after api_users, 4d
    Рассылка меню по расписанию   :         menu_scheduler, after bot_ordering, 3d
    Календарь рабочих дней        :         work_calendar, after api_users, 3d

    section Тестирование и релиз
    Интеграционное тестирование   :         testing, 2024-01-22, 5d
    Фиксы и доработки             :         fixes, after testing, 3d
    Релиз MVP                     :         release_mvp, after fixes, 2d

    section Phase 2 (3 недели)
    Импорт Excel                  :         excel_import, after release_mvp, 7d
    Веб-интерфейс для сотрудников :         user_web, after release_mvp, 10d
    Платежная система             :         payments, after release_mvp, 7d
    Расширенная аналитика         :         analytics, after user_web, 5d
```

## Архитектура приложения

```mermaid
graph TB
    subgraph "Клиентские приложения"
        TG[Telegram Bot]
        ADMIN[Admin Web Panel]
        EMAIL[Email Service]
    end

    subgraph "API Gateway / Load Balancer"
        GW[API Gateway]
        LB[Load Balancer]
    end

    subgraph "Бэкенд сервисы (REST API)"
        AUTH[Auth Service<br/>JWT, OAuth2]
        USER[User Service<br/>Сотрудники, баланс]
        MENU[Menu Service<br/>Группы товаров, меню]
        ORDER[Order Service<br/>Заказы, отчеты]
        NOTIFY[Notification Service<br/>Очередь сообщений]
        SCHED[Scheduler Service<br/>Cron задачи]
    end

    subgraph "Базы данных"
        DB_MAIN[(Main DB<br/>PostgreSQL)]
        DB_CACHE[(Cache<br/>Redis)]
        DB_QUEUE[(Message Queue<br/>RabbitMQ)]
    end

    subgraph "Внешние интеграции"
        TG_API[Telegram API]
        SMTP[SMTP Server]
        RESTAURANT[Restaurant APIs]
        PAYMENT[Payment Gateways]
    end

    TG --> GW
    ADMIN --> GW
    GW --> LB
    LB --> AUTH
    LB --> USER
    LB --> MENU
    LB --> ORDER

    AUTH --> DB_MAIN
    AUTH --> DB_CACHE
    USER --> DB_MAIN
    MENU --> DB_MAIN
    ORDER --> DB_MAIN

    NOTIFY --> DB_QUEUE
    SCHED --> DB_QUEUE

    USER -.-> NOTIFY
    MENU -.-> NOTIFY
    ORDER -.-> NOTIFY

    SCHED --> USER
    SCHED --> MENU

    NOTIFY --> TG_API
    NOTIFY --> SMTP
    NOTIFY --> EMAIL

    ORDER -.-> RESTAURANT
    USER -.-> PAYMENT
```

## Компонентная диаграмма архитектуры

```mermaid
graph LR
    subgraph "Презентационный слой"
        WEB[Веб-интерфейс<br/>React/Vue.js]
        BOT[Telegram Bot<br/>python-telegram-bot]
        EMAIL_CLIENT[Email Client]
    end

    subgraph "Бизнес-логика"
        AUTH_MOD[Модуль аутентификации]
        USER_MOD[Модуль пользователей<br/>• Регистрация<br/>• Баланс<br/>• Календарь]
        MENU_MOD[Модуль меню<br/>• Группы товаров<br/>• Импорт Excel]
        ORDER_MOD[Модуль заказов<br/>• Корзина<br/>• Отчеты]
        PAYMENT_MOD[Модуль платежей]
        NOTIFY_MOD[Модуль уведомлений]
    end

    subgraph "Сервисный слой"
        SCHED_SRV[Сервис планировщика]
        EXPORT_SRV[Сервис экспорта]
        REPORT_SRV[Сервис отчетности]
        VALID_SRV[Сервис валидации]
    end

    subgraph "Слой доступа к данным"
        USER_REPO[User Repository]
        MENU_REPO[Menu Repository]
        ORDER_REPO[Order Repository]
        BALANCE_REPO[Balance Repository]
    end

    subgraph "Базы данных"
        PG[(PostgreSQL)]
        REDIS[(Redis Cache)]
        RABBIT[(RabbitMQ)]
    end

    WEB --> AUTH_MOD
    BOT --> AUTH_MOD

    AUTH_MOD --> USER_REPO
    USER_MOD --> USER_REPO
    MENU_MOD --> MENU_REPO
    ORDER_MOD --> ORDER_REPO

    USER_REPO --> PG
    MENU_REPO --> PG
    ORDER_REPO --> PG

    NOTIFY_MOD --> RABBIT
    SCHED_SRV --> RABBIT

    USER_MOD --> REDIS
    AUTH_MOD --> REDIS

    NOTIFY_MOD --> EMAIL_CLIENT
    EMAIL_CLIENT --> SMTP[External SMTP]
```

## Описание архитектуры:

### 1. **Многослойная архитектура:**
- **Презентационный слой:** Веб-интерфейс (админка), Telegram-бот, Email-рассылки
- **Бизнес-логика:** Изолированные модули с четкими ответственностями
- **Сервисный слой:** Вспомогательные сервисы (планировщик, экспорт, отчеты)
- **Слой данных:** Репозитории для работы с БД

### 2. **Ключевые компоненты:**

#### **Модуль пользователей:**
- Управление профилями сотрудников
- Баланс и финансовые операции
- Календарь рабочих/нерабочих дней
- Критические лимиты и блокировки

#### **Модуль меню:**
- Группы товаров с привязкой к датам
- Импорт из Excel (шаблон nextweek_menu.xlsx)
- Управление видимостью и сроками
- Валидация данных

#### **Модуль заказов:**
- Корзина и оформление заказа
- Проверка доступности баланса
- Формирование отчетов по закрытым группам
- Экспорт в Excel для ресторанов

#### **Модуль уведомлений:**
- Асинхронная очередь сообщений
- Интеграция с Telegram Bot API
- Email-рассылка через SMTP
- Шаблоны сообщений

#### **Сервис планировщика:**
- Ежедневное начисление баланса
- Автоматическая рассылка меню
- Напоминания о закрытии выбора
- Фоновые задачи

### 3. **Технологический стек:**

#### **Бэкенд:**
- **Язык:** Python (FastAPI/Django) или Node.js (NestJS)
- **Базы данных:** PostgreSQL (основная), Redis (кэш)
- **Очередь сообщений:** RabbitMQ или Celery
- **Документация API:** Swagger/OpenAPI

#### **Фронтенд (админка):**
- **Фреймворк:** React/Vue.js
- **UI библиотека:** Ant Design/Element UI
- **Чарты:** Chart.js или Apache ECharts

#### **Telegram-бот:**
- **Библиотека:** python-telegram-bot или Telegraf.js
- **Вебхуки:** для production окружения

#### **Инфраструктура:**
- **Контейнеризация:** Docker + Docker Compose
- **Оркестрация:** Kubernetes (опционально)
- **CI/CD:** GitLab CI/GitHub Actions
- **Мониторинг:** Prometheus + Grafana

### 4. **Безопасность:**
- JWT токены для аутентификации
- RBAC (ролевая модель доступа)
- Валидация входных данных
- HTTPS для всех соединений
- Защита от SQL-инъекций, XSS, CSRF

### 5. **Масштабируемость:**
- Горизонтальное масштабирование сервисов
- Кэширование частых запросов
- Асинхронная обработка задач
- Репликация баз данных

## Сжатые сроки реализации:

### **Неделя 1-2:**
- Базовый бэкенд с API
- Модели базы данных
- Простая аутентификация

### **Неделя 2-3:**
- Админка: управление сотрудниками
- Telegram-бот: регистрация
- Базовая бизнес-логика

### **Неделя 4:**
- Полный цикл заказа
- Закрытие групп и отчеты
- Интеграционное тестирование

### **Неделя 5:**
- Релиз MVP
- Документация и деплой

### **Неделя 6-8:**
- Дополнительные функции Phase 2
- Улучшение UI/UX
- Оптимизация производительности

Такая архитектура позволяет:
1. Параллельно разрабатывать модули
2. Легко тестировать компоненты изолированно
3. Масштабировать нагрузку на отдельные сервисы
4. Интегрировать новые функции без переписывания кода
