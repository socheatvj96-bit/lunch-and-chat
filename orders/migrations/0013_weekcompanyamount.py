# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0012_order_amount_paid_by_employee'),
    ]

    operations = [
        migrations.CreateModel(
            name='WeekCompanyAmount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week_start', models.DateField(unique=True, verbose_name='Понедельник недели')),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Сумма (₽)')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
            ],
            options={
                'verbose_name': 'Сумма компании за неделю',
                'verbose_name_plural': 'Суммы компании за неделю',
                'ordering': ['-week_start'],
            },
        ),
    ]
