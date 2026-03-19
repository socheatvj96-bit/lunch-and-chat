from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from .models import Employee, Restaurant, MenuItem, Order, OrderItem, BalanceTransaction, MenuItemGroup
from .serializers import (
    EmployeeSerializer, RestaurantSerializer, MenuItemSerializer,
    OrderSerializer, CreateOrderSerializer
)


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    
    @action(detail=False, methods=['get'])
    def by_telegram(self, request):
        """Получить сотрудника по Telegram ID"""
        telegram_id = request.query_params.get('telegram_id')
        if not telegram_id:
            return Response({'error': 'telegram_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            employee = Employee.objects.get(telegram_id=telegram_id)
            serializer = self.get_serializer(employee)
            return Response(serializer.data)
        except Employee.DoesNotExist:
            return Response({'error': 'Employee not found'}, status=status.HTTP_404_NOT_FOUND)


class RestaurantViewSet(viewsets.ModelViewSet):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer
    
    @action(detail=False, methods=['get'])
    def available_today(self, request):
        """Получить доступные рестораны на сегодня"""
        restaurants = [r for r in self.queryset if r.is_available_today()]
        serializer = self.get_serializer(restaurants, many=True)
        return Response(serializer.data)


class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    
    @action(detail=False, methods=['get'])
    def available_today(self, request):
        """Получить доступные блюда на сегодня"""
        from django.utils import timezone
        today = timezone.now().date()
        
        # Получаем доступные рестораны
        available_restaurants = [r.id for r in Restaurant.objects.all() if r.is_available_today()]
        
        # Получаем блюда из доступных ресторанов
        items = MenuItem.objects.filter(
            restaurant_id__in=available_restaurants,
            is_available=True
        )
        
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        employee_id = self.request.query_params.get('employee_id')
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        return queryset
    
    @action(detail=False, methods=['post'])
    def create_order(self, request):
        """Создание заказа"""
        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        employee_id = request.data.get('employee_id')
        if not employee_id:
            return Response({'error': 'employee_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return Response({'error': 'Employee not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Проверяем возможность сделать заказ
        if not employee.can_make_order():
            if not employee.is_approved:
                return Response({'error': 'Учётная запись не подтверждена'}, status=status.HTTP_403_FORBIDDEN)
            if not employee.is_active:
                return Response({'error': 'Учётная запись заблокирована'}, status=status.HTTP_403_FORBIDDEN)
            if employee.personal_balance <= employee.min_balance_limit:
                return Response({
                    'error': f'Баланс достиг минимального лимита ({employee.min_balance_limit}₽). Пополните баланс для возможности делать заказы.',
                    'balance': float(employee.balance),
                    'company_balance': float(employee.balance),
                    'personal_balance': float(employee.personal_balance),
                    'min_balance_limit': float(employee.min_balance_limit)
                }, status=status.HTTP_403_FORBIDDEN)
        
        today = timezone.now().date()
        
        # Проверяем, нет ли уже заказа на сегодня
        existing_order = Order.objects.filter(employee=employee, order_date=today).first()
        if existing_order:
            return Response({'error': 'Order for today already exists'}, status=status.HTTP_400_BAD_REQUEST)
        
        menu_items_data = serializer.validated_data['menu_items']
        total_amount = 0
        order_items = []
        
        # Проверяем доступность блюд и считаем сумму
        for item_data in menu_items_data:
            menu_item_id = item_data['menu_item_id']
            quantity = item_data['quantity']
            
            try:
                menu_item = MenuItem.objects.get(id=menu_item_id, is_available=True)
            except MenuItem.DoesNotExist:
                return Response({'error': f'MenuItem {menu_item_id} not found or not available'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Проверяем доступность ресторана
            if not menu_item.restaurant.is_available_today():
                return Response({'error': f'Restaurant {menu_item.restaurant.name} is not available today'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Проверяем, что группа товаров не закрыта для выбора
            if menu_item.group and not menu_item.group.can_select():
                if menu_item.group.is_selection_closed:
                    return Response({'error': f'Выбор из группы "{menu_item.group.name}" закрыт'}, 
                                  status=status.HTTP_400_BAD_REQUEST)
                if not menu_item.group.is_visible_today():
                    return Response({'error': f'Группа "{menu_item.group.name}" не доступна на сегодня'}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            
            item_total = menu_item.price * quantity
            total_amount += item_total
            
            order_items.append({
                'menu_item': menu_item,
                'quantity': quantity,
                'price': menu_item.price
            })
        
        # Списание: сначала баланс компании, затем личный баланс сотрудника.
        company_part = min(employee.balance, total_amount) if employee.balance > 0 else Decimal('0')
        personal_part = total_amount - company_part
        personal_after = employee.personal_balance - personal_part

        if personal_after < employee.min_balance_limit:
            return Response({
                'error': 'Insufficient balance',
                'balance': float(employee.balance),
                'company_balance': float(employee.balance),
                'personal_balance': float(employee.personal_balance),
                'required': float(total_amount)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Определяем группу товаров (берем из первого товара)
        group = order_items[0]['menu_item'].group if order_items else None
        
        # Создаем заказ со статусом 'reserved' (резервируем средства)
        with transaction.atomic():
            old_balance = employee.balance
            order = Order.objects.create(
                employee=employee,
                group=group,
                order_date=today,
                total_amount=total_amount,
                amount_paid_by_employee=personal_part,
                status='reserved'  # Резервируем, а не списываем сразу
            )
            
            for item_data in order_items:
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
                    f'Резервирование средств за заказ от {today} '
                    f'(группа: {group.name if group else "без группы"}, '
                    f'компания: {company_part}₽, личный: {personal_part}₽)'
                )
            )
        
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Отмена заказа"""
        order = self.get_object()
        
        if order.status in ['completed', 'cancelled']:
            return Response({'error': 'Order cannot be cancelled'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Возвращаем средства в те же кошельки, из которых списали
            personal_part = order.amount_paid_by_employee or Decimal('0')
            company_part = order.total_amount - personal_part
            order.employee.balance += company_part
            order.employee.personal_balance += personal_part
            order.employee.save()
            
            order.status = 'cancelled'
            order.save()
        
        serializer = OrderSerializer(order)
        return Response(serializer.data)

