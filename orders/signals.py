from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from .tasks import send_order_confirmation


@receiver(post_save, sender=Order)
def order_confirmed(sender, instance, created, **kwargs):
    """Отправка уведомления при подтверждении заказа"""
    if instance.status == 'confirmed' and created:
        send_order_confirmation.delay(instance.employee.id, instance.id)

