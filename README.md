# 🍽 Lunch Order & Chat — Corporate Lunch Management System

A full-featured web application for corporate lunch ordering with a built-in real-time chat, Telegram Bot integration, and PWA support.

---

## ✨ Features

### 🛒 Lunch Ordering
- Browse weekly menus from restaurants (VkusVill and others)
- Order lunch for any workday, track order status
- Balance system: company subsidy + personal balance
- Order history and cancellations with automatic refunds

### 💬 Real-time Chat (via Supabase)
- **General company chat** — all employees in one room
- **Direct messages (DM)** — private one-on-one conversations
- Emoji picker, message forwarding
- Unread message badges on tab and contact list items
- Contacts sorted by last message time
- Employee avatar uploads

### 🔔 Push Notifications (Web Push / VAPID)
- Browser push notifications for new chat messages
- Works on mobile and desktop (PWA)
- Triggered by Supabase Database Webhooks → Django → pywebpush

### 🤖 Telegram Bot
- Balance inquiries, today's menu, order history
- Notifications for new orders
- One-time token Telegram account linking from desktop browser
- Group chat LLM support assistant (GPT-4.1-mini)

### 📱 PWA (Progressive Web App)
- Installable on Android/iOS home screen
- Service Worker for offline fallback and push handling
- Mobile-first UI optimized for Telegram Mini App

### 🛠 Admin Panel
- Manage employees, restaurants, menu items
- Upload menu item images in bulk via integration API
- Weekly menu management with selection close deadlines
- Export orders to CSV, balance transaction history

---

## 🏗 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2, Django REST Framework |
| Database | PostgreSQL (via dj-database-url) |
| Cache / Queue | Redis + Celery + Celery Beat |
| Real-time Chat | Supabase (PostgreSQL + Realtime) |
| Push Notifications | Web Push API (VAPID) + pywebpush |
| Telegram | python-telegram-bot |
| Frontend | Vanilla JS SPA (no framework) |
| Auth | Django session auth + Telegram WebApp |
| Deployment | Docker Compose + Nginx + Let's Encrypt |

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- A [Supabase](https://supabase.com) project (for real-time chat)
- A Telegram Bot token ([@BotFather](https://t.me/BotFather))
- VAPID keys for Web Push

### 1. Clone & configure

```bash
git clone https://github.com/neo37/lunch-and-chat.git
cd lunch-and-chat
cp .env.example .env
# Fill in .env with your credentials
```

### 2. Generate VAPID keys (for push notifications)

```bash
pip install py-vapid
vapid --gen
# Copy the output keys to .env
```

### 3. Run with Docker Compose

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py createsuperuser
```

App will be available at `http://localhost:8082`

---

## 🗺 URL Structure

| URL | Description |
|---|---|
| `/` | Landing page |
| `/login/` | Staff login |
| `/catalog/` | Product catalog |
| `/admin/products/` | Admin: manage menu items |
| `/app/` | Employee mini-app (Telegram Mini App compatible) |
| `/app/login/` | App authentication |
| `api/integration/menu/day/` | Integration API (Basic Auth) |

---

## 🔧 Supabase Setup

Create a `messages` table in your Supabase project:

```sql
create table messages (
  id bigint generated always as identity primary key,
  sender_name text not null,
  text text not null,
  recipient text default null,  -- null = general chat, name = DM
  created_at timestamp with time zone default now()
);

-- Enable Realtime
alter publication supabase_realtime add table messages;

-- Row-level security (allow all)
alter table messages enable row level security;
create policy "Allow all" on messages for all using (true) with check (true);
```

Set a **Database Webhook** in Supabase:
- Event: `INSERT` on `messages`
- URL: `https://your-domain.com/app/push/send/`
- Headers: `Authorization: Bearer <your-SUPABASE_WEBHOOK_SECRET>`

---

## 📦 Environment Variables

See [`.env.example`](.env.example) for all required variables.

Key ones:

```env
SECRET_KEY=...
DATABASE_URL=postgresql://...
TELEGRAM_BOT_TOKEN=...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=<anon/public key>
VAPID_PRIVATE_KEY=...
VAPID_PUBLIC_KEY=...
```

---

## 📄 License

MIT
