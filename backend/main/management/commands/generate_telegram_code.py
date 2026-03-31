import secrets
import string
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from main.models import TelegramLinkCode, User


class Command(BaseCommand):
    help = "CRM user uchun Telegram link kod yaratadi"

    def add_arguments(self, parser):
        parser.add_argument('username', help='CRM username')
        parser.add_argument('--minutes', type=int, default=15, help='Kod amal qilish muddati')

    def handle(self, *args, **options):
        username = options['username']
        minutes = options['minutes']
        user = User.objects.filter(username=username).first()
        if not user:
            raise CommandError("Bunday user topilmadi")

        alphabet = string.ascii_uppercase + string.digits
        code = ''.join(secrets.choice(alphabet) for _ in range(6))
        expires_at = timezone.now() + timedelta(minutes=minutes)

        TelegramLinkCode.objects.create(user=user, code=code, expires_at=expires_at)

        self.stdout.write(self.style.SUCCESS(f"Username: {user.username}"))
        self.stdout.write(self.style.SUCCESS(f"Code: {code}"))
        self.stdout.write(self.style.SUCCESS(f"Expires: {expires_at:%Y-%m-%d %H:%M:%S}"))
