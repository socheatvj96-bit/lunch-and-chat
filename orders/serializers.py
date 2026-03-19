from rest_framework import serializers
from .models import Employee, Restaurant, MenuItem, Order, OrderItem


class MenuItemSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    
    class Meta:
        model = MenuItem
        fields = ['id', 'restaurant', 'restaurant_name', 'name', 'description', 'price', 'is_available']


class RestaurantSerializer(serializers.ModelSerializer):
    menu_items = MenuItemSerializer(many=True, read_only=True)
    is_available_today = serializers.SerializerMethodField()
    
    class Meta:
        model = Restaurant
        fields = ['id', 'name', 'is_active', 'period_start', 'period_end', 'menu_items', 'is_available_today']
    
    def get_is_available_today(self, obj):
        return obj.is_available_today()


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ['id', 'name', 'telegram_id', 'email', 'balance', 'personal_balance', 'is_active']


class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)
    subtotal = serializers.ReadOnlyField()
    
    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item', 'menu_item_name', 'quantity', 'price', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    
    class Meta:
        model = Order
        fields = ['id', 'employee', 'employee_name', 'order_date', 'total_amount', 'status', 'items', 'created_at']


class CreateOrderSerializer(serializers.Serializer):
    """Сериализатор для создания заказа"""
    menu_items = serializers.ListField(
        child=serializers.DictField(
            child=serializers.IntegerField()
        )
    )
    
    def validate_menu_items(self, value):
        """Проверка формата: [{'menu_item_id': 1, 'quantity': 2}, ...]"""
        for item in value:
            if 'menu_item_id' not in item or 'quantity' not in item:
                raise serializers.ValidationError("Каждый элемент должен содержать 'menu_item_id' и 'quantity'")
            if item['quantity'] < 1:
                raise serializers.ValidationError("Количество должно быть больше 0")
        return value

