import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lunch_order.settings')
django.setup()

from orders.models import ProductCategory

def update_order():
    # Define priority: lower is first
    priorities = {
        'Первое': 10,
        'Второе': 20,
        'Салаты': 25, 
        'Завтраки': 28,
        'Напитки': 30,
        'Десерты': 40,
        'Остальное': 100
    }

    for name, order in priorities.items():
        try:
            category = ProductCategory.objects.get(name=name)
            category.order = order
            category.save()
            print(f"Updated '{name}' order to {order}")
        except ProductCategory.DoesNotExist:
            print(f"Category '{name}' not found")

if __name__ == '__main__':
    update_order()
