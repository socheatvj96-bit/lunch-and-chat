from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import Employee, Restaurant, MenuItem, WorkDayCalendar, BalanceTransaction, GlobalWorkDay
from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone
import logging

logger = logging.getLogger(__name__)

# Стандартная сумма ежедневного начисления
DAILY_ACCRUAL_AMOUNT = Decimal('150.00')


def _accrue_one_day(target_date, is_backfill=False):
    """Начисляет баланс за конкретную дату с защитой от дублей."""
    # Проверяем глобальный календарь
    if not GlobalWorkDay.is_work_day_for_all(target_date):
        logger.info(f"{target_date}: выходной день по общему календарю, пропуск начисления.")
        return 0

    employees = Employee.objects.filter(is_active=True, is_approved=True)
    count = 0

    for employee in employees:
        # Индивидуальный календарь (больничный/отпуск)
        individual_day = WorkDayCalendar.objects.filter(employee=employee, date=target_date).first()
        if individual_day and not individual_day.is_work_day():
            continue

        # Защита от дублей: для сотрудника не должно быть более 1 начисления в день
        already_exists = BalanceTransaction.objects.filter(
            employee=employee,
            transaction_type='accrual',
            created_at__date=target_date
        ).exists()
        if already_exists:
            continue

        amount = employee.daily_balance_amount or DAILY_ACCRUAL_AMOUNT
        old_balance = employee.balance
        employee.balance += amount
        employee.save()

        comment = f'Ежедневное начисление за {target_date}'
        if is_backfill:
            comment = f'Авто-доначисление за {target_date} (восстановление пропуска)'

        tx = BalanceTransaction.objects.create(
            employee=employee,
            transaction_type='accrual',
            amount=amount,
            balance_after=employee.balance,
            comment=comment
        )

        # Для backfill фиксируем дату операции в сам целевой день.
        if is_backfill:
            forced_dt = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0, tzinfo=dt_timezone.utc)
            BalanceTransaction.objects.filter(id=tx.id).update(created_at=forced_dt)

        count += 1
        logger.info(
            f"{target_date}: начислено {amount}₽ сотруднику {employee.name} "
            f"(баланс компании: {old_balance}₽ → {employee.balance}₽)"
        )

    return count


@shared_task
def daily_balance_accrual():
    """Ежедневное начисление баланса сотрудникам
    
    Логика:
    1. Проверяем глобальный календарь рабочих дней
    2. Если день рабочий - начисляем 150₽ всем активным сотрудникам
    3. Если выходной - пропускаем
    """
    today = timezone.now().date()
    count = _accrue_one_day(today, is_backfill=False)
    logger.info(f"Начисление завершено: {count} сотрудников")
    return f"Начислено {count} сотрудникам"


@shared_task
def auto_backfill_balance_accrual():
    """Авто-доначисление пропущенных рабочих дней (защита от сбоев beat/worker)."""
    today = timezone.now().date()
    # Проверяем последние 14 дней (без сегодняшнего)
    start = today - timedelta(days=14)
    target_dates = []
    d = start
    while d < today:
        target_dates.append(d)
        d += timedelta(days=1)

    total = 0
    for target_date in target_dates:
        total += _accrue_one_day(target_date, is_backfill=True)

    logger.info(f"Авто-доначисление завершено. Создано операций: {total}")
    return f"Авто-доначисление: {total} операций"


