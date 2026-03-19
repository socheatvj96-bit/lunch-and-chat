# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0014_menuitem_image_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='personal_balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Личный баланс сотрудника'),
        ),
        migrations.AlterField(
            model_name='employee',
            name='balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Баланс компании'),
        ),
    ]
