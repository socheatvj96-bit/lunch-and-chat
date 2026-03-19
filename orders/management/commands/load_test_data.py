from django.core.management.base import BaseCommand
from orders.models import Employee, Restaurant, MenuItem
from decimal import Decimal
from datetime import date, timedelta


class Command(BaseCommand):
    help = 'Загрузка тестовых данных'

    def handle(self, *args, **options):
        self.stdout.write('Создание тестовых данных...')

        # Создание сотрудников
        employees_data = [
            {'name': 'Иван Иванов', 'telegram_id': '123456789', 'email': 'ivan@example.com', 'balance': 500},
            {'name': 'Мария Петрова', 'telegram_id': '987654321', 'email': 'maria@example.com', 'balance': 300},
            {'name': 'Алексей Сидоров', 'telegram_id': None, 'email': 'alex@example.com', 'balance': 450},
            {'name': 'Елена Козлова', 'telegram_id': '555666777', 'email': 'elena@example.com', 'balance': 200},
            {'name': 'Дмитрий Волков', 'telegram_id': None, 'email': 'dmitry@example.com', 'balance': 600},
        ]

        employees = []
        for emp_data in employees_data:
            employee, created = Employee.objects.get_or_create(
                email=emp_data['email'],
                defaults={
                    'name': emp_data['name'],
                    'telegram_id': emp_data['telegram_id'],
                    'balance': emp_data['balance'],
                    'is_active': True
                }
            )
            if not created:
                employee.name = emp_data['name']
                employee.telegram_id = emp_data['telegram_id']
                employee.balance = emp_data['balance']
                employee.save()
            employees.append(employee)
            self.stdout.write(f'  Создан сотрудник: {employee.name}')

        # Создание ресторанов
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        next_week_start = week_end + timedelta(days=1)
        next_week_end = next_week_start + timedelta(days=6)

        restaurants_data = [
            {
                'name': 'ВкусВилл',
                'is_active': True,
                'period_start': week_start,
                'period_end': week_end,
            },
            {
                'name': 'Теремок',
                'is_active': True,
                'period_start': next_week_start,
                'period_end': next_week_end,
            },
            {
                'name': 'Якитория',
                'is_active': True,
                'period_start': None,
                'period_end': None,
            },
        ]

        restaurants = []
        for rest_data in restaurants_data:
            restaurant, created = Restaurant.objects.get_or_create(
                name=rest_data['name'],
                defaults=rest_data
            )
            if not created:
                restaurant.is_active = rest_data['is_active']
                restaurant.period_start = rest_data['period_start']
                restaurant.period_end = rest_data['period_end']
                restaurant.save()
            restaurants.append(restaurant)
            self.stdout.write(f'  Создан ресторан: {restaurant.name}')

        # Создание блюд для ВкусВилл
        vkusvill = restaurants[0]
        vkusvill_items = [
            {'name': 'Салат Цезарь', 'description': 'Курица, салат, сухарики, соус', 'price': 250},
            {'name': 'Борщ с мясом', 'description': 'Традиционный борщ с говядиной', 'price': 180},
            {'name': 'Котлета по-киевски', 'description': 'Куриная котлета с маслом', 'price': 320},
            {'name': 'Плов', 'description': 'Узбекский плов с бараниной', 'price': 280},
            {'name': 'Пицца Маргарита', 'description': 'Классическая пицца', 'price': 350},
        ]

        for item_data in vkusvill_items:
            menu_item, created = MenuItem.objects.get_or_create(
                restaurant=vkusvill,
                name=item_data['name'],
                defaults={
                    'description': item_data['description'],
                    'price': Decimal(str(item_data['price'])),
                    'is_available': True
                }
            )
            if not created:
                menu_item.description = item_data['description']
                menu_item.price = Decimal(str(item_data['price']))
                menu_item.is_available = True
                menu_item.save()
            self.stdout.write(f'  Создано блюдо: {menu_item.name} ({vkusvill.name})')

        # Создание блюд для Теремок
        teremok = restaurants[1]
        teremok_items = [
            {'name': 'Блины с мясом', 'description': 'Тонкие блины с мясной начинкой', 'price': 220},
            {'name': 'Борщ', 'description': 'Классический борщ', 'price': 190},
            {'name': 'Пельмени', 'description': 'Домашние пельмени со сметаной', 'price': 240},
            {'name': 'Оливье', 'description': 'Классический салат', 'price': 200},
        ]

        for item_data in teremok_items:
            menu_item, created = MenuItem.objects.get_or_create(
                restaurant=teremok,
                name=item_data['name'],
                defaults={
                    'description': item_data['description'],
                    'price': Decimal(str(item_data['price'])),
                    'is_available': True
                }
            )
            if not created:
                menu_item.description = item_data['description']
                menu_item.price = Decimal(str(item_data['price']))
                menu_item.is_available = True
                menu_item.save()
            self.stdout.write(f'  Создано блюдо: {menu_item.name} ({teremok.name})')

        # Создание блюд для Якитория
        yakitoria = restaurants[2]
        yakitoria_items = [
            {'name': 'Ролл Филадельфия', 'description': 'Лосось, сыр, огурец', 'price': 380},
            {'name': 'Ролл Калифорния', 'description': 'Краб, авокадо, огурец', 'price': 320},
            {'name': 'Суши сет', 'description': 'Ассорти из суши', 'price': 450},
            {'name': 'Лапша Удон', 'description': 'Горячая лапша с курицей', 'price': 280},
        ]

        for item_data in yakitoria_items:
            menu_item, created = MenuItem.objects.get_or_create(
                restaurant=yakitoria,
                name=item_data['name'],
                defaults={
                    'description': item_data['description'],
                    'price': Decimal(str(item_data['price'])),
                    'is_available': True
                }
            )
            if not created:
                menu_item.description = item_data['description']
                menu_item.price = Decimal(str(item_data['price']))
                menu_item.is_available = True
                menu_item.save()
            self.stdout.write(f'  Создано блюдо: {menu_item.name} ({yakitoria.name})')

        self.stdout.write(self.style.SUCCESS('\nТестовые данные успешно загружены!'))
        self.stdout.write(f'\nСоздано:')
        self.stdout.write(f'  - Сотрудников: {len(employees)}')
        self.stdout.write(f'  - Ресторанов: {len(restaurants)}')
        self.stdout.write(f'  - Блюд: {MenuItem.objects.count()}')
        self.stdout.write(f'\nДля доступа к админ панели создайте суперпользователя:')
        self.stdout.write(f'  python manage.py createsuperuser')

