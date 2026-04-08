import json
import hmac
import hashlib
from urllib.parse import parse_qsl
from urllib import request

from django.conf import settings
from django.core import signing
from django.db.models import Sum
from django.utils import timezone

from .models import Client, Product, Sale, TelegramLinkCode, TelegramProfile, WarehouseTransaction

TELEGRAM_INIT_DATA_MAX_AGE = 7 * 24 * 60 * 60
MINI_APP_LAUNCH_TOKEN_SALT = 'mini-app-launch'


def bot_enabled():
    return bool(settings.TELEGRAM_BOT_TOKEN)


def bot_api_url(method):
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def telegram_request(method, payload):
    if not bot_enabled():
        raise RuntimeError('TELEGRAM_BOT_TOKEN sozlanmagan')

    data = json.dumps(payload).encode('utf-8')
    req = request.Request(
        bot_api_url(method),
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


def send_message(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return telegram_request('sendMessage', payload)


def set_webhook(url):
    payload = {'url': url}
    if settings.TELEGRAM_WEBHOOK_SECRET:
        payload['secret_token'] = settings.TELEGRAM_WEBHOOK_SECRET
    return telegram_request('setWebhook', payload)


def delete_webhook():
    return telegram_request('deleteWebhook', {'drop_pending_updates': False})


def get_or_create_profile(chat):
    defaults = {
        'chat_username': chat.get('username', ''),
        'first_name': chat.get('first_name', ''),
        'last_name': chat.get('last_name', ''),
        'is_active': True,
    }
    profile, created = TelegramProfile.objects.get_or_create(chat_id=chat['id'], defaults=defaults)
    if not created:
        profile.chat_username = chat.get('username', '')
        profile.first_name = chat.get('first_name', '')
        profile.last_name = chat.get('last_name', '')
        profile.is_active = True
        profile.save(update_fields=['chat_username', 'first_name', 'last_name', 'is_active', 'last_seen_at'])
    return profile


def build_help_text():
    return (
        "Medical CRM yordam markazi\n\n"
        "/start - asosiy menyuni ochadi\n"
        "/link KOD - Telegram profilingizni CRM user bilan bog'laydi\n"
        "/me - bog'langan profilingizni ko'rsatadi\n"
        "/stats - rolingizga mos qisqa statistikani chiqaradi\n"
        "/help - yordam oynasini qayta ochadi"
    )


def build_start_text():
    lines = [
        "Medical CRM botiga xush kelibsiz.",
        "",
        "Quyidagi menyu orqali tez ishlashingiz mumkin:",
        "- Buyurtma berish: katalogni ochadi",
        "- /stats: qisqa ko'rsatkichlar",
        "- /me: bog'langan profilingiz",
        "- /link KOD: CRM bilan ulash",
    ]
    if not settings.APP_BASE_URL:
        lines.extend(
            [
                "",
                "Mini App hozircha sozlanmagan.",
            ]
        )
    return "\n".join(lines)


def issue_mini_app_launch_token(chat):
    payload = {
        'chat_id': chat['id'],
        'username': chat.get('username', ''),
        'first_name': chat.get('first_name', ''),
        'last_name': chat.get('last_name', ''),
    }
    return signing.dumps(payload, salt=MINI_APP_LAUNCH_TOKEN_SALT)


def build_main_menu_markup(chat=None):
    first_row = []
    if settings.APP_BASE_URL:
        mini_app_url = f'{settings.APP_BASE_URL}/mini-app/'
        if chat:
            mini_app_url = f"{mini_app_url}?launch={issue_mini_app_launch_token(chat)}"
        first_row.append(
            {
                'text': 'Buyurtma berish',
                'web_app': {'url': mini_app_url},
            }
        )

    keyboard = []
    if first_row:
        keyboard.append(first_row)

    keyboard.extend(
        [
            [{'text': '/stats'}, {'text': '/me'}],
            [{'text': '/help'}, {'text': '/link KOD'}],
        ]
    )
    return {
        'keyboard': keyboard,
        'resize_keyboard': True,
        'is_persistent': True,
        'input_field_placeholder': "Buyruq tanlang yoki yozing",
    }


def validate_init_data(init_data):
    if not bot_enabled() or not init_data:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop('hash', '')
    if not received_hash:
        return None

    data_check_string = '\n'.join(f'{key}={value}' for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b'WebAppData', settings.TELEGRAM_BOT_TOKEN.encode('utf-8'), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        return None

    auth_date = int(pairs.get('auth_date', '0') or '0')
    if not auth_date:
        return None
    if timezone.now().timestamp() - auth_date > TELEGRAM_INIT_DATA_MAX_AGE:
        return None

    user_raw = pairs.get('user')
    if not user_raw:
        return None

    try:
        user_data = json.loads(user_raw)
    except json.JSONDecodeError:
        return None

    return {'user': user_data, 'auth_date': auth_date}


def build_stats_text(user):
    today = timezone.now().date()
    if user.role == 'director':
        total_revenue = Sale.objects.filter(status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        return (
            "Direktor statistikasi:\n"
            f"Mahsulotlar: {Product.objects.count()}\n"
            f"Mijozlar: {Client.objects.count()}\n"
            f"Sotuvlar: {Sale.objects.count()}\n"
            f"Daromad: {total_revenue:.0f} so'm"
        )
    if user.role == 'seller':
        my_revenue = Sale.objects.filter(seller=user, status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        return (
            "Sotuvchi statistikasi:\n"
            f"Jami sotuvlar: {Sale.objects.filter(seller=user).count()}\n"
            f"Bugungi sotuvlar: {Sale.objects.filter(seller=user, created_at__date=today).count()}\n"
            f"Daromad: {my_revenue:.0f} so'm"
        )
    total_stock = Product.objects.aggregate(Sum('stock'))['stock__sum'] or 0
    low_stock = Product.objects.filter(stock__lt=10).count()
    return (
        "Ombor statistikasi:\n"
        f"Mahsulot turlari: {Product.objects.count()}\n"
        f"Jami qoldiq: {total_stock}\n"
        f"Kam qolgan mahsulotlar: {low_stock}\n"
        f"So'nggi operatsiyalar: {WarehouseTransaction.objects.count()}"
    )


def process_link_command(chat, code):
    now = timezone.now()
    link_code = (
        TelegramLinkCode.objects.select_related('user')
        .filter(code=code, is_used=False, expires_at__gte=now)
        .order_by('-created_at')
        .first()
    )
    if not link_code:
        send_message(chat['id'], "Kod topilmadi yoki muddati tugagan.")
        return

    TelegramProfile.objects.filter(user=link_code.user).exclude(chat_id=chat['id']).delete()
    profile = get_or_create_profile(chat)
    profile.user = link_code.user
    profile.save(update_fields=['user', 'chat_username', 'first_name', 'last_name', 'is_active', 'last_seen_at'])

    link_code.is_used = True
    link_code.used_at = now
    link_code.save(update_fields=['is_used', 'used_at'])

    send_message(
        chat['id'],
        f"Bog'landi: {link_code.user.username} ({link_code.user.get_role_display()}). Endi /stats ni ishlatishingiz mumkin.",
    )


def process_message(message):
    chat = message.get('chat') or {}
    text = (message.get('text') or '').strip()
    if not chat or not text:
        return

    parts = text.split(maxsplit=1)
    command = parts[0].lower()

    if command in {'/start', '/help'}:
        send_message(
            chat['id'],
            build_start_text() if command == '/start' else build_help_text(),
            reply_markup=build_main_menu_markup(chat),
        )
        return

    if command == '/link':
        if len(parts) < 2:
            send_message(chat['id'], "Kod yuboring: /link ABC123")
            return
        process_link_command(chat, parts[1].strip().upper())
        return

    profile = TelegramProfile.objects.filter(chat_id=chat['id'], is_active=True).select_related('user').first()
    if not profile or not profile.user:
        send_message(chat['id'], "Avval profilingizni bog'lang. Buning uchun CRM ichida link kod yarating va /link KOD yuboring.")
        return

    if command == '/me':
        send_message(
            chat['id'],
            f"User: {profile.user.username}\nRol: {profile.user.get_role_display()}",
        )
        return

    if command == '/stats':
        send_message(chat['id'], build_stats_text(profile.user))
        return

    send_message(chat['id'], "Buyruq tushunilmadi. /help ni yuboring.")


def process_update(update):
    message = update.get('message') or update.get('edited_message')
    if message:
        process_message(message)
