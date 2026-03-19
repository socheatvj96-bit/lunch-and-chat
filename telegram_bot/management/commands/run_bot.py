from django.core.management.base import BaseCommand
from telegram_bot.bot import start_bot


class Command(BaseCommand):
    help = 'Запуск Telegram бота'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Запуск Telegram бота...'))
        start_bot()