@shared_task
def send_menu_notifications():
    """Рассылка меню сотрудникам"""
    today = timezone.now().date()
    
    # Получаем доступные рестораны
    available_restaurants = [r for r in Restaurant.objects.all() if r.is_available_today()]
    
    if not available_restaurants:
        logger.info("Нет доступных ресторанов на сегодня")
        return
    
    # Получаем доступные блюда
    restaurant_ids = [r.id for r in available_restaurants]
    menu_items = MenuItem.objects.filter(
        restaurant_id__in=restaurant_ids,
        is_available=True
    )
    
    if not menu_items.exists():
        logger.info("Нет доступных блюд на сегодня")
        return
    
    employees = Employee.objects.filter(is_active=True)
    
    telegram_count = 0
    email_count = 0
    
    # Формируем текст меню
    menu_text = "🍽 *Меню на сегодня:*\n\n"
    for restaurant in available_restaurants:
        items = menu_items.filter(restaurant=restaurant)
        if items.exists():
            menu_text += f"*{restaurant.name}*\n"
            for item in items:
                menu_text += f"  • {item.name} - {item.price}₽\n"
                if item.description:
                    menu_text += f"    _{item.description[:50]}..._\n"
            menu_text += "\n"
    
    menu_text += "\nИспользуйте /menu для заказа"
    
    # Отправляем через Telegram
    try:
        from telegram import Bot
        from telegram.error import TelegramError
        
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        
        for employee in employees:
            if employee.telegram_id:
                try:
                    bot.send_message(
                        chat_id=employee.telegram_id,
                        text=menu_text,
                        parse_mode='Markdown'
                    )
                    telegram_count += 1
                except TelegramError as e:
                    logger.error(f"Ошибка отправки в Telegram для {employee.name}: {e}")
    except Exception as e:
        logger.error(f"Ошибка при отправке через Telegram: {e}")
    
    # Отправляем через Email
    email_subject = "Меню на сегодня"
    email_body = menu_text.replace('*', '').replace('_', '')  # Убираем Markdown для email
    
    for employee in employees:
        if not employee.telegram_id and employee.email:
            try:
                send_mail(
                    email_subject,
                    email_body,
                    settings.DEFAULT_FROM_EMAIL,
                    [employee.email],
                    fail_silently=False,
                )
                email_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки email для {employee.name}: {e}")
    
    logger.info(f"Отправлено меню: Telegram - {telegram_count}, Email - {email_count}")
    return f"Отправлено: Telegram - {telegram_count}, Email - {email_count}"


@shared_task
def send_order_confirmation(employee_id, order_id):
    """Отправка подтверждения заказа"""
    try:
        from orders.models import Employee, Order
        from telegram import Bot
        from telegram.error import TelegramError
        from django.core.mail import send_mail
        
        employee = Employee.objects.get(id=employee_id)
        order = Order.objects.get(id=order_id)
        
        message = f"✅ Заказ подтвержден!\n\n"
        message += f"Дата: {order.order_date}\n"
        message += f"Сумма: {order.total_amount}₽\n"
        message += f"Остаток на балансе: {employee.balance}₽\n\n"
        message += "Блюда:\n"
        for item in order.items.all():
            message += f"  • {item.menu_item.name} x{item.quantity}\n"
        
        # Отправка в Telegram
        if employee.telegram_id:
            try:
                bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                bot.send_message(
                    chat_id=employee.telegram_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except TelegramError as e:
                logger.error(f"Ошибка отправки подтверждения в Telegram: {e}")
        
        # Отправка на Email
        if employee.email:
            try:
                send_mail(
                    "Подтверждение заказа",
                    message.replace('*', '').replace('_', ''),
                    settings.DEFAULT_FROM_EMAIL,
                    [employee.email],
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f"Ошибка отправки подтверждения на email: {e}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке подтверждения заказа: {e}")


@shared_task
def send_admin_notification(employee_id, menu_item_id, message_text):
    """Отправка уведомления администратору о проблеме с товаром"""
    try:
        from orders.models import Employee, MenuItem
        from telegram import Bot
        from telegram.error import TelegramError
        
        employee = Employee.objects.get(id=employee_id)
        menu_item = MenuItem.objects.get(id=menu_item_id)
        
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        
        notification = f"⚠️ *ВНИМАНИЕ АДМИНУ*\n\n"
        notification += f"👤 Сотрудник: {employee.name}\n"
        notification += f"🍽 Товар: {menu_item.name}\n"
        notification += f"💰 Цена: {menu_item.price}₽\n"
        notification += f"🏪 Ресторан: {menu_item.restaurant.name}\n\n"
        notification += f"📝 Сообщение: {message_text}"
        
        bot.send_message(
            chat_id=settings.TELEGRAM_ADMIN_CHAT_ID,
            text=notification,
            parse_mode='Markdown'
        )
        
        logger.info(f"Отправлено уведомление админу о товаре {menu_item.name} от {employee.name}")
        
    except TelegramError as e:
        logger.error(f"Ошибка отправки уведомления админу в Telegram: {e}")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления админу: {e}")
