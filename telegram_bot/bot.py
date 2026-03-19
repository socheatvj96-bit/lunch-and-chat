import os
import django
import logging
import json
import re
import time
from datetime import date, timedelta
import urllib.request
import urllib.error
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest
from django.conf import settings
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lunch_order.settings')
# Бот работает на async-обработчиках python-telegram-bot, а код использует синхронный Django ORM.
# Разрешаем этот сценарий для текущего процесса бота.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
django.setup()

from orders.models import Employee, MenuItem, Order, Restaurant
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger(__name__)


class LunchOrderBot:
    def __init__(self, token):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.schema_cache = ""
        self.schema_cached_at = 0.0
        self.chat_memory = {}      # {session_id: [{"role": "user|assistant", "text": "..."}]}
        self.chat_last_db = {}     # {session_id: "last formatted db block"}
        self.chat_last_orders_date = {}  # {session_id: date}
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("group_menu", self.group_menu))
        self.application.add_handler(CommandHandler("menu", self.show_menu))
        self.application.add_handler(CommandHandler("balance", self.show_balance))
        self.application.add_handler(CommandHandler("orders", self.show_orders))
        self.application.add_handler(CommandHandler("orders_today", self.show_all_orders_today))
        self.application.add_handler(CommandHandler("who_ordered", self.show_all_orders_today))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_error_handler(self.on_error)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start [link_TOKEN]"""
        telegram_id = str(update.effective_user.id)

        # Handle link token from desktop
        if context.args and context.args[0].startswith('link_'):
            from django.core.cache import cache
            token = context.args[0][len('link_'):]
            employee_id = cache.get(f'tg_link_token:{token}')
            if not employee_id:
                await update.message.reply_text('❌ Ссылка устарела или уже использована. Сгенерируйте новую в приложении.')
                return
            cache.delete(f'tg_link_token:{token}')
            try:
                employee = Employee.objects.get(id=employee_id)
                employee.telegram_id = telegram_id
                employee.save(update_fields=['telegram_id'])
                await update.message.reply_text(
                    f'✅ Telegram успешно привязан к аккаунту {employee.name}!\n'
                    f'Теперь вы будете получать уведомления здесь.'
                )
                return
            except Employee.DoesNotExist:
                await update.message.reply_text('❌ Сотрудник не найден.')
                return

        try:
            employee = Employee.objects.get(telegram_id=telegram_id)
            
            # Создаем inline клавиатуру с кнопками
            keyboard = [
                [
                    InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                    InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
                ],
                [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await update.message.reply_text(
                    f"Привет, {employee.name}!\n\n"
                    f"Выберите действие:",
                    reply_markup=reply_markup
                )
            except BadRequest:
                if update.effective_chat:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"Привет, {employee.name}!\n\nВыберите действие:",
                        reply_markup=reply_markup,
                    )
        except Employee.DoesNotExist:
            try:
                await update.message.reply_text(
                    "Вы не зарегистрированы в системе. Обратитесь к администратору."
                )
            except BadRequest:
                if update.effective_chat:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Вы не зарегистрированы в системе. Обратитесь к администратору.",
                    )

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Глобальный обработчик ошибок, чтобы бот не ронялся на единичных BadRequest."""
        err = context.error
        if isinstance(err, BadRequest):
            logger.warning(f"Telegram BadRequest ignored: {err}")
            return
        logger.error("Unhandled telegram bot error", exc_info=err)
    
    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Показать меню на сегодня"""
        if query:
            telegram_id = str(query.from_user.id)
            message_func = query.edit_message_text
        else:
            telegram_id = str(update.effective_user.id)
            message_func = update.message.reply_text
        
        try:
            employee = Employee.objects.get(telegram_id=telegram_id)
        except Employee.DoesNotExist:
            if query:
                await query.edit_message_text("Вы не зарегистрированы в системе.")
            else:
                await update.message.reply_text("Вы не зарегистрированы в системе.")
            return
        
        today = timezone.now().date()
        available_restaurants = [r for r in Restaurant.objects.all() if r.is_available_today()]
        
        # Проверяем, есть ли меню на сегодня
        has_menu_items = False
        for restaurant in available_restaurants:
            if MenuItem.objects.filter(restaurant=restaurant, is_available=True).exists():
                has_menu_items = True
                break
        
        if not available_restaurants or not has_menu_items:
            # Меню еще не известно
            status_text = "⏳ *Меню на сегодня*\n\n"
            status_text += "Меню на сегодня еще не доступно.\n"
            status_text += "Ожидайте обновления от администратора.\n\n"
            status_text += f"📅 Дата: {today.strftime('%d.%m.%Y')}\n"
            status_text += f"💰 Ваш баланс: {employee.balance}₽"
            
            # Создаем inline клавиатуру с кнопками
            keyboard = [
                [
                    InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                    InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
                ],
                [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message_func(status_text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        # Проверяем, есть ли уже заказ на сегодня
        existing_order = Order.objects.filter(employee=employee, order_date=today).first()
        if existing_order:
            status_text = "✅ *Меню на сегодня*\n\n"
            status_text += f"У вас уже есть заказ на сегодня.\n"
            status_text += f"Используйте кнопку 'Мой выбор' для просмотра."
            
            # Создаем inline клавиатуру с кнопками
            keyboard = [
                [
                    InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                    InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
                ],
                [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message_func(status_text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        # Меню известно - показываем его
        menu_text = "✅ *Меню на сегодня (известно):*\n\n"
        menu_text += f"📅 Дата: {today.strftime('%d.%m.%Y')}\n"
        menu_text += f"💰 Ваш баланс: {employee.balance}₽\n\n"
        
        keyboard_buttons = []
        
        # Показываем информацию о корзине, если она не пуста
        cart = context.user_data.get('cart', {})
        if cart:
            cart_total = sum(item['price'] * item['quantity'] for item in cart.values())
            cart_count = sum(item['quantity'] for item in cart.values())
            menu_text += f"🛒 *В корзине: {cart_count} шт. на сумму {cart_total}₽*\n\n"
        
        for restaurant in available_restaurants:
            items = MenuItem.objects.filter(restaurant=restaurant, is_available=True)
            if items.exists():
                menu_text += f"*🍴 {restaurant.name}*\n"
                for item in items:
                    menu_text += f"  • {item.name} - {item.price}₽\n"
                    if item.description:
                        menu_text += f"    _{item.description[:50]}..._\n"
                    
                    # Кнопка для добавления в корзину
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            f"➕ {item.name} ({item.price}₽)",
                            callback_data=f"add_{item.id}"
                        )
                    ])
                menu_text += "\n"
        
        if keyboard_buttons:
            if cart:
                keyboard_buttons.append([InlineKeyboardButton("🛒 Корзина", callback_data="cart")])
            else:
                keyboard_buttons.append([InlineKeyboardButton("🛒 Посмотреть корзину", callback_data="cart")])
            reply_markup = InlineKeyboardMarkup(keyboard_buttons)
        else:
            reply_markup = None
        
        # Сохраняем состояние корзины в контексте пользователя
        if 'cart' not in context.user_data:
            context.user_data['cart'] = {}
        
        await message_func(menu_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def show_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Показать баланс"""
        if query:
            telegram_id = str(query.from_user.id)
            message_func = query.edit_message_text
        else:
            telegram_id = str(update.effective_user.id)
            message_func = update.message.reply_text
        
        try:
            employee = Employee.objects.get(telegram_id=telegram_id)
            
            # Получаем информацию о заказах на сегодня
            today = timezone.now().date()
            today_order = Order.objects.filter(employee=employee, order_date=today).first()
            
            balance_text = f"💰 *Ваш баланс:* {employee.balance}₽\n\n"
            
            if today_order:
                balance_text += f"📋 *Заказ на сегодня:*\n"
                balance_text += f"Сумма: {today_order.total_amount}₽\n"
                balance_text += f"Статус: {today_order.get_status_display()}\n\n"
            
            # Показываем корзину, если она есть
            cart = context.user_data.get('cart', {})
            if cart:
                cart_total = sum(item['price'] * item['quantity'] for item in cart.values())
                balance_text += f"🛒 *В корзине:* {cart_total}₽\n"
                if employee.balance < cart_total:
                    balance_text += f"⚠️ Недостаточно средств! Нужно еще {cart_total - employee.balance}₽"
            
            # Создаем inline клавиатуру с кнопками
            keyboard = [
                [
                    InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                    InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
                ],
                [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message_func(
                balance_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Employee.DoesNotExist:
            if query:
                await query.edit_message_text("Вы не зарегистрированы в системе.")
            else:
                await update.message.reply_text("Вы не зарегистрированы в системе.")
    
    async def show_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Показать заказы"""
        if query:
            telegram_id = str(query.from_user.id)
            message_func = query.edit_message_text
        else:
            telegram_id = str(update.effective_user.id)
            message_func = update.message.reply_text
        
        try:
            employee = Employee.objects.get(telegram_id=telegram_id)
        except Employee.DoesNotExist:
            if query:
                await query.edit_message_text("Вы не зарегистрированы в системе.")
            else:
                await update.message.reply_text("Вы не зарегистрированы в системе.")
            return
        
        today = timezone.now().date()
        
        # Сначала показываем заказ на сегодня, если есть
        today_order = Order.objects.filter(employee=employee, order_date=today).first()
        
        if today_order:
            text = "📋 *Мой выбор на сегодня:*\n\n"
            status_emoji = {
                'pending': '⏳',
                'confirmed': '✅',
                'sent': '📤',
                'completed': '🎉',
                'cancelled': '❌'
            }.get(today_order.status, '📦')
            
            text += f"{status_emoji} *{today_order.order_date.strftime('%d.%m.%Y')}*\n"
            text += f"💰 Сумма: {today_order.total_amount}₽\n"
            text += f"📊 Статус: {today_order.get_status_display()}\n"
            text += f"🆔 Номер заказа: #{today_order.id}\n\n"
            
            if today_order.items.exists():
                text += "*Блюда:*\n"
                for item in today_order.items.all():
                    item_total = item.price * item.quantity
                    text += f"  • {item.menu_item.name}\n"
                    text += f"    {item.price}₽ × {item.quantity} = {item_total}₽\n"
            
            # Создаем inline клавиатуру с кнопками
            keyboard = [
                [
                    InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                    InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
                ],
                [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message_func(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        # Если заказа на сегодня нет, показываем последние заказы
        orders = Order.objects.filter(employee=employee).order_by('-order_date')[:10]
        
        if not orders:
            text = "📋 *Мой выбор*\n\n"
            text += "У вас пока нет заказов на сегодня."
            
            # Создаем inline клавиатуру с кнопками
            keyboard = [
                [
                    InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                    InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
                ],
                [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message_func(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        text = "📋 *Ваши последние заказы:*\n\n"
        for order in orders:
            status_emoji = {
                'pending': '⏳',
                'confirmed': '✅',
                'sent': '📤',
                'completed': '🎉',
                'cancelled': '❌'
            }.get(order.status, '📦')
            
            text += f"{status_emoji} *{order.order_date.strftime('%d.%m.%Y')}*\n"
            text += f"💰 Сумма: {order.total_amount}₽\n"
            text += f"📊 Статус: {order.get_status_display()}\n"
            text += f"🆔 Номер: #{order.id}\n"
            
            if order.items.exists():
                text += "Блюда:\n"
                for item in order.items.all():
                    text += f"  • {item.menu_item.name} × {item.quantity}\n"
            
            text += "\n"
        
        # Создаем inline клавиатуру с кнопками
        keyboard = [
            [
                InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
            ],
            [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message_func(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def show_all_orders_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Групповая команда: кто и что заказал сегодня."""
        chat_type = update.effective_chat.type if update.effective_chat else "private"
        query = update.callback_query
        message_obj = query.message if query else update.message

        if chat_type not in ("group", "supergroup"):
            if message_obj:
                await message_obj.reply_text("Команда работает в группе. Используйте /orders_today в групповом чате.")
            return

        today = timezone.now().date()
        orders = (
            Order.objects.filter(order_date=today)
            .exclude(status='cancelled')
            .select_related('employee__user')
            .prefetch_related('items__menu_item')
            .order_by('employee__user__last_name', 'employee__user__first_name', 'created_at')
        )

        if not orders.exists():
            if message_obj:
                await message_obj.reply_text(f"📋 На {today.strftime('%d.%m.%Y')} заказов нет.")
            return

        lines = [f"📋 Заказы на {today.strftime('%d.%m.%Y')}:\n"]
        total_sum = Decimal("0")
        for idx, order in enumerate(orders, start=1):
            lines.append(f"{idx}. {order.employee.name} — {order.total_amount}₽ ({order.get_status_display()})")
            if order.items.exists():
                for item in order.items.all():
                    lines.append(f"   • {item.menu_item.name} ×{item.quantity}")
            lines.append("")
            total_sum += order.total_amount

        lines.append(f"Итого по всем: {total_sum}₽")
        # Без markdown, чтобы спецсимволы в названиях блюд не ломали сообщение.
        if message_obj:
            await message_obj.reply_text("\n".join(lines))

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Справка по возможностям бота."""
        text = (
            "🤖 Возможности бота:\n"
            "• /group_menu — меню функций для группы\n"
            "• /orders_today или /who_ordered — кто и что заказал сегодня\n"
            "• /menu — меню на сегодня\n"
            "• /orders — мои заказы\n"
            "• /balance — мой баланс\n"
            "• В группе можно писать обычным текстом — отвечает помощник"
        )
        if update.message:
            await update.message.reply_text(text)

    async def group_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Групповое меню с основными возможностями бота."""
        chat_type = update.effective_chat.type if update.effective_chat else "private"
        if chat_type not in ("group", "supergroup"):
            if update.message:
                await update.message.reply_text("Эта команда доступна в группе.")
            return

        keyboard = [
            [InlineKeyboardButton("📋 Кто заказал сегодня", callback_data="grp_orders_today")],
            [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="grp_menu_today")],
            [InlineKeyboardButton("💰 Мой баланс", callback_data="grp_my_balance")],
            [InlineKeyboardButton("🧾 Мои заказы", callback_data="grp_my_orders")],
            [InlineKeyboardButton("🧠 Помощник (агент)", callback_data="grp_agent_help")],
            [InlineKeyboardButton("❓ Справка", callback_data="grp_help")],
        ]
        if update.message:
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        telegram_id = str(update.effective_user.id)
        
        try:
            employee = Employee.objects.get(telegram_id=telegram_id)
        except Employee.DoesNotExist:
            await query.edit_message_text("Вы не зарегистрированы в системе.")
            return
        
        callback_data = query.data
        
        # Обработка основных кнопок навигации
        if callback_data == "btn_balance":
            await self.show_balance(update, context, query=query)
            return
        elif callback_data == "btn_orders":
            await self.show_orders(update, context, query=query)
            return
        elif callback_data == "btn_menu":
            await self.show_menu(update, context, query=query)
            return
        elif callback_data == "grp_orders_today":
            await self.show_all_orders_today(update, context)
            return
        elif callback_data == "grp_menu_today":
            await self.show_menu(update, context, query=query)
            return
        elif callback_data == "grp_my_balance":
            await self.show_balance(update, context, query=query)
            return
        elif callback_data == "grp_my_orders":
            await self.show_orders(update, context, query=query)
            return
        elif callback_data == "grp_help":
            await query.edit_message_text(
                "🤖 Команды: /group_menu, /orders_today, /menu, /orders, /balance.\n"
                "Также можно писать обычными сообщениями — помощник отвечает в группе."
            )
            return
        elif callback_data == "grp_agent_help":
            await query.edit_message_text(
                "🧠 Помощник в группе:\n"
                "• понимает контекст приложения (заказы, балансы)\n"
                "• учитывает теги участников (@username)\n"
                "• может отвечать по данным (read-only запросы к БД)"
            )
            return
        
        if callback_data.startswith("add_"):
            # Добавление в корзину
            item_id = int(callback_data.split("_")[1])
            try:
                menu_item = MenuItem.objects.get(id=item_id, is_available=True)
                
                if not menu_item.restaurant.is_available_today():
                    await query.answer("Это блюдо больше не доступно", show_alert=True)
                    return
                
                if 'cart' not in context.user_data:
                    context.user_data['cart'] = {}
                
                cart = context.user_data['cart']
                if str(item_id) in cart:
                    cart[str(item_id)]['quantity'] += 1
                else:
                    cart[str(item_id)] = {
                        'menu_item_id': item_id,
                        'quantity': 1,
                        'name': menu_item.name,
                        'price': float(menu_item.price)
                    }
                
                await query.answer(f"✅ Добавлено: {menu_item.name}")
            except MenuItem.DoesNotExist:
                await query.answer("Блюдо не найдено", show_alert=True)
        
        elif callback_data.startswith("inc_"):
            # Увеличить количество
            item_id = callback_data.split("_")[1]
            cart = context.user_data.get('cart', {})
            if item_id in cart:
                cart[item_id]['quantity'] += 1
                await query.answer(f"Количество увеличено: {cart[item_id]['quantity']}")
                # Обновляем отображение корзины
                await self._show_cart(query, employee, context)
            else:
                await query.answer("Товар не найден в корзине", show_alert=True)
        
        elif callback_data.startswith("dec_"):
            # Уменьшить количество
            item_id = callback_data.split("_")[1]
            cart = context.user_data.get('cart', {})
            if item_id in cart:
                if cart[item_id]['quantity'] > 1:
                    cart[item_id]['quantity'] -= 1
                    await query.answer(f"Количество уменьшено: {cart[item_id]['quantity']}")
                    # Обновляем отображение корзины
                    await self._show_cart(query, employee, context)
                else:
                    await query.answer("Минимальное количество: 1", show_alert=True)
            else:
                await query.answer("Товар не найден в корзине", show_alert=True)
        
        elif callback_data.startswith("remove_"):
            # Удалить товар из корзины
            item_id = callback_data.split("_")[1]
            cart = context.user_data.get('cart', {})
            if item_id in cart:
                item_name = cart[item_id]['name']
                del cart[item_id]
                await query.answer(f"Удалено: {item_name}")
                # Обновляем отображение корзины
                await self._show_cart(query, employee, context)
            else:
                await query.answer("Товар не найден в корзине", show_alert=True)
        
        elif callback_data == "noop":
            # Пустое действие (для кнопки с количеством)
            await query.answer()
        
        elif callback_data == "cart":
            # Показать корзину
            cart = context.user_data.get('cart', {})
            if not cart:
                # Создаем клавиатуру с кнопками
                keyboard = [
                    [KeyboardButton("💰 Баланс"), KeyboardButton("📋 Мой выбор")],
                    [KeyboardButton("🍽 Меню на сегодня")]
                ]
                reply_markup_main = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                await query.edit_message_text(
                    "🛒 Корзина пуста.\n\nИспользуйте кнопки для навигации:",
                    reply_markup=reply_markup_main
                )
                return
            
            text = "🛒 *Ваша корзина:*\n\n"
            total = 0
            
            keyboard_buttons = []
            for item_id, item_data in cart.items():
                item_total = item_data['price'] * item_data['quantity']
                text += f"• *{item_data['name']}*\n"
                text += f"  {item_data['price']}₽ × {item_data['quantity']} = {item_total}₽\n"
                
                # Кнопки для управления количеством
                keyboard_buttons.append([
                    InlineKeyboardButton("➖", callback_data=f"dec_{item_id}"),
                    InlineKeyboardButton(f"{item_data['quantity']} шт", callback_data="noop"),
                    InlineKeyboardButton("➕", callback_data=f"inc_{item_id}"),
                    InlineKeyboardButton("🗑", callback_data=f"remove_{item_id}")
                ])
                text += "\n"
                total += item_total
            
            text += f"\n*Итого: {total}₽*\n"
            text += f"Ваш баланс: {employee.balance}₽\n"
            
            if employee.balance < total:
                text += f"\n⚠️ Недостаточно средств! Нужно еще {total - employee.balance}₽"
            
            keyboard_buttons.append([InlineKeyboardButton("➕ Добавить еще", callback_data="back_to_menu")])
            keyboard_buttons.append([
                InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout"),
                InlineKeyboardButton("🗑 Очистить все", callback_data="clear_cart")
            ])
            reply_markup = InlineKeyboardMarkup(keyboard_buttons)
            
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        
        elif callback_data == "checkout":
            # Оформление заказа
            cart = context.user_data.get('cart', {})
            if not cart:
                await query.answer("Корзина пуста", show_alert=True)
                return
            
            today = timezone.now().date()
            
            # Проверяем, нет ли уже заказа
            existing_order = Order.objects.filter(employee=employee, order_date=today).first()
            if existing_order:
                await query.answer("У вас уже есть заказ на сегодня", show_alert=True)
                return
            
            # Подготавливаем данные для создания заказа
            menu_items = []
            total_amount = 0
            
            for item_id, item_data in cart.items():
                try:
                    menu_item = MenuItem.objects.get(id=item_data['menu_item_id'], is_available=True)
                    if not menu_item.restaurant.is_available_today():
                        await query.answer(f"Блюдо {menu_item.name} больше не доступно", show_alert=True)
                        return
                    
                    # Проверяем, что группа товаров не закрыта для выбора
                    if menu_item.group:
                        if menu_item.group.is_selection_closed:
                            await query.answer(f"Выбор из группы '{menu_item.group.name}' закрыт", show_alert=True)
                            return
                        if not menu_item.group.is_visible_today():
                            await query.answer(f"Группа '{menu_item.group.name}' не доступна на сегодня", show_alert=True)
                            return
                    
                    menu_items.append({
                        'menu_item_id': menu_item.id,
                        'quantity': item_data['quantity']
                    })
                    total_amount += menu_item.price * item_data['quantity']
                except MenuItem.DoesNotExist:
                    await query.answer(f"Блюдо {item_data['name']} больше не доступно", show_alert=True)
                    return
            
            # Проверяем возможность сделать заказ
            if not employee.can_make_order():
                keyboard = [
                    [KeyboardButton("💰 Баланс"), KeyboardButton("📋 Мой выбор")],
                    [KeyboardButton("🍽 Меню на сегодня")]
                ]
                reply_markup_main = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                error_msg = "❌ *Невозможно оформить заказ!*\n\n"
                if not employee.is_approved:
                    error_msg += "⚠️ Ваша учётная запись не подтверждена администратором."
                elif not employee.is_active:
                    error_msg += f"⚠️ Ваша учётная запись заблокирована.\n💵 Баланс: {employee.balance}₽\n📉 Лимит: {employee.min_balance_limit}₽\n\nПополните баланс для разблокировки."
                elif employee.balance <= employee.min_balance_limit:
                    error_msg += f"⚠️ Баланс достиг минимального лимита.\n💵 Баланс: {employee.balance}₽\n📉 Лимит: {employee.min_balance_limit}₽\n\nПополните баланс для возможности делать заказы."
                
                await query.edit_message_text(
                    error_msg,
                    parse_mode='Markdown',
                    reply_markup=reply_markup_main
                )
                return
            
            # Проверяем баланс
            if employee.balance < total_amount:
                keyboard = [
                    [KeyboardButton("💰 Баланс"), KeyboardButton("📋 Мой выбор")],
                    [KeyboardButton("🍽 Меню на сегодня")]
                ]
                reply_markup_main = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await query.edit_message_text(
                    f"❌ *Недостаточно средств!*\n\n"
                    f"💰 Нужно: {total_amount}₽\n"
                    f"💵 У вас: {employee.balance}₽\n"
                    f"⚠️ Не хватает: {total_amount - employee.balance}₽\n\n"
                    f"Пополните баланс или измените заказ.",
                    parse_mode='Markdown',
                    reply_markup=reply_markup_main
                )
                return
            
            # Создаем заказ напрямую
            from django.db import transaction
            from orders.models import OrderItem
            
            try:
                with transaction.atomic():
                    order = Order.objects.create(
                        employee=employee,
                        order_date=today,
                        total_amount=total_amount,
                        status='reserved'  # Резервируем средства
                    )
                    
                    for item_data in menu_items:
                        menu_item = MenuItem.objects.get(id=item_data['menu_item_id'])
                        OrderItem.objects.create(
                            order=order,
                            menu_item=menu_item,
                            quantity=item_data['quantity'],
                            price=menu_item.price
                        )
                    
                    # Резервируем средства (логически вычитаем из доступного баланса)
                    # Списание произойдет при закрытии группы администратором
                    employee.balance -= total_amount
                    employee.save()
                    
                    # Создаем запись о резервировании
                    from orders.models import BalanceTransaction
                    BalanceTransaction.objects.create(
                        employee=employee,
                        transaction_type='deduction',
                        amount=-total_amount,
                        balance_after=employee.balance,
                        order=order,
                        comment=f'Резервирование средств за заказ от {today}'
                    )
                
                # Очищаем корзину
                context.user_data['cart'] = {}
                
                # Формируем детали заказа
                order_details = "✅ *Заказ оформлен!*\n\n"
                order_details += f"📅 Дата: {today}\n"
                order_details += f"💰 Сумма: {total_amount}₽\n"
                order_details += f"💵 Остаток на балансе: {employee.balance}₽\n\n"
                order_details += "*Ваш заказ:*\n"
                for item_data in menu_items:
                    menu_item = MenuItem.objects.get(id=item_data['menu_item_id'])
                    order_details += f"  • {menu_item.name} × {item_data['quantity']}\n"
                
                # Создаем клавиатуру с кнопками
                keyboard = [
                    [KeyboardButton("💰 Баланс"), KeyboardButton("📋 Мой выбор")],
                    [KeyboardButton("🍽 Меню на сегодня")]
                ]
                reply_markup_main = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                await query.edit_message_text(
                    order_details,
                    parse_mode='Markdown',
                    reply_markup=reply_markup_main
                )
            except Exception as e:
                logger.error(f"Ошибка при создании заказа: {e}", exc_info=True)
                keyboard = [
                    [KeyboardButton("💰 Баланс"), KeyboardButton("📋 Мой выбор")],
                    [KeyboardButton("🍽 Меню на сегодня")]
                ]
                reply_markup_main = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await query.edit_message_text(
                    f"❌ *Ошибка при создании заказа*\n\n"
                    f"Попробуйте позже или обратитесь к администратору.",
                    parse_mode='Markdown',
                    reply_markup=reply_markup_main
                )
        
        elif callback_data == "clear_cart":
            context.user_data['cart'] = {}
            # Создаем клавиатуру с кнопками
            keyboard = [
                [
                    InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                    InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
                ],
                [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
            ]
            reply_markup_main = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "🗑 Корзина очищена.\n\nИспользуйте кнопки для навигации:",
                reply_markup=reply_markup_main
            )
        
        elif callback_data == "back_to_menu":
            # Возврат к меню - обновляем сообщение
            today = timezone.now().date()
            available_restaurants = [r for r in Restaurant.objects.all() if r.is_available_today()]
            
            has_menu_items = False
            for restaurant in available_restaurants:
                if MenuItem.objects.filter(restaurant=restaurant, is_available=True).exists():
                    has_menu_items = True
                    break
            
            if not available_restaurants or not has_menu_items:
                status_text = "⏳ *Меню на сегодня*\n\n"
                status_text += "Меню на сегодня еще не доступно. Ожидайте обновления."
                keyboard = [
                    [KeyboardButton("💰 Баланс"), KeyboardButton("📋 Мой выбор")],
                    [KeyboardButton("🍽 Меню на сегодня")]
                ]
                reply_markup_main = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await query.edit_message_text(status_text, parse_mode='Markdown', reply_markup=reply_markup_main)
                return
            
            menu_text = "✅ *Меню на сегодня (известно):*\n\n"
            keyboard_buttons = []
            
            cart = context.user_data.get('cart', {})
            if cart:
                cart_total = sum(item['price'] * item['quantity'] for item in cart.values())
                cart_count = sum(item['quantity'] for item in cart.values())
                menu_text += f"🛒 *В корзине: {cart_count} шт. на сумму {cart_total}₽*\n\n"
            
            for restaurant in available_restaurants:
                items = MenuItem.objects.filter(restaurant=restaurant, is_available=True)
                if items.exists():
                    menu_text += f"*🍴 {restaurant.name}*\n"
                    for item in items:
                        menu_text += f"  • {item.name} - {item.price}₽\n"
                        if item.description:
                            menu_text += f"    _{item.description[:50]}..._\n"
                        
                        keyboard_buttons.append([
                            InlineKeyboardButton(
                                f"➕ {item.name} ({item.price}₽)",
                                callback_data=f"add_{item.id}"
                            )
                        ])
                    menu_text += "\n"
            
            if keyboard_buttons:
                if cart:
                    keyboard_buttons.append([InlineKeyboardButton("🛒 Корзина", callback_data="cart")])
                else:
                    keyboard_buttons.append([InlineKeyboardButton("🛒 Посмотреть корзину", callback_data="cart")])
                reply_markup = InlineKeyboardMarkup(keyboard_buttons)
            else:
                reply_markup = None
            
            await query.edit_message_text(menu_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _show_cart(self, query, employee, context):
        """Вспомогательная функция для отображения корзины"""
        cart = context.user_data.get('cart', {})
        if not cart:
            keyboard = [
                [
                    InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                    InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
                ],
                [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
            ]
            reply_markup_main = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "🛒 Корзина пуста.\n\nИспользуйте кнопки для навигации:",
                reply_markup=reply_markup_main
            )
            return
        
        text = "🛒 *Ваша корзина:*\n\n"
        total = 0
        
        keyboard_buttons = []
        for item_id, item_data in cart.items():
            item_total = item_data['price'] * item_data['quantity']
            text += f"• *{item_data['name']}*\n"
            text += f"  {item_data['price']}₽ × {item_data['quantity']} = {item_total}₽\n"
            
            keyboard_buttons.append([
                InlineKeyboardButton("➖", callback_data=f"dec_{item_id}"),
                InlineKeyboardButton(f"{item_data['quantity']} шт", callback_data="noop"),
                InlineKeyboardButton("➕", callback_data=f"inc_{item_id}"),
                InlineKeyboardButton("🗑", callback_data=f"remove_{item_id}")
            ])
            text += "\n"
            total += item_total
        
        text += f"\n*Итого: {total}₽*\n"
        text += f"Ваш баланс: {employee.balance}₽\n"
        
        if employee.balance < total:
            text += f"\n⚠️ Недостаточно средств! Нужно еще {total - employee.balance}₽"
        
        keyboard_buttons.append([InlineKeyboardButton("➕ Добавить еще", callback_data="back_to_menu")])
        keyboard_buttons.append([
            InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout"),
            InlineKeyboardButton("🗑 Очистить все", callback_data="clear_cart")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard_buttons)
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        if not update.message:
            return

        text = (update.message.text or "").strip()
        if not text:
            return

        # Групповой режим "агент поддержки": отвечаем на обычные сообщения через LLM API.
        chat_type = update.effective_chat.type if update.effective_chat else "private"
        if chat_type in ("group", "supergroup"):
            # Не отвечаем на команды — они обрабатываются CommandHandler.
            if text.startswith("/"):
                return
            # Не отвечаем сами себе/ботам.
            if update.effective_user and update.effective_user.is_bot:
                return

            session_id = f"tg_chat_{update.effective_chat.id}"
            self._append_chat_memory(session_id, "user", text)
            history_text = self._format_recent_history(session_id)
            is_followup = self._looks_like_followup(text)

            # Специализированный и более надежный обработчик запросов о заказах.
            # Для вопросов "заказы на завтра / сумма / кто заказал" отвечаем напрямую из БД.
            direct_orders_answer = self._try_answer_orders_query(
                text=text,
                session_id=session_id,
                is_followup=is_followup,
            )
            if direct_orders_answer:
                self._append_chat_memory(session_id, "assistant", direct_orders_answer)
                await update.message.reply_text(direct_orders_answer)
                return

            db_block = ""
            should_query_db = self._looks_like_db_request(text) or (is_followup and session_id in self.chat_last_db)
            if should_query_db:
                query_text = text
                if is_followup:
                    prev_q = self._get_last_meaningful_user_question(session_id)
                    if prev_q:
                        query_text = f"Предыдущий запрос: {prev_q}\nУточнение: {text}"
                sql, sql_comment = self._plan_readonly_sql(query_text, session_id, str(update.update_id))
                if sql:
                    db_block = self._execute_readonly_sql(sql, sql_comment)
                    self.chat_last_db[session_id] = db_block
            elif is_followup and session_id in self.chat_last_db:
                # Если SQL не строили, но есть недавний результат БД — отдадим его как контекст.
                db_block = self.chat_last_db[session_id]

            semantic_prompt = self._build_group_semantic_prompt(update, text, history_text=history_text, db_block=db_block)
            answer = self._call_support_llm(
                prompt=semantic_prompt,
                session_id=session_id,
                log_id=str(update.update_id),
            )
            self._append_chat_memory(session_id, "assistant", answer)
            await update.message.reply_text(answer)
            return

        telegram_id = str(update.effective_user.id)
        
        try:
            employee = Employee.objects.get(telegram_id=telegram_id)
        except Employee.DoesNotExist:
            await update.message.reply_text("Вы не зарегистрированы в системе. Обратитесь к администратору.")
            return
        
        # Обработка текстовых команд (для обратной совместимости)
        if text == "💰 Баланс" or text == "/balance":
            await self.show_balance(update, context)
        elif text == "📋 Мой выбор" or text == "/orders":
            await self.show_orders(update, context)
        elif text == "🍽 Меню на сегодня" or text == "/menu":
            await self.show_menu(update, context)
        else:
            # Создаем inline клавиатуру с кнопками
            keyboard = [
                [
                    InlineKeyboardButton("💰 Баланс", callback_data="btn_balance"),
                    InlineKeyboardButton("📋 Мой выбор", callback_data="btn_orders")
                ],
                [InlineKeyboardButton("🍽 Меню на сегодня", callback_data="btn_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=reply_markup
            )

    def _call_support_llm(self, prompt: str, session_id: str, log_id: str) -> str:
        """Вызов внешнего LLM API для ответа в группе с памятью по session_id."""
        url = getattr(settings, "SUPPORT_LLM_API_URL", "").strip()
        if not url:
            return "Не настроен SUPPORT_LLM_API_URL."

        auth_header = getattr(settings, "SUPPORT_LLM_AUTH_HEADER", "").strip()
        referer = getattr(settings, "SUPPORT_LLM_REFERER", "").strip()
        model = getattr(settings, "SUPPORT_LLM_MODEL", "gpt-4.1-mini")

        payload = {
            "question_to_send": prompt,
            "session_id": session_id,
            "user": "openai",
            "model": model,
            "log_id": log_id,
        }
        body = json.dumps(payload).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header
        if referer:
            headers["Referer"] = referer

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=45) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            try:
                data = json.loads(raw)
            except Exception:
                data = None

            # Поддержка нескольких распространенных форматов ответа API.
            if isinstance(data, dict):
                # Приоритет: API c массивом messages.
                messages = data.get("messages")
                if isinstance(messages, list):
                    extracted = []
                    for m in messages:
                        if isinstance(m, str) and m.strip():
                            extracted.append(m.strip())
                        elif isinstance(m, dict):
                            for mk in ("text", "message", "content"):
                                mv = m.get(mk)
                                if isinstance(mv, str) and mv.strip():
                                    extracted.append(mv.strip())
                                    break
                    if extracted:
                        return "\n".join(extracted)

                for key in ("answer", "response", "text", "result", "message"):
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
                # Иногда ответ лежит глубже.
                if isinstance(data.get("data"), dict):
                    nested = data["data"]
                    messages = nested.get("messages")
                    if isinstance(messages, list):
                        extracted = []
                        for m in messages:
                            if isinstance(m, str) and m.strip():
                                extracted.append(m.strip())
                            elif isinstance(m, dict):
                                for mk in ("text", "message", "content"):
                                    mv = m.get(mk)
                                    if isinstance(mv, str) and mv.strip():
                                        extracted.append(mv.strip())
                                        break
                        if extracted:
                            return "\n".join(extracted)
                    for key in ("answer", "response", "text", "result", "message"):
                        val = nested.get(key)
                        if isinstance(val, str) and val.strip():
                            return val.strip()
            # Если API вернул голый текст.
            if raw.strip():
                return raw.strip()
            return "Пустой ответ от LLM."
        except urllib.error.HTTPError as e:
            return f"LLM HTTP error: {e.code}"
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            return "Не удалось получить ответ от LLM."

    def _build_group_semantic_prompt(self, update: Update, text: str, history_text: str = "", db_block: str = "") -> str:
        """Собирает контекст сообщения группы для более точной LLM-обработки."""
        msg = update.message
        mentions = []
        entities = msg.entities or []
        for ent in entities:
            if ent.type == "mention":
                mention_value = msg.text[ent.offset:ent.offset + ent.length]
                if mention_value:
                    mentions.append(mention_value)
            elif ent.type == "text_mention" and ent.user:
                full_name = " ".join(
                    part for part in [ent.user.first_name, ent.user.last_name] if part
                ).strip()
                if full_name:
                    mentions.append(full_name)

        sender_name = " ".join(
            part for part in [update.effective_user.first_name if update.effective_user else "", update.effective_user.last_name if update.effective_user else ""]
            if part
        ).strip() or (update.effective_user.username if update.effective_user else "unknown")

        chat_title = update.effective_chat.title if update.effective_chat else ""
        mentions_text = ", ".join(mentions) if mentions else "нет"
        app_context = self._build_app_semantic_context()
        history_part = f"\n\nНедавний контекст диалога:\n{history_text}" if history_text else ""
        db_part = f"\n\nДанные из БД (read-only):\n{db_block}" if db_block else ""

        # Инструкция: если сообщение адресовано через тег участнику, трактуем это как "агента/роль",
        # но отвечаем обычным текстом без JSON и тех. метаданных.
        return (
            "Ты агент поддержки в групповом чате. "
            "Отвечай кратко и по делу на русском языке. "
            "Если в сообщении есть теги участников, воспринимай тегнутых пользователей как роли/агентов, "
            "к которым адресована задача, и учитывай это в ответе.\n"
            "Не выводи JSON/служебные поля, только человекочитаемый ответ.\n\n"
            f"Чат: {chat_title}\n"
            f"Автор: {sender_name}\n"
            f"Теги: {mentions_text}\n"
            f"Контекст приложения:\n{app_context}\n\n"
            f"Сообщение: {text}"
            f"{history_part}"
            f"{db_part}"
        )

    def _build_app_semantic_context(self) -> str:
        """Короткий семантический контекст по предметной области + схема БД."""
        return (
            "Система: lunch_order (заказы обедов).\n"
            "Ключевая логика балансов: сначала списывается баланс компании, затем личный баланс сотрудника.\n"
            "Отрицательный лимит применяется к личному балансу сотрудника.\n"
            "Основные сущности: Employee, Order, OrderItem, MenuItem, Restaurant, WorkDayCalendar, "
            "BalanceTransaction, WeekCompanyAmount.\n"
            "Схема БД:\n"
            f"{self._get_schema_snapshot()}"
        )

    def _get_schema_snapshot(self) -> str:
        """Возвращает кешированную текстовую схему таблиц orders_*."""
        ttl = int(getattr(settings, "SUPPORT_LLM_SCHEMA_TTL_SECONDS", 600))
        now_ts = time.time()
        if self.schema_cache and now_ts - self.schema_cached_at < ttl:
            return self.schema_cache

        lines = []
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name LIKE 'orders_%'
                    ORDER BY table_name, ordinal_position
                    """
                )
                rows = cursor.fetchall()
            current_table = None
            for table_name, column_name, data_type in rows:
                if table_name != current_table:
                    lines.append(f"- {table_name}:")
                    current_table = table_name
                lines.append(f"  - {column_name} ({data_type})")
        except Exception as e:
            logger.error(f"Failed to build schema snapshot: {e}", exc_info=True)
            lines.append("Схема БД временно недоступна.")

        self.schema_cache = "\n".join(lines[:300]) if lines else "Схема БД не найдена."
        self.schema_cached_at = now_ts
        return self.schema_cache

    def _looks_like_db_request(self, text: str) -> bool:
        """Эвристика: определяем, нужно ли делать выборку из БД перед ответом."""
        lowered = text.lower()
        triggers = [
            "из базы", "из бд", "в базе", "по базе", "sql", "таблиц", "таблица",
            "сколько заказ", "кто заказал", "покажи заказ", "баланс", "сотрудник",
            "статистика", "отчет", "сводка", "по дням", "за сегодня", "за неделю",
            "чаще всего", "топ", "лидер", "заказывает",
        ]
        return any(t in lowered for t in triggers)

    def _looks_like_followup(self, text: str) -> bool:
        lowered = text.strip().lower()
        followups = {
            "уточни", "подробнее", "поясни", "еще", "ещё", "а кто", "а сколько",
            "а что", "и кто", "и сколько", "и что",
        }
        if lowered in followups:
            return True
        if len(lowered) <= 20 and any(lowered.startswith(x) for x in ("уточ", "подроб", "еще", "ещё")):
            return True
        return False

    def _try_answer_orders_query(self, text: str, session_id: str, is_followup: bool) -> str:
        lowered = text.lower()
        order_intent = any(
            t in lowered for t in [
                "заказ", "заказы", "кто заказал", "кто что заказал",
                "сумма заказ", "итог заказ", "всего заказ", "сколько заказ",
            ]
        )
        # Фразы вроде "и сумму этих заказов" должны сработать как follow-up.
        followup_orders = is_followup and any(t in lowered for t in ["сумм", "итог", "всего", "этих заказ", "их заказ"])
        if not order_intent and not followup_orders:
            return ""

        target_date = self._extract_target_date_from_text(text, session_id=session_id, is_followup=is_followup)
        if not target_date:
            return ""
        self.chat_last_orders_date[session_id] = target_date

        orders = (
            Order.objects.filter(order_date=target_date)
            .exclude(status="cancelled")
            .select_related("employee__user")
            .prefetch_related("items__menu_item")
            .order_by("employee__user__last_name", "employee__user__first_name", "created_at")
        )

        if not orders.exists():
            return f"На {target_date.strftime('%d.%m.%Y')} заказов нет."

        need_total = any(t in lowered for t in ["сумм", "итог", "всего", "сколько денег"])
        need_count = any(t in lowered for t in ["сколько заказ", "количество заказ", "сколько всего"])
        need_details = any(t in lowered for t in ["кто", "что", "список", "по сотруд", "блюд", "детал"])

        # Если запрос общий ("покажи заказы на завтра"), даем и детали, и итог.
        if not (need_total or need_count or need_details):
            need_total = True
            need_details = True

        employee_orders = defaultdict(list)
        total_sum = Decimal("0")
        total_orders = 0
        for order in orders:
            employee_orders[order.employee.name].append(order)
            total_sum += (order.total_amount or Decimal("0"))
            total_orders += 1

        lines = [f"Заказы на {target_date.strftime('%d.%m.%Y')}:"]  # plain text, без markdown
        if need_count:
            lines.append(f"- Заказов: {total_orders}")
            lines.append(f"- Сотрудников: {len(employee_orders)}")
        if need_total:
            lines.append(f"- Общая сумма: {total_sum}₽")

        if need_details:
            lines.append("")
            idx = 1
            for employee_name in sorted(employee_orders.keys()):
                emp_orders = employee_orders[employee_name]
                emp_sum = sum((o.total_amount or Decimal("0")) for o in emp_orders)
                lines.append(f"{idx}. {employee_name} — {emp_sum}₽")
                for o in emp_orders:
                    for it in o.items.all():
                        lines.append(f"   • {it.menu_item.name} ×{it.quantity}")
                idx += 1

        answer = "\n".join(lines)
        # Telegram max text ~= 4096; подрежем, чтобы сообщение точно отправилось.
        if len(answer) > 3800:
            answer = answer[:3750] + "\n... (список обрезан)"
        return answer

    def _extract_target_date_from_text(self, text: str, session_id: str, is_followup: bool) -> date | None:
        lowered = text.lower()
        today = timezone.localdate()

        if "сегодня" in lowered:
            return today
        if "завтра" in lowered:
            return today + timedelta(days=1)
        if "послезавтра" in lowered:
            return today + timedelta(days=2)

        # Фиксируем популярный кейс "на пятницу"
        if "пятниц" in lowered:
            return today + timedelta((4 - today.weekday()) % 7)
        if "понедель" in lowered:
            return today + timedelta((0 - today.weekday()) % 7)
        if "вторник" in lowered:
            return today + timedelta((1 - today.weekday()) % 7)
        if "сред" in lowered:
            return today + timedelta((2 - today.weekday()) % 7)
        if "четверг" in lowered:
            return today + timedelta((3 - today.weekday()) % 7)
        if "суббот" in lowered:
            return today + timedelta((5 - today.weekday()) % 7)
        if "воскрес" in lowered:
            return today + timedelta((6 - today.weekday()) % 7)

        # Поддержка даты формата dd.mm[.yyyy]
        m = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?\b", lowered)
        if m:
            d = int(m.group(1))
            mm = int(m.group(2))
            yy_raw = m.group(3)
            if yy_raw:
                yy = int(yy_raw)
                if yy < 100:
                    yy += 2000
            else:
                yy = today.year
            try:
                return date(yy, mm, d)
            except ValueError:
                return None

        if is_followup and session_id in self.chat_last_orders_date:
            return self.chat_last_orders_date[session_id]
        return None

    def _append_chat_memory(self, session_id: str, role: str, text: str):
        if session_id not in self.chat_memory:
            self.chat_memory[session_id] = []
        self.chat_memory[session_id].append({"role": role, "text": text})
        max_msgs = int(getattr(settings, "SUPPORT_LLM_CHAT_MEMORY_MESSAGES", 14))
        self.chat_memory[session_id] = self.chat_memory[session_id][-max_msgs:]

    def _format_recent_history(self, session_id: str) -> str:
        messages = self.chat_memory.get(session_id, [])
        # Убираем текущее сообщение пользователя из истории, чтобы не дублировать.
        if messages and messages[-1]["role"] == "user":
            messages = messages[:-1]
        if not messages:
            return ""
        return "\n".join(
            f"{'Пользователь' if m['role'] == 'user' else 'Бот'}: {m['text']}"
            for m in messages[-8:]
        )

    def _get_last_meaningful_user_question(self, session_id: str) -> str:
        messages = self.chat_memory.get(session_id, [])
        for m in reversed(messages[:-1]):  # исключаем текущее "уточни"
            if m["role"] == "user" and not self._looks_like_followup(m["text"]):
                return m["text"]
        return ""

    def _plan_readonly_sql(self, user_text: str, session_id: str, log_id: str):
        """Просим LLM сгенерировать только безопасный read-only SQL."""
        schema = self._get_schema_snapshot()
        planner_prompt = (
            "Сгенерируй ОДИН SQL запрос ТОЛЬКО для PostgreSQL, только read-only.\n"
            "Разрешены только SELECT/WITH. Запрещены INSERT/UPDATE/DELETE/ALTER/DROP/CREATE/TRUNCATE.\n"
            "Ограничь результат максимум 50 строками (через LIMIT).\n"
            "Ответь только JSON формата: "
            "{\"sql\":\"...\",\"comment\":\"коротко что выбрал\"}\n\n"
            f"Схема:\n{schema}\n\n"
            f"Запрос пользователя: {user_text}"
        )
        # Важно: отдельная planner-сессия, чтобы JSON/SQL-инструкции не засоряли диалоговую память.
        raw = self._call_support_llm(
            planner_prompt,
            session_id=f"{session_id}__sql_planner",
            log_id=f"{log_id}-sql",
        )
        try:
            payload = json.loads(raw)
            sql = (payload.get("sql") or "").strip()
            comment = (payload.get("comment") or "").strip()
        except Exception:
            sql = ""
            comment = ""
            # fallback: попробуем вытащить sql из текста
            m = re.search(r"(SELECT|WITH)\s+.+", raw, flags=re.IGNORECASE | re.DOTALL)
            if m:
                sql = m.group(0).strip()
        sql = self._normalize_planned_sql(sql)
        if not self._is_safe_readonly_sql(sql):
            return "", ""
        return sql, comment

    def _normalize_planned_sql(self, sql: str) -> str:
        """Нормализация SQL из LLM: убираем markdown/code fences и escaped newlines."""
        if not sql:
            return ""
        q = sql.strip()
        # Иногда LLM возвращает SQL в ```sql ... ```
        q = re.sub(r"^```(?:sql)?\s*", "", q, flags=re.IGNORECASE)
        q = re.sub(r"\s*```$", "", q)
        # Иногда приходят литералы \\n / \\t, которые нужно превратить в реальные пробелы/переносы.
        q = q.replace("\\r", "\n").replace("\\n", "\n").replace("\\t", " ")
        return q.strip()

    def _is_safe_readonly_sql(self, sql: str) -> bool:
        if not sql:
            return False
        cleaned = sql.strip().rstrip(";")
        if not re.match(r"^(select|with)\b", cleaned, flags=re.IGNORECASE):
            return False
        forbidden = [
            "insert", "update", "delete", "drop", "alter", "create", "truncate",
            "grant", "revoke", "vacuum", "analyze", "copy", "call", "do ",
        ]
        lowered = cleaned.lower()
        return not any(tok in lowered for tok in forbidden)

    def _execute_readonly_sql(self, sql: str, comment: str = "") -> str:
        """Выполняет безопасный read-only SQL и форматирует результат."""
        try:
            q = self._normalize_planned_sql(sql).rstrip(";")
            # Подстраховка: если LIMIT не указан, ограничим сами.
            # Ищем LIMIT устойчиво, включая конец строки и переносы.
            has_limit = bool(re.search(r"\blimit\s+\d+\b", q, flags=re.IGNORECASE))
            if not has_limit:
                q = f"{q} LIMIT {int(getattr(settings, 'SUPPORT_LLM_DB_ROW_LIMIT', 50))}"
            with connection.cursor() as cursor:
                cursor.execute(q)
                cols = [c[0] for c in (cursor.description or [])]
                rows = cursor.fetchall()
            if not cols:
                return "SQL выполнен, но без табличного результата."
            lines = []
            if comment:
                lines.append(f"Комментарий: {comment}")
            lines.append("Колонки: " + ", ".join(cols))
            for idx, row in enumerate(rows, start=1):
                values = [str(v) for v in row]
                lines.append(f"{idx}. " + " | ".join(values))
            if not rows:
                lines.append("Записей не найдено.")
            return "\n".join(lines[:120])
        except Exception as e:
            logger.error(f"Readonly SQL execution failed: {e}", exc_info=True)
            return "Не удалось выполнить read-only запрос к БД."
    
    def run(self):
        """Запуск бота"""
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def start_bot():
    """Функция для запуска бота"""
    token = settings.TELEGRAM_BOT_TOKEN
    bot = LunchOrderBot(token)
    bot.run()

