from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from decimal import Decimal


class Employee(models.Model):
    """Сотрудник"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee', null=True, blank=True, verbose_name='Пользователь Django')
    telegram_id = models.CharField(max_length=100, unique=True, null=True, blank=True, verbose_name='Telegram ID')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Баланс компании')
    personal_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Личный баланс сотрудника')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    is_approved = models.BooleanField(default=False, verbose_name='Учётная запись подтверждена')
    min_balance_limit = models.DecimalField(max_digits=10, decimal_places=2, default=-1000, verbose_name='Минимальный баланс (блокировка)')
    daily_balance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=150, verbose_name='Начисление в рабочий день')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name='Аватар')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    
    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'
        ordering = ['user__username']
    
    def __str__(self):
        if self.user:
            return self.user.get_full_name() or self.user.username
        return f"Сотрудник #{self.id}"
    
    @property
    def name(self):
        """Имя сотрудника из User"""
        if self.user:
            return self.user.get_full_name() or self.user.username
        return f"Сотрудник #{self.id}"
    
    @property
    def email(self):
        """Email сотрудника из User"""
        if self.user:
            return self.user.email
        return ""
    
    def save(self, *args, **kwargs):
        # Автоматическая блокировка при достижении минимального баланса
        if self.personal_balance <= self.min_balance_limit:
            self.is_active = False
        super().save(*args, **kwargs)
    
    def can_make_order(self):
        """Проверка возможности сделать заказ"""
        return self.is_active and self.is_approved and self.personal_balance > self.min_balance_limit


class Restaurant(models.Model):
    """Ресторан"""
    name = models.CharField(max_length=200, verbose_name='Название')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    period_start = models.DateField(null=True, blank=True, verbose_name='Начало периода')
    period_end = models.DateField(null=True, blank=True, verbose_name='Конец периода')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    
    class Meta:
        verbose_name = 'Ресторан'
        verbose_name_plural = 'Рестораны'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def is_available_today(self):
        """Проверка доступности ресторана сегодня"""
        from django.utils import timezone
        today = timezone.now().date()
        
        if not self.is_active:
            return False
        
        if self.period_start and today < self.period_start:
            return False
        
        if self.period_end and today > self.period_end:
            return False
        
        return True


class MenuItemGroup(models.Model):
    """Группа товаров (категория)"""
    name = models.CharField(max_length=200, verbose_name='Название группы')
    description = models.TextField(blank=True, verbose_name='Описание')
    order = models.IntegerField(default=0, verbose_name='Порядок сортировки')
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    period_start = models.DateField(null=True, blank=True, verbose_name='Начало периода видимости')
    period_end = models.DateField(null=True, blank=True, verbose_name='Конец периода видимости')
    is_selection_closed = models.BooleanField(default=False, verbose_name='Выбор закрыт')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    
    class Meta:
        verbose_name = 'Группа товаров'
        verbose_name_plural = 'Группы товаров'
        ordering = ['order', 'name']
    
    def __str__(self):
        return self.name
    
    def is_visible_today(self):
        """Проверка видимости группы сегодня"""
        from django.utils import timezone
        today = timezone.now().date()
        
        if not self.is_active:
            return False
        
        if self.period_start and today < self.period_start:
            return False
        
        if self.period_end and today > self.period_end:
            return False
        
        return True
    
    def is_visible_on_date(self, target_date):
        """Проверка видимости группы на конкретную дату"""
        if not self.is_active:
            return False
        
        if self.period_start and target_date < self.period_start:
            return False
        
        if self.period_end and target_date > self.period_end:
            return False
        
        return True
    
    def can_select(self, target_date=None):
        """Проверка возможности выбора из группы
        
        Args:
            target_date: Дата для проверки (опционально). Если не указана, используется сегодняшняя дата.
        """
        if target_date:
            is_visible = self.is_visible_on_date(target_date)
        else:
            is_visible = self.is_visible_today()
        return is_visible and not self.is_selection_closed
    
    def close_selection_and_finalize_orders(self):
        """Закрыть выбор и финализировать заказы (списать средства)"""
        from django.db import transaction
        
        with transaction.atomic():
            # Получаем все заказы со статусом 'reserved' для этой группы
            reserved_orders = self.orders.filter(status='reserved')
            
            finalized_count = 0
            for order in reserved_orders:
                # Списываем средства
                old_balance = order.employee.balance
                order.employee.balance -= order.total_amount
                order.employee.save()
                
                # Меняем статус заказа на 'confirmed'
                order.status = 'confirmed'
                order.save()
                
                # Создаем запись о транзакции
                BalanceTransaction.objects.create(
                    employee=order.employee,
                    transaction_type='deduction',
                    amount=-order.total_amount,
                    balance_after=order.employee.balance,
                    order=order,
                    comment=f'Списание за заказ из группы "{self.name}"'
                )
                
                finalized_count += 1
            
            # Закрываем выбор
            self.is_selection_closed = True
            self.save()
            
            return finalized_count


class MenuItem(models.Model):
    """Блюдо в меню"""
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='menu_items', verbose_name='Ресторан')
    group = models.ForeignKey(MenuItemGroup, on_delete=models.SET_NULL, null=True, related_name='items', verbose_name='Группа')
    category = models.ForeignKey('ProductCategory', on_delete=models.SET_NULL, null=True, blank=True, related_name='items', verbose_name='Категория')
    name = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name='Цена', null=True, blank=True)

    # Дополнительные поля
    weight = models.CharField(max_length=50, blank=True, verbose_name='Вес/Объем')
    calories = models.IntegerField(null=True, blank=True, verbose_name='Калорийность (ккал)')
    protein = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name='Белки')
    fat = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name='Жиры')
    carbohydrates = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name='Углеводы')
    composition = models.TextField(blank=True, verbose_name='Состав')
    source_url = models.URLField(max_length=500, null=True, blank=True, verbose_name='Ссылка на источник')
    image_url = models.URLField(max_length=500, null=True, blank=True, verbose_name='Ссылка на изображение (если нет загруженного)')

    is_available = models.BooleanField(default=True, verbose_name='Доступно')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
    
    class Meta:
        verbose_name = 'Блюдо'
        verbose_name_plural = 'Блюда'
        ordering = ['restaurant', 'name']
    
    def __str__(self):
        return f"{self.restaurant.name} - {self.name}"
    
    def get_primary_image(self):
        """Получить основное изображение"""
        return self.images.filter(is_primary=True).first() or self.images.first()


class ProductCategory(models.Model):
    """Категория товара (Супы, Салаты и т.д.)"""
    name = models.CharField(max_length=100, verbose_name='Название')
    order = models.IntegerField(default=0, verbose_name='Порядок сортировки')
    is_active = models.BooleanField(default=True, verbose_name='Активна')

    class Meta:
        verbose_name = 'Категория товара'
        verbose_name_plural = 'Категории товаров'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class MenuItemImage(models.Model):
    """Изображение товара"""
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='images', verbose_name='Товар')
    image = models.ImageField(upload_to='menu_items/%Y/%m/%d/', verbose_name='Изображение')
    is_primary = models.BooleanField(default=False, verbose_name='Основное изображение')
    order = models.IntegerField(default=0, verbose_name='Порядок')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Загружено')
    
    class Meta:
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товаров'
        ordering = ['-is_primary', 'order', 'created_at']
    
    def __str__(self):
        return f"Изображение для {self.menu_item.name}"
    
    def save(self, *args, **kwargs):
        # Если это основное изображение, снимаем флаг с остальных
        if self.is_primary:
            MenuItemImage.objects.filter(menu_item=self.menu_item, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)


class Order(models.Model):
    """Заказ"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('reserved', 'Зарезервирован'),
        ('confirmed', 'Подтвержден'),
        ('sent', 'Отправлен в ресторан'),
        ('completed', 'Выполнен'),
        ('cancelled', 'Отменен'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='orders', verbose_name='Сотрудник')
    group = models.ForeignKey(MenuItemGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders', verbose_name='Группа товаров')
    order_date = models.DateField(verbose_name='Дата заказа')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Сумма')
    amount_paid_by_employee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, default=0,
        verbose_name='Оплатил сам (₽)'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')
    
    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-order_date', '-created_at']
        # Убрали unique_together, чтобы можно было делать заказы на разные дни заранее
    
    def __str__(self):
        return f"Заказ {self.id} - {self.employee.name} ({self.order_date})"
    
    def calculate_total(self):
        """Пересчет общей суммы заказа"""
        total = sum(item.subtotal for item in self.items.all())
        self.total_amount = total
        self.save()
        return total


class OrderItem(models.Model):
    """Позиция в заказе"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='Заказ')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, verbose_name='Блюдо')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)], verbose_name='Количество')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена за единицу')
    
    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказов'
    
    def __str__(self):
        return f"{self.menu_item.name} x{self.quantity}"
    
    @property
    def subtotal(self):
        """Подсчет суммы позиции"""
        return self.price * self.quantity


class BalanceTransaction(models.Model):
    """Операция с балансом сотрудника"""
    TRANSACTION_TYPES = [
        ('accrual', 'Начисление'),
        ('deduction', 'Списание'),
        ('correction', 'Корректировка'),
        ('refund', 'Возврат'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='balance_transactions', verbose_name='Сотрудник')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, verbose_name='Тип операции')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма')
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Баланс после операции')
    comment = models.TextField(blank=True, verbose_name='Комментарий')
    order = models.ForeignKey('Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='balance_transactions', verbose_name='Связанный заказ')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    
    class Meta:
        verbose_name = 'Операция с балансом'
        verbose_name_plural = 'Операции с балансом'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.amount}₽ - {self.employee.name} ({self.created_at.date()})"


class WorkDayCalendar(models.Model):
    """Календарь рабочих дней для сотрудника"""
    DAY_TYPES = [
        ('work', 'Рабочий день'),
        ('vacation', 'Отпуск'),
        ('sick_leave', 'Больничный'),
        ('day_off', 'Отгул'),
        ('holiday', 'Праздничный день'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='work_calendar', verbose_name='Сотрудник')
    date = models.DateField(verbose_name='Дата')
    day_type = models.CharField(max_length=20, choices=DAY_TYPES, default='work', verbose_name='Тип дня')
    comment = models.TextField(blank=True, verbose_name='Комментарий')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
    
    class Meta:
        verbose_name = 'Календарь рабочих дней'
        verbose_name_plural = 'Календарь рабочих дней'
        ordering = ['-date']
        unique_together = ['employee', 'date']
    
    def __str__(self):
        return f"{self.employee.name} - {self.date} ({self.get_day_type_display()})"
    
    def is_work_day(self):
        """Проверка, является ли день рабочим"""
        return self.day_type == 'work'


class GlobalWorkDay(models.Model):
    """Глобальный календарь рабочих дней для всех сотрудников"""
    DAY_TYPES = [
        ('work', 'Рабочий день'),
        ('holiday', 'Выходной/Праздник'),
    ]
    
    date = models.DateField(unique=True, verbose_name='Дата')
    day_type = models.CharField(max_length=20, choices=DAY_TYPES, default='work', verbose_name='Тип дня')
    comment = models.TextField(blank=True, verbose_name='Комментарий')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    
    class Meta:
        verbose_name = 'Рабочий день (общий)'
        verbose_name_plural = 'Рабочие дни (общий календарь)'
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.date} - {self.get_day_type_display()}"
    
    @classmethod
    def is_work_day_for_all(cls, date):
        """Проверяет, является ли дата рабочим днём для всех"""
        record = cls.objects.filter(date=date).first()
        if record:
            return record.day_type == 'work'
        # Если записи нет - используем стандартную логику (пн-пт = рабочие)
        return date.weekday() < 5  # 0-4 = пн-пт


class Settings(models.Model):
    """Настройки системы"""
    key = models.CharField(max_length=100, unique=True, verbose_name='Ключ')
    value = models.TextField(verbose_name='Значение')
    description = models.TextField(blank=True, verbose_name='Описание')
    
    class Meta:
        verbose_name = 'Настройка'
        verbose_name_plural = 'Настройки'
    
    def __str__(self):
        return self.key


class WeekCompanyAmount(models.Model):
    """Сколько дала компания на неделю (пн–вс); week_start = понедельник."""
    week_start = models.DateField(unique=True, verbose_name='Понедельник недели')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Сумма (₽)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Сумма компании за неделю'
        verbose_name_plural = 'Суммы компании за неделю'
        ordering = ['-week_start']

    def __str__(self):
        return f"{self.week_start} — {self.amount}₽"


class PushSubscription(models.Model):
    """Web Push подписка браузера сотрудника"""
    employee_name = models.CharField(max_length=255, verbose_name='Имя сотрудника', db_index=True)
    endpoint = models.TextField(unique=True, verbose_name='Endpoint')
    p256dh = models.TextField(verbose_name='p256dh ключ')
    auth = models.TextField(verbose_name='auth ключ')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Push подписка'
        verbose_name_plural = 'Push подписки'

    def __str__(self):
        return f'{self.employee_name} — {self.endpoint[:60]}'


class SystemConfig(models.Model):
    """Системные настройки (логотип и т.д.)"""
    logo = models.ImageField(upload_to='system/', verbose_name='Логотип', blank=True, null=True)
    
    class Meta:
        verbose_name = 'Настройки системы'
        verbose_name_plural = 'Настройки системы'

    def save(self, *args, **kwargs):
        if not self.pk and SystemConfig.objects.exists():
            # Prevent creating multiple instances
            raise ValueError('Можно создать только одну настройку системы')
        return super(SystemConfig, self).save(*args, **kwargs)

    def __str__(self):
        return "Настройки системы"


