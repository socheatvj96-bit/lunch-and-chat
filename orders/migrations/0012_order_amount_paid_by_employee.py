# Generated manually for Order.amount_paid_by_employee

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0011_globalworkday'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='amount_paid_by_employee',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Оплатил сам (₽)'),
        ),
    ]
