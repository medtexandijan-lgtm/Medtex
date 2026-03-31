from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from main.telegram_bot import delete_webhook


class Command(BaseCommand):
    help = "Telegram webhook ni o'chiradi"

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("TELEGRAM_BOT_TOKEN sozlanmagan")

        result = delete_webhook()
        if not result.get('ok'):
            raise CommandError(str(result))

        self.stdout.write(self.style.SUCCESS("Webhook o'chirildi"))
