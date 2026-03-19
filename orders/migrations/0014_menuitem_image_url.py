# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0013_weekcompanyamount'),
    ]

    operations = [
        migrations.AddField(
            model_name='menuitem',
            name='image_url',
            field=models.URLField(blank=True, max_length=500, null=True, verbose_name='Ссылка на изображение (если нет загруженного)'),
        ),
    ]
