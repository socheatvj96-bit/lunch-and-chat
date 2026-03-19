from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from .models import Employee, MenuItem, MenuItemGroup, Order, OrderItem, BalanceTransaction, SystemConfig, Settings, PushSubscription
from decimal import Decimal
import json
import urllib.request
import urllib.parse
import base64
import binascii
import hmac
from django.conf import settings


@csrf_exempt
@require_http_methods(["POST"])
def user_login(request):
    """Авторизация пользователя через стандартную систему Django"""
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        password = (data.get('password') or '').strip()
        
        if not username or not password:
            return JsonResponse({'success': False, 'error': 'Логин и пароль обязательны'}, status=400)
        
        # Аутентификация через Django
        user = authenticate(request, username=username, password=password)
        
        if user is None:
            return JsonResponse({'success': False, 'error': 'Неверные учетные данные'}, status=401)
        
        # Проверяем, есть ли связанный Employee
        try:
            employee = user.employee
        except Employee.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'У вас нет доступа к системе заказов'}, status=403)
        
        # Проверяем, что учетная запись подтверждена и активна
        if not employee.is_approved:
            return JsonResponse({'success': False, 'error': 'Учётная запись не подтверждена администратором'}, status=403)
        
        if not employee.is_active:
            return JsonResponse({'success': False, 'error': 'Учётная запись заблокирована'}, status=403)
        
        # Логиним пользователя в сессию Django
        login(request, user)
        
        # Возвращаем данные сотрудника
        return JsonResponse({
            'success': True,
            'employee': {
                'id': employee.id,
                'name': employee.name,
                'email': employee.email,
                'balance': float(employee.balance),
                'company_balance': float(employee.balance),
                'personal_balance': float(employee.personal_balance),
                'telegram_linked': bool(employee.telegram_id),
                'telegram_id': employee.telegram_id or '',
                'min_balance_limit': float(employee.min_balance_limit),
                'can_make_order': employee.can_make_order(),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def user_app(request):
    """Главная страница мини-приложения для пользователей"""
    # Проверяем, есть ли параметр авторизации в URL или сессии
    employee_id = request.GET.get('employee_id') or request.session.get('employee_id')
    
    # Get system logo
    logo_url = None
    config = SystemConfig.objects.first()
    if config and config.logo:
        logo_url = config.logo.url

    from django.conf import settings as django_settings
    context = {
        'employee_id': employee_id,
        'is_telegram': request.GET.get('tgWebAppStartParam') is not None,
        'logo_url': logo_url,
        'SUPABASE_URL': django_settings.SUPABASE_URL,
        'SUPABASE_KEY': django_settings.SUPABASE_KEY,
        'VAPID_PUBLIC_KEY': django_settings.VAPID_PUBLIC_KEY,
    }
    
    return render(request, 'orders/user_app.html', context)


def get_employees_list(request):
    """Список активных сотрудников для чата"""
    employees = Employee.objects.filter(is_active=True, is_approved=True).order_by('user__first_name', 'user__last_name')
    data = [{'id': e.id, 'name': e.name, 'avatar_url': e.avatar.url if e.avatar else None} for e in employees]
    return JsonResponse({'success': True, 'employees': data})


@csrf_exempt
@require_http_methods(["POST"])
def push_subscribe(request):
    """Сохранить или обновить Web Push подписку браузера."""
    try:
        data = json.loads(request.body)
        employee_name = str(data.get('employee_name', '')).strip()
        endpoint = str(data.get('endpoint', '')).strip()
        p256dh = str(data.get('p256dh', '')).strip()
        auth_key = str(data.get('auth', '')).strip()
        if not (employee_name and endpoint and p256dh and auth_key):
            return JsonResponse({'success': False, 'error': 'Missing fields'}, status=400)
        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={'employee_name': employee_name, 'p256dh': p256dh, 'auth': auth_key}
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def push_send(request):
    """Вызывается Supabase Webhook при INSERT в messages — рассылает пуш получателям."""
    # Simple shared-secret check
    webhook_secret = settings.SUPABASE_WEBHOOK_SECRET if hasattr(settings, 'SUPABASE_WEBHOOK_SECRET') else ''
    if webhook_secret:
        auth_header = request.headers.get('Authorization', '')
        if auth_header != f'Bearer {webhook_secret}':
            return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        body = json.loads(request.body)
        record = body.get('record', {})
        sender_name = record.get('sender_name', '')
        recipient = record.get('recipient')  # None = general chat
        text = record.get('text', '')

        if recipient:
            # DM — push only to recipient
            target_names = [recipient]
        else:
            # General chat — push to everyone except sender
            target_names = list(
                PushSubscription.objects.exclude(employee_name=sender_name)
                .values_list('employee_name', flat=True)
                .distinct()
            )

        subscriptions = PushSubscription.objects.filter(employee_name__in=target_names)
        if not subscriptions.exists():
            return JsonResponse({'success': True, 'sent': 0})

        from pywebpush import webpush, WebPushException
        private_key = settings.VAPID_PRIVATE_KEY
        public_key = settings.VAPID_PUBLIC_KEY
        claims_email = settings.VAPID_CLAIMS_EMAIL
        if not private_key:
            return JsonResponse({'success': False, 'error': 'VAPID not configured'})

        title = sender_name if recipient else f'Общий чат: {sender_name}'
        payload = json.dumps({'title': title, 'body': text[:100], 'sender': sender_name, 'recipient': recipient or ''})

        sent, failed = 0, []
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={'endpoint': sub.endpoint, 'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
                    data=payload,
                    vapid_private_key=private_key,
                    vapid_claims={'sub': f'mailto:{claims_email}'},
                )
                sent += 1
            except WebPushException as e:
                status = e.response.status_code if e.response else 0
                if status in (404, 410):  # subscription expired
                    sub.delete()
                else:
                    failed.append(str(e))

        return JsonResponse({'success': True, 'sent': sent, 'failed': len(failed)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def telegram_link_token(request):
    """Генерация одноразовой ссылки для привязки Telegram с компьютера."""
    from django.core.cache import cache
    import secrets

    # Resolve employee from session or employee_id param
    employee = None
    if request.user.is_authenticated:
        try:
            employee = request.user.employee
        except Employee.DoesNotExist:
            pass
    if not employee:
        eid = request.GET.get('employee_id') or (json.loads(request.body or '{}').get('employee_id') if request.method == 'POST' else None)
        if eid:
            try:
                employee = Employee.objects.get(id=eid)
            except Employee.DoesNotExist:
                pass
    if not employee:
        return JsonResponse({'success': False, 'error': 'Сотрудник не найден'}, status=404)

    token = secrets.token_urlsafe(20)
    cache.set(f'tg_link_token:{token}', employee.id, timeout=300)  # 5 минут

    bot_username = settings.TELEGRAM_BOT_USERNAME
    link = f'https://t.me/{bot_username}?start=link_{token}'
    return JsonResponse({'success': True, 'link': link, 'expires_in': 300})


@csrf_exempt
@require_http_methods(["POST"])
def send_support_message(request):
    """Отправить сообщение в поддержку через Telegram"""
    try:
        data = json.loads(request.body)
        text = str(data.get('text', '')).strip()
        employee_id = data.get('employee_id')
        if not text:
            return JsonResponse({'success': False, 'error': 'Пустое сообщение'}, status=400)
        sender = ''
        if employee_id:
            try:
                emp = Employee.objects.get(id=employee_id)
                sender = emp.name
            except Employee.DoesNotExist:
                pass
        admin_chat_id = settings.TELEGRAM_ADMIN_CHAT_ID
        full_text = f"📩 Обращение в поддержку\nОт: {sender or 'неизвестный'}\n\n{text}"
        ok = _send_telegram_message(admin_chat_id, full_text)
        return JsonResponse({'success': ok})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def check_auth(request):
    """Проверка текущей авторизации пользователя"""
    try:
        if request.user.is_authenticated:
            try:
                employee = request.user.employee
                if employee.is_approved and employee.is_active:
                    return JsonResponse({
                        'success': True,
                        'authenticated': True,
                        'employee': {
                            'id': employee.id,
                            'name': employee.name,
                            'email': employee.email,
                            'balance': float(employee.balance),
                            'company_balance': float(employee.balance),
                            'personal_balance': float(employee.personal_balance),
                            'telegram_linked': bool(employee.telegram_id),
                            'telegram_id': employee.telegram_id or '',
                            'min_balance_limit': float(employee.min_balance_limit),
                            'can_make_order': employee.can_make_order(),
                        }
                    })
            except Employee.DoesNotExist:
                pass
        
        return JsonResponse({'success': True, 'authenticated': False})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def user_register(request):
    """Регистрация нового сотрудника (временно отключена)"""
    return JsonResponse({
        'success': False,
        'error': 'Регистрация временно отключена. Обратитесь к администратору для создания учетной записи.'
    }, status=403)


@csrf_exempt
@require_http_methods(["GET"])
def get_menu(request):
    """Получение доступного меню на выбранную дату или на неделю"""
    try:
        # Получаем дату из параметров, или используем сегодня
        date_str = request.GET.get('date')
        if date_str:
            try:
                target_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
            except:
                target_date = timezone.now().date()
        else:
            target_date = timezone.now().date()
        
        # Получаем доступные группы товаров на выбранную дату
        groups = MenuItemGroup.objects.filter(
            is_active=True,
            period_start__lte=target_date,
            period_end__gte=target_date,
            is_selection_closed=False
        ).prefetch_related('items__restaurant', 'items__images')
        
        menu_data = []
        for group in groups:
            items = []
            for item in group.items.filter(is_available=True):
                primary_image = item.get_primary_image()
                image_url = None
                if primary_image and primary_image.image:
                    try:
                        image_url = primary_image.image.url
                    except Exception:
                        image_url = None
                if not image_url and getattr(item, 'image_url', None):
                    image_url = item.image_url
                items.append({
                    'id': item.id,
                    'name': item.name,
                    'description': item.description,
                    'price': float(item.price) if item.price else 0,
                    'restaurant': item.restaurant.name,
                    'image': image_url,
                    'weight': item.weight or '',
                    'calories': item.calories,
                    'protein': float(item.protein) if item.protein else None,
                    'fat': float(item.fat) if item.fat else None,
                    'carbohydrates': float(item.carbohydrates) if item.carbohydrates else None,
                    'composition': item.composition or '',
                    'source_url': item.source_url or '',
                })
            
            if items:
                menu_data.append({
                    'group_id': group.id,
                    'group_name': group.name,
                    'period_start': group.period_start.isoformat() if group.period_start else None,
                    'period_end': group.period_end.isoformat() if group.period_end else None,
                    'items': items,
                })
        
        return JsonResponse({'success': True, 'menu': menu_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_order(request):
    """Создание заказа пользователем на выбранную дату"""
    try:
        data = json.loads(request.body)
        employee_id = data.get('employee_id')
        group_id = data.get('group_id')
        order_date_str = data.get('order_date')  # Дата заказа (можно выбрать на будущее)
        items = data.get('items', [])  # [{'menu_item_id': 1, 'quantity': 2}, ...]
        
        if not employee_id:
            return JsonResponse({'success': False, 'error': 'employee_id обязателен'}, status=400)
        
        if not items:
            return JsonResponse({'success': False, 'error': 'Выберите хотя бы одно блюдо'}, status=400)
        
        employee = get_object_or_404(Employee, id=employee_id)
        
        # Проверяем возможность сделать заказ
        if not employee.can_make_order():
            if not employee.is_approved:
                return JsonResponse({'success': False, 'error': 'Учётная запись не подтверждена'}, status=403)
            if not employee.is_active:
                return JsonResponse({'success': False, 'error': 'Учётная запись заблокирована'}, status=403)
            if employee.personal_balance <= employee.min_balance_limit:
                return JsonResponse({
                    'success': False, 
                    'error': f'Баланс достиг минимального лимита ({employee.min_balance_limit}₽). Пополните баланс.'
                }, status=403)
        
        # Определяем дату заказа
        if order_date_str:
            try:
                order_date = timezone.datetime.strptime(order_date_str, '%Y-%m-%d').date()
            except:
                order_date = timezone.now().date()
        else:
            order_date = timezone.now().date()
        
        # Проверяем, нет ли уже заказа на эту дату
        # existing_order = Order.objects.filter(employee=employee, order_date=order_date).first()
        # if existing_order:
        #     return JsonResponse({'success': False, 'error': f'У вас уже есть заказ на {order_date.strftime("%d.%m.%Y")}'}, status=400)
        
        # Получаем группу
        group = None
        if group_id:
            group = get_object_or_404(MenuItemGroup, id=group_id)
            if not group.can_select(order_date):
                return JsonResponse({'success': False, 'error': 'Выбор из этой группы закрыт'}, status=400)
        
        # Подсчитываем сумму и проверяем доступность товаров
        total_amount = Decimal('0')
        order_items_data = []
        
        for item_data in items:
            menu_item_id = item_data.get('menu_item_id')
            quantity = item_data.get('quantity', 1)
            
            menu_item = get_object_or_404(MenuItem, id=menu_item_id, is_available=True)
            
            if not menu_item.restaurant.is_available_today():
                return JsonResponse({'success': False, 'error': f'Блюдо "{menu_item.name}" больше не доступно'}, status=400)
            
            if menu_item.group and not menu_item.group.can_select(order_date):
                return JsonResponse({'success': False, 'error': f'Группа "{menu_item.group.name}" закрыта для выбора'}, status=400)
            
            item_total = (menu_item.price or Decimal('0')) * quantity
            total_amount += item_total
            
            order_items_data.append({
                'menu_item': menu_item,
                'quantity': quantity,
                'price': menu_item.price or Decimal('0'),
            })
        
        # Списание: сначала баланс компании, затем личный баланс сотрудника.
        company_part = min(employee.balance, total_amount) if employee.balance > 0 else Decimal('0')
        personal_part = total_amount - company_part
        personal_after = employee.personal_balance - personal_part

        # В минус уходим только личным балансом и только до лимита.
        if personal_after < employee.min_balance_limit:
            return JsonResponse({
                'success': False,
                'error': f'Недостаточно средств. Лимит: {employee.min_balance_limit}₽',
                'balance': float(employee.balance),
                'company_balance': float(employee.balance),
                'personal_balance': float(employee.personal_balance),
                'required': float(total_amount),
            }, status=400)
        
        # Создаем заказ
        with transaction.atomic():
            order = Order.objects.create(
                employee=employee,
                group=group,
                order_date=order_date,
                total_amount=total_amount,
                amount_paid_by_employee=personal_part,
                status='reserved'
            )
            
            for item_data in order_items_data:
                OrderItem.objects.create(
                    order=order,
                    menu_item=item_data['menu_item'],
                    quantity=item_data['quantity'],
                    price=item_data['price']
                )
            
            # Резервируем средства: фирма -> личный
            employee.balance -= company_part
            employee.personal_balance = personal_after
            employee.save()
            
            # Создаем запись о резервировании
            BalanceTransaction.objects.create(
                employee=employee,
                transaction_type='deduction',
                amount=-total_amount,
                balance_after=employee.balance,
                order=order,
                comment=(
                    f'Резервирование средств за заказ на {order_date.strftime("%d.%m.%Y")} '
                    f'(компания: {company_part}₽, личный: {personal_part}₽)'
                )
            )
        
        return JsonResponse({
            'success': True,
            'order': {
                'id': order.id,
                'total_amount': float(total_amount),
                'balance_after': float(employee.balance),
                'company_balance_after': float(employee.balance),
                'personal_balance_after': float(employee.personal_balance),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_employee_info(request, employee_id):
    """Получение информации о сотруднике"""
    try:
        employee = get_object_or_404(Employee, id=employee_id)
        
        # Получаем последние заказы
        orders = Order.objects.filter(employee=employee).order_by('-order_date')[:10]
        orders_data = []
        for order in orders:
            orders_data.append({
                'id': order.id,
                'order_date': order.order_date.isoformat(),
                'total_amount': float(order.total_amount),
                'status': order.status,
                'status_display': order.get_status_display(),
                'group': order.group.name if order.group else None,
            })
        
        return JsonResponse({
            'success': True,
            'employee': {
                'id': employee.id,
                'name': employee.name,
                'email': employee.email,
                'balance': float(employee.balance),
                'company_balance': float(employee.balance),
                'personal_balance': float(employee.personal_balance),
                'telegram_linked': bool(employee.telegram_id),
                'telegram_id': employee.telegram_id or '',
                'min_balance_limit': float(employee.min_balance_limit),
                'daily_balance_amount': float(employee.daily_balance_amount),
                'can_make_order': employee.can_make_order(),
                'is_approved': employee.is_approved,
                'is_active': employee.is_active,
                'avatar_url': employee.avatar.url if employee.avatar else None,
            },
            'orders': orders_data,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_order_details(request, order_id):
    """Получение деталей заказа"""
    try:
        order = get_object_or_404(Order, id=order_id)
        
        items = []
        for item in order.items.all():
            items.append({
                'name': item.menu_item.name,
                'quantity': item.quantity,
                'price': float(item.price),
                'subtotal': float(item.subtotal),
            })
        
        return JsonResponse({
            'success': True,
            'order': {
                'id': order.id,
                'order_date': order.order_date.isoformat(),
                'total_amount': float(order.total_amount),
                'status': order.status,
                'status_display': order.get_status_display(),
                'group': order.group.name if order.group else None,
                'items': items,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_week_menu(request):
    """Получение меню на неделю (7 дней вперед)"""
    try:
        today = timezone.now().date()
        week_menu = {}
        
        # Получаем меню на каждый день недели
        for i in range(7):
            date = today + timezone.timedelta(days=i)
            date_str = date.isoformat()
            
            # Получаем доступные группы товаров на эту дату
            groups = MenuItemGroup.objects.filter(
                is_active=True,
                period_start__lte=date,
                period_end__gte=date,
                # is_selection_closed=False  # Убрали фильтр, чтобы показывать закрытые группы
            ).prefetch_related('items__restaurant', 'items__images', 'items__category')
            
            # Собираем все товары из всех активных групп
            items_by_category = {}
            other_items = []
            seen_item_ids = set()
            
            for group in groups:
                for item in group.items.filter(is_available=True):
                    if item.id in seen_item_ids:
                        continue
                    seen_item_ids.add(item.id)
                    
                    primary_image = item.get_primary_image()
                    image_url = None
                    if primary_image and primary_image.image:
                        try:
                            image_url = primary_image.image.url
                        except Exception:
                            image_url = None
                    if not image_url and getattr(item, 'image_url', None):
                        image_url = item.image_url
                    item_dict = {
                        'id': item.id,
                        'name': item.name,
                        'description': item.description,
                        'price': float(item.price) if item.price else 0,
                        'restaurant': item.restaurant.name,
                        'image': image_url,
                        'weight': item.weight or '',
                        'calories': item.calories,
                        'protein': float(item.protein) if item.protein else None,
                        'fat': float(item.fat) if item.fat else None,
                        'carbohydrates': float(item.carbohydrates) if item.carbohydrates else None,
                        'composition': item.composition or '',
                        'source_url': item.source_url or '',
                        'is_selection_closed': group.is_selection_closed,
                    }
                    
                    if item.category:
                        if item.category not in items_by_category:
                            items_by_category[item.category] = []
                        items_by_category[item.category].append(item_dict)
                    else:
                        other_items.append(item_dict)
            
            # Формируем список категорий
            menu_data = []
            
            # Сортируем категории
            sorted_cats = sorted(items_by_category.keys(), key=lambda c: (c.order, c.name))
            
            for cat in sorted_cats:
                menu_data.append({
                    'name': cat.name,
                    'items': items_by_category[cat]
                })
            
            # Добавляем "Остальное" в конец
            if other_items:
                menu_data.append({
                    'name': 'Остальное',
                    'items': other_items
                })
            
            week_menu[date_str] = menu_data
        
        return JsonResponse({'success': True, 'week_menu': week_menu})
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': error_msg}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_employee_orders(request, employee_id):
    """Получение всех заказов сотрудника"""
    try:
        employee = get_object_or_404(Employee, id=employee_id)
        
        # Получаем заказы (прошлые 7 дней и будущие 30 дней)
        today = timezone.now().date()
        start_date = today - timezone.timedelta(days=7)
        end_date = today + timezone.timedelta(days=30)
        
        orders = Order.objects.filter(
            employee=employee,
            order_date__gte=start_date,
            order_date__lte=end_date
        ).order_by('order_date', 'created_at').prefetch_related('items__menu_item', 'group')
        
        orders_data = {}
        for order in orders:
            date_str = order.order_date.isoformat()
            items = []
            for item in order.items.all():
                items.append({
                    'name': item.menu_item.name,
                    'quantity': item.quantity,
                    'price': float(item.price),
                    'subtotal': float(item.subtotal),
                })
            
            order_info = {
                'id': order.id,
                'total_amount': float(order.total_amount),
                'status': order.status,
                'status_display': order.get_status_display(),
                'group': order.group.name if order.group else None,
                'items': items,
                'amount_paid_by_employee': float(order.amount_paid_by_employee or 0),
            }
            
            if date_str not in orders_data:
                orders_data[date_str] = []
            orders_data[date_str].append(order_info)
        
        return JsonResponse({'success': True, 'orders': orders_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def report_item(request):
    """Отправка уведомления администратору о проблеме с товаром"""
    try:
        data = json.loads(request.body)
        employee_id = data.get('employee_id')
        menu_item_id = data.get('menu_item_id')
        
        if not employee_id or not menu_item_id:
            return JsonResponse({'success': False, 'error': 'Необходимы employee_id и menu_item_id'}, status=400)
        
        # Проверяем существование сотрудника и товара
        employee = get_object_or_404(Employee, id=employee_id)
        menu_item = get_object_or_404(MenuItem, id=menu_item_id)
        
        # Отправляем уведомление асинхронно
        from orders.tasks import send_admin_notification
        send_admin_notification.delay(
            employee_id=employee.id,
            menu_item_id=menu_item.id,
            message_text=f"Товар с нулевой ценой требует внимания"
        )
        
        return JsonResponse({'success': True, 'message': 'Уведомление отправлено администратору'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def cancel_order(request):
    """Отмена заказа пользователем"""
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        employee_id = data.get('employee_id')
        
        if not order_id or not employee_id:
            return JsonResponse({'success': False, 'error': 'order_id и employee_id обязательны'}, status=400)
            
        order = get_object_or_404(Order, id=order_id, employee_id=employee_id)
        
        # Можно отменять только зарезервированные заказы
        if order.status != 'reserved':
            return JsonResponse({'success': False, 'error': f'Заказ в статусе "{order.get_status_display()}" нельзя отменить'}, status=400)
            
        with transaction.atomic():
            # Возвращаем средства в те же кошельки, из которых списали
            employee = order.employee
            personal_part = order.amount_paid_by_employee or Decimal('0')
            company_part = order.total_amount - personal_part
            employee.balance += company_part
            employee.personal_balance += personal_part
            employee.save()
            
            # Меняем статус заказа
            order.status = 'cancelled'
            order.save()
            
            # Создаем запись о возврате
            BalanceTransaction.objects.create(
                employee=employee,
                transaction_type='refund',
                amount=order.total_amount,
                balance_after=employee.balance,
                order=order,
                comment=(
                    f'Возврат средств за отмену заказа #{order.id} '
                    f'(компания: {company_part}₽, личный: {personal_part}₽)'
                )
            )
            
        return JsonResponse({
            'success': True,
            'message': 'Заказ успешно отменен',
            'new_balance': float(employee.balance),
            'company_balance': float(employee.balance),
            'personal_balance': float(employee.personal_balance),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def set_order_paid_by_me(request):
    """Установка суммы «заплатил сам» по заказу (в ЛК сотрудника)."""
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        employee_id = data.get('employee_id')
        amount = data.get('amount_paid_by_employee')
        if order_id is None or not employee_id:
            return JsonResponse({'success': False, 'error': 'Нужны order_id и employee_id'}, status=400)
        order = get_object_or_404(Order, id=order_id, employee_id=employee_id)
        try:
            amount = Decimal(str(amount)) if amount is not None and str(amount).strip() != '' else Decimal('0')
        except (ValueError, TypeError):
            amount = Decimal('0')
        if amount < 0:
            amount = Decimal('0')
        if amount > order.total_amount:
            return JsonResponse({'success': False, 'error': f'Сумма не может быть больше {order.total_amount}₽'}, status=400)
        order.amount_paid_by_employee = amount
        order.save()
        return JsonResponse({
            'success': True,
            'new_balance': float(order.employee.balance),
            'company_balance': float(order.employee.balance),
            'personal_balance': float(order.employee.personal_balance),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_settings(request):
    """Получение публичных настроек системы"""
    try:
        settings_objs = Settings.objects.all()
        settings_data = {s.key: s.value for s in settings_objs}
        
        # Добавляем стандартные значения если ключей нет
        if 'payment_details' not in settings_data:
            settings_data['payment_details'] = 'Реквизиты для пополнения не указаны.'
            
        return JsonResponse({'success': True, 'settings': settings_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _send_telegram_message(chat_id: str, text: str) -> bool:
    """Отправка сообщения в Telegram chat_id через Bot API."""
    token = (settings.TELEGRAM_BOT_TOKEN or '').strip()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            _ = resp.read()
        return True
    except Exception:
        return False


@csrf_exempt
@require_http_methods(["POST"])
def link_telegram(request):
    """Привязка Telegram к текущему авторизованному профилю."""
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'error': 'Нужна авторизация'}, status=401)

        try:
            employee = request.user.employee
        except Employee.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Профиль сотрудника не найден'}, status=404)

        data = json.loads(request.body or "{}")
        telegram_id = str(data.get('telegram_id') or '').strip()
        telegram_username = str(data.get('telegram_username') or '').strip()

        if not telegram_id.isdigit():
            return JsonResponse({'success': False, 'error': 'Некорректный telegram_id'}, status=400)

        other = Employee.objects.filter(telegram_id=telegram_id).exclude(id=employee.id).first()
        if other:
            return JsonResponse({
                'success': False,
                'error': 'Этот Telegram уже привязан к другому сотруднику'
            }, status=409)

        employee.telegram_id = telegram_id
        employee.save(update_fields=['telegram_id'])

        human_name = employee.name or employee.email or 'сотрудник'
        username_text = f" (@{telegram_username})" if telegram_username else ""
        _send_telegram_message(
            telegram_id,
            (
                f"✅ Профиль привязан{username_text}.\n"
                f"Сотрудник: {human_name}\n"
                f"Баланс компании: {employee.balance}₽\n"
                f"Личный баланс: {employee.personal_balance}₽\n\n"
                "Доступные команды: /start, /menu, /balance, /orders, /orders_today, /group_menu"
            )
        )

        return JsonResponse({
            'success': True,
            'telegram_linked': True,
            'telegram_id': employee.telegram_id,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _basic_auth_ok(request) -> bool:
    """Проверка Basic Auth для интеграционных API."""
    expected_user = (getattr(settings, "INTEGRATION_API_BASIC_USER", "") or "").strip()
    expected_pass = (getattr(settings, "INTEGRATION_API_BASIC_PASSWORD", "") or "").strip()
    if not expected_user or not expected_pass:
        return False

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return False
    token = auth_header[6:].strip()
    try:
        decoded = base64.b64decode(token).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    if ":" not in decoded:
        return False
    user, password = decoded.split(":", 1)
    return hmac.compare_digest(user, expected_user) and hmac.compare_digest(password, expected_pass)


def _unauthorized_response():
    resp = JsonResponse({"success": False, "error": "Unauthorized"}, status=401)
    resp["WWW-Authenticate"] = 'Basic realm="integration-api"'
    return resp


@csrf_exempt
@require_http_methods(["GET"])
def api_available_menu_day(request):
    """
    Интеграционный API: получить доступные блюда на дату.
    Basic Auth обязателен.
    """
    if not _basic_auth_ok(request):
        return _unauthorized_response()

    date_str = (request.GET.get("date") or "").strip()
    if date_str:
        try:
            target_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"success": False, "error": "Неверный формат date. Используйте YYYY-MM-DD"}, status=400)
    else:
        target_date = timezone.localdate()

    groups = (
        MenuItemGroup.objects.filter(
            is_active=True,
            period_start__lte=target_date,
            period_end__gte=target_date,
        )
        .prefetch_related("items__restaurant", "items__images")
        .order_by("order", "name")
    )

    seen = set()
    items = []
    for group in groups:
        for item in group.items.filter(is_available=True):
            if item.id in seen:
                continue
            seen.add(item.id)

            # Проверяем доступность ресторана на target_date
            rest = item.restaurant
            if not rest.is_active:
                continue
            if rest.period_start and target_date < rest.period_start:
                continue
            if rest.period_end and target_date > rest.period_end:
                continue

            primary_image = item.get_primary_image()
            image_url = None
            image_source = "none"
            if primary_image and primary_image.image:
                try:
                    image_url = primary_image.image.url
                    image_source = "uploaded"
                except Exception:
                    image_url = None
            if not image_url and item.image_url:
                image_url = item.image_url
                image_source = "image_url"
            if image_url and image_url.startswith("/"):
                image_url = request.build_absolute_uri(image_url)

            items.append({
                "id": item.id,
                "name": item.name,
                "restaurant": rest.name,
                "group": group.name,
                "price": float(item.price) if item.price is not None else 0,
                "description": item.description or "",
                "image_url": image_url or "",
                "image_source": image_source,
            })

    return JsonResponse({
        "success": True,
        "date": target_date.isoformat(),
        "count": len(items),
        "items": items,
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_upload_item_images(request):
    """
    Интеграционный API: массовое обновление image_url у блюд.
    Basic Auth обязателен.

    Формат JSON:
    {
      "date": "2026-03-20",           // optional, ограничение по меню даты
      "restaurant": "ВкусВилл",       // optional default restaurant for rows
      "dry_run": false,               // optional
      "items": [
        {"id": 123, "image_url": "https://..."},
        {"name": "Борщ", "restaurant": "ВкусВилл", "image_url": "https://..."}
      ]
    }
    """
    if not _basic_auth_ok(request):
        return _unauthorized_response()

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Некорректный JSON"}, status=400)

    rows = data.get("items", [])
    if not isinstance(rows, list) or not rows:
        return JsonResponse({"success": False, "error": "Поле items должно быть непустым массивом"}, status=400)

    default_restaurant = (data.get("restaurant") or "").strip()
    dry_run = bool(data.get("dry_run", False))
    date_str = (data.get("date") or "").strip()
    target_date = None
    if date_str:
        try:
            target_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"success": False, "error": "Неверный формат date. Используйте YYYY-MM-DD"}, status=400)

    updated = 0
    matched = 0
    not_found = 0
    errors = []
    not_found_rows = []

    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append({"row": idx, "error": "Элемент items должен быть объектом"})
            continue
        image_url = (row.get("image_url") or "").strip()
        if not image_url.startswith("http://") and not image_url.startswith("https://"):
            errors.append({"row": idx, "error": "image_url должен начинаться с http:// или https://"})
            continue

        menu_items_qs = None
        item_id = row.get("id")
        if item_id:
            menu_items_qs = MenuItem.objects.filter(id=item_id)
        else:
            name = (row.get("name") or "").strip()
            if not name:
                errors.append({"row": idx, "error": "Нужен id или name"})
                continue
            row_restaurant = (row.get("restaurant") or default_restaurant).strip()
            menu_items_qs = MenuItem.objects.filter(name=name)
            if row_restaurant:
                menu_items_qs = menu_items_qs.filter(restaurant__name=row_restaurant)

        if target_date:
            menu_items_qs = menu_items_qs.filter(
                group__is_active=True,
                group__period_start__lte=target_date,
                group__period_end__gte=target_date,
            )

        menu_items = list(menu_items_qs[:500])
        if not menu_items:
            not_found += 1
            not_found_rows.append({"row": idx, "id": item_id, "name": row.get("name", "")})
            continue

        matched += len(menu_items)
        if not dry_run:
            for menu_item in menu_items:
                menu_item.image_url = image_url
                menu_item.save(update_fields=["image_url"])
        updated += len(menu_items)

    result = {
        "success": True,
        "dry_run": dry_run,
        "updated": updated,
        "matched": matched,
        "not_found": not_found,
        "errors_count": len(errors),
        "errors": errors[:100],
        "not_found_rows": not_found_rows[:200],
    }
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(["POST"])
def upload_avatar(request):
    """Загрузка аватара сотрудника."""
    try:
        employee = None
        if request.user.is_authenticated:
            try:
                employee = request.user.employee
            except Employee.DoesNotExist:
                pass
        if not employee:
            eid = request.POST.get('employee_id') or request.GET.get('employee_id')
            if eid:
                try:
                    employee = Employee.objects.get(id=eid)
                except Employee.DoesNotExist:
                    pass
        if not employee:
            return JsonResponse({'success': False, 'error': 'Сотрудник не найден'}, status=404)

        f = request.FILES.get('avatar')
        if not f:
            return JsonResponse({'success': False, 'error': 'Файл не передан'}, status=400)

        # Keep old avatar if present
        if employee.avatar:
            try:
                employee.avatar.delete(save=False)
            except Exception:
                pass

        employee.avatar = f
        employee.save(update_fields=['avatar'])
        return JsonResponse({'success': True, 'avatar_url': employee.avatar.url})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def push_send_test(request):
    """Отправить тестовый push всем подписчикам (для отладки)."""
    webhook_secret = getattr(settings, 'SUPABASE_WEBHOOK_SECRET', '')
    if webhook_secret:
        auth_header = request.headers.get('Authorization', '')
        if auth_header != f'Bearer {webhook_secret}':
            return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        from pywebpush import webpush, WebPushException
        private_key = settings.VAPID_PRIVATE_KEY
        public_key = settings.VAPID_PUBLIC_KEY
        claims_email = settings.VAPID_CLAIMS_EMAIL
        if not private_key:
            return JsonResponse({'success': False, 'error': 'VAPID not configured'})

        subscriptions = PushSubscription.objects.all()
        if not subscriptions.exists():
            return JsonResponse({'success': True, 'sent': 0, 'note': 'No subscribers'})

        payload = json.dumps({'title': 'Тест уведомлений 🔔', 'body': 'Push-уведомления работают!', 'sender': '', 'recipient': ''})
        sent, failed = 0, []
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={'endpoint': sub.endpoint, 'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
                    data=payload,
                    vapid_private_key=private_key,
                    vapid_claims={'sub': f'mailto:{claims_email}'},
                )
                sent += 1
            except WebPushException as e:
                status = e.response.status_code if e.response else 0
                if status in (404, 410):
                    sub.delete()
                else:
                    failed.append({'employee': sub.employee_name, 'error': str(e)})

        return JsonResponse({'success': True, 'sent': sent, 'failed': len(failed), 'details': failed})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
