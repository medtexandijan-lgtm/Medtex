from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from main.telegram_bot import set_webhook


class Command(BaseCommand):
    help = "Telegram webhook ni o'rnatadi"

    def add_arguments(self, parser):
        parser.add_argument('--base-url', help='Masalan: https://example.com')

    def handle(self, *args, **options):
        base_url = (options.get('base_url') or settings.APP_BASE_URL).rstrip('/')
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("TELEGRAM_BOT_TOKEN sozlanmagan")
        if not base_url:
            raise CommandError("APP_BASE_URL yoki --base-url kerak")

        webhook_url = f"{base_url}/telegram/webhook/"
        result = set_webhook(webhook_url)
        if not result.get('ok'):
            raise CommandError(str(result))

        self.stdout.write(self.style.SUCCESS(f"Webhook o'rnatildi: {webhook_url}"))
