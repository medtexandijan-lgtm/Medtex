from datetime import timedelta
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from unittest.mock import patch
from django.utils import timezone

from .models import (
    Category,
    Client,
    Product,
    Sale,
    TelegramLinkCode,
    TelegramOrder,
    TelegramProfile,
    User,
    WarehouseTransaction,
)


class CRMFlowTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(
            username='director',
            password='testpass123',
            role='director',
            first_name='Direktor',
        )
        self.seller = User.objects.create_user(
            username='seller',
            password='testpass123',
            role='seller',
            first_name='Sotuvchi',
        )
        self.warehouse_user = User.objects.create_user(
            username='warehouse',
            password='testpass123',
            role='warehouse',
            first_name='Omborchi',
        )
        self.category = Category.objects.create(name='Monitor')
        self.client_obj = Client.objects.create(name='Klinika', phone='+998900000000')
        self.product = Product.objects.create(
            name='EKG apparati',
            category=self.category,
            price=1500000,
            stock=10,
            unit='dona',
        )

    def test_clients_page_is_available(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('clients'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mijozlar')

    def test_sale_create_reduces_stock_and_creates_transactions(self):
        self.client.force_login(self.seller)
        response = self.client.post(
            reverse('sale_create'),
            {
                'client': str(self.client_obj.id),
                'notes': 'Test savdo',
                'product_id[]': [str(self.product.id)],
                'quantity[]': ['2'],
            },
        )
        self.assertRedirects(response, reverse('sales'))

        sale = Sale.objects.get()
        self.product.refresh_from_db()

        self.assertEqual(sale.client, self.client_obj)
        self.assertEqual(sale.status, 'completed')
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(WarehouseTransaction.objects.filter(transaction_type='out').count(), 1)

    def test_warehouse_out_transaction_requires_enough_stock(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(
            reverse('warehouse_transaction'),
            {
                'product': str(self.product.id),
                'transaction_type': 'out',
                'quantity': '50',
                'notes': 'Xato chiqim',
            },
            follow=True,
        )

        self.product.refresh_from_db()

        self.assertEqual(self.product.stock, 10)
        self.assertContains(response, "yetarli qoldiq yo&#x27;q", html=False)

    @override_settings(TELEGRAM_BOT_TOKEN='test-token', TELEGRAM_WEBHOOK_SECRET='secret123')
    @patch('main.telegram_bot.send_message')
    def test_telegram_link_command_links_chat_to_user(self, mock_send_message):
        code = TelegramLinkCode.objects.create(
            user=self.seller,
            code='ABC123',
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        response = self.client.post(
            reverse('telegram_webhook'),
            data={
                'update_id': 1,
                'message': {
                    'message_id': 1,
                    'date': 1,
                    'chat': {'id': 987654321, 'type': 'private', 'username': 'seller_bot'},
                    'text': '/link ABC123',
                },
            },
            content_type='application/json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='secret123',
        )

        self.assertEqual(response.status_code, 200)
        profile = TelegramProfile.objects.get(chat_id=987654321)
        code.refresh_from_db()

        self.assertEqual(profile.user, self.seller)
        self.assertTrue(code.is_used)
        mock_send_message.assert_called()

    @override_settings(TELEGRAM_BOT_TOKEN='test-token', TELEGRAM_WEBHOOK_SECRET='secret123')
    def test_telegram_webhook_rejects_invalid_secret(self):
        response = self.client.post(
            reverse('telegram_webhook'),
            data={'message': {'chat': {'id': 1}, 'text': '/start'}},
            content_type='application/json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='wrong-secret',
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(TELEGRAM_BOT_TOKEN='test-token')
    @patch('main.views.validate_init_data')
    def test_mini_app_auth_returns_token_and_products(self, mock_validate):
        mock_validate.return_value = {
            'user': {
                'id': 123456,
                'username': 'mini_user',
                'first_name': 'Mini',
                'last_name': 'User',
            }
        }

        response = self.client.post(
            reverse('mini_app_auth'),
            data={'initData': 'signed-data'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['token'])
        self.assertEqual(len(payload['products']), 1)
        self.assertTrue(TelegramProfile.objects.filter(chat_id=123456).exists())

    @override_settings(TELEGRAM_BOT_TOKEN='test-token')
    @patch('main.views.validate_init_data')
    def test_mini_app_can_create_order(self, mock_validate):
        mock_validate.return_value = {
            'user': {
                'id': 123456,
                'username': 'mini_user',
                'first_name': 'Mini',
            }
        }
        auth_response = self.client.post(
            reverse('mini_app_auth'),
            data={'initData': 'signed-data'},
            content_type='application/json',
        )
        token = auth_response.json()['token']

        response = self.client.post(
            reverse('mini_app_create_order'),
            data={
                'full_name': 'Mini User',
                'phone': '+998901234567',
                'comment': 'Test order',
                'items': [{'product_id': self.product.id, 'quantity': 2}],
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(TelegramOrder.objects.count(), 1)
        self.assertEqual(TelegramOrder.objects.first().items.count(), 1)

    def test_confirming_telegram_order_creates_sale(self):
        profile = TelegramProfile.objects.create(chat_id=12345, chat_username='customer1')
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Telegram Customer',
            phone='+998901112233',
            comment='Mini app order',
            total_amount=3000000,
        )
        order.items.create(
            product=self.product,
            quantity=2,
            unit_price=self.product.price,
            total_price=self.product.price * 2,
        )

        self.client.force_login(self.director)
        response = self.client.post(
            reverse('telegram_order_update_status', args=[order.id]),
            {'status': 'confirmed'},
            follow=True,
        )

        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, 'confirmed')
        self.assertIsNotNone(order.sale)
        self.assertEqual(order.sale.client.phone, '+998901112233')
        self.assertEqual(self.product.stock, 8)
