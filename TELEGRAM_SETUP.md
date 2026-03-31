# Telegram Bot Integratsiyasi

## Kerakli environment variable'lar

PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN="BOT_TOKEN"
$env:TELEGRAM_WEBHOOK_SECRET="LONG_RANDOM_SECRET"
$env:APP_BASE_URL="https://your-domain.example"
```

## Webhook o'rnatish

```powershell
python manage.py set_telegram_webhook
```

## Userni Telegram bilan bog'lash

1. CRM user uchun kod yarating:

```powershell
python manage.py generate_telegram_code seller1
```

2. Telegram botga yuboring:

```text
/link ABC123
```

## Bot buyruqlari

- `/start`
- `/help`
- `/link KOD`
- `/me`
- `/stats`

## Mini App

`/start` yuborilganda bot `Buyurtma berish` tugmasini chiqaradi. Bu tugma quyidagi URL'ni ochadi:

```text
https://your-domain.example/mini-app/
```

Mini App imkoniyatlari:

- katalogni ko'rish
- savat yig'ish
- buyurtma yuborish
- buyurtma holatini ko'rish
- buyurtmani CRM ichida ko'rish

## CRM ichida ko'rish

Yangi sahifalar:

- `/telegram-orders/`
- `/telegram-orders/<id>/`

Bu sahifalarda Telegram buyurtmani tasdiqlab `Sale` ga aylantirish mumkin.
