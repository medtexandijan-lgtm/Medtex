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
    SellerShift,
    TelegramLinkCode,
    TelegramOrder,
    TelegramProfile,
    User,
    WarehouseTransaction,
)
from .telegram_bot import build_main_menu_markup


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
        self.supplier_user = User.objects.create_user(
            username='supplier',
            password='testpass123',
            role='supplier',
            first_name='Yetkazib',
        )
        self.courier_user = User.objects.create_user(
            username='courier',
            password='testpass123',
            role='courier',
            first_name='Kuryer',
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
        self.out_of_stock_product = Product.objects.create(
            name='Holter monitor',
            category=self.category,
            price=2500000,
            stock=0,
            unit='dona',
        )

    def test_director_cannot_open_clients_page(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('clients'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_seller_cannot_open_clients_page(self):
        self.client.force_login(self.seller)
        response = self.client.get(reverse('clients'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_seller_cannot_open_products_page(self):
        self.client.force_login(self.seller)
        response = self.client.get(reverse('products'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_seller_cannot_open_categories_page(self):
        self.client.force_login(self.seller)
        response = self.client.get(reverse('categories'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_warehouse_cannot_open_clients_page(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('clients'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_warehouse_cannot_open_categories_page(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('categories'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_warehouse_cannot_open_sales_page(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('sales'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_warehouse_cannot_open_transactions_history(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('transactions'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_supplier_cannot_open_clients_page(self):
        self.client.force_login(self.supplier_user)
        response = self.client.get(reverse('clients'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_supplier_cannot_open_sales_page(self):
        self.client.force_login(self.supplier_user)
        response = self.client.get(reverse('sales'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_supplier_cannot_open_categories_page(self):
        self.client.force_login(self.supplier_user)
        response = self.client.get(reverse('categories'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_supplier_cannot_open_generic_products_page(self):
        self.client.force_login(self.supplier_user)
        response = self.client.get(reverse('products'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_supplier_can_open_telegram_orders_management(self):
        self.client.force_login(self.supplier_user)
        response = self.client.get(reverse('telegram_orders'))
        self.assertEqual(response.status_code, 200)

    def test_supplier_can_view_confirmed_delivery_orders(self):
        profile = TelegramProfile.objects.create(chat_id=45678, chat_username='delivery_user')
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Yetkazish mijoz',
            phone='+998901234500',
            comment='Andijon shahar',
            total_amount=self.product.price,
            status='confirmed',
        )
        order.items.create(
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
        )

        self.client.force_login(self.supplier_user)
        response = self.client.get(reverse('supplier_deliveries'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.full_name)
        self.assertContains(response, 'Tasdiqlangan')
        self.assertContains(response, 'Qabul qilish')

    def test_supplier_sees_yetkazildi_button_for_delivering_order_in_list(self):
        profile = TelegramProfile.objects.create(chat_id=45681, chat_username='delivering_user')
        TelegramOrder.objects.create(
            profile=profile,
            full_name='Yetkazilayotgan mijoz',
            phone='+998901234503',
            comment='Asaka',
            total_amount=self.product.price,
            status='delivering',
        )

        self.client.force_login(self.supplier_user)
        response = self.client.get(reverse('supplier_deliveries'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Yetkazildi')

    def test_seller_sees_accept_button_for_new_telegram_order_in_list(self):
        profile = TelegramProfile.objects.create(chat_id=45677, chat_username='new_order_user')
        TelegramOrder.objects.create(
            profile=profile,
            full_name='Yangi buyurtma mijoz',
            phone='+998901234599',
            comment='Test',
            total_amount=self.product.price,
            status='new',
        )

        self.client.force_login(self.seller)
        response = self.client.get(reverse('telegram_orders'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Qabul qilish')

    def test_supplier_legacy_supply_url_redirects_to_deliveries(self):
        self.client.force_login(self.supplier_user)
        response = self.client.get('/supplier/supplies/')
        self.assertRedirects(response, reverse('supplier_deliveries'))

    @patch('main.views.send_message')
    def test_supplier_can_accept_confirmed_delivery(self, mock_send_message):
        profile = TelegramProfile.objects.create(chat_id=45679, chat_username='delivery_done')
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Mijoz Delivery',
            phone='+998901234501',
            comment='Margilan',
            total_amount=self.product.price,
            status='confirmed',
        )
        order.items.create(
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
        )

        self.client.force_login(self.supplier_user)
        response = self.client.post(reverse('supplier_delivery_complete', args=[order.id]), follow=True)
        order.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, 'delivering')
        self.assertContains(response, "yetkazib berish jarayoniga o&#x27;tdi", html=False)
        mock_send_message.assert_called_once()
        self.assertIn("mahsulot yetkazib berilyapti", mock_send_message.call_args.args[1])

    @patch('main.views.send_message')
    def test_supplier_can_complete_delivery_after_accepting(self, mock_send_message):
        profile = TelegramProfile.objects.create(chat_id=45680, chat_username='delivery_finished')
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Mijoz Yetkazildi',
            phone='+998901234502',
            comment='Qo`qon',
            total_amount=self.product.price,
            status='delivering',
        )
        order.items.create(
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
        )

        self.client.force_login(self.supplier_user)
        response = self.client.post(reverse('supplier_delivery_complete', args=[order.id]), follow=True)
        order.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, 'completed')
        self.assertContains(response, 'mijozga yetkazildi', html=False)
        mock_send_message.assert_called_once()
        self.assertIn("muvaffaqiyatli yetkazildi", mock_send_message.call_args.args[1])

    def test_director_sees_shift_buttons_for_seller_in_users_list(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('users'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Smenani boshlash")

    def test_user_form_contains_supplier_role(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('user_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Yetkazib beruvchi')
        self.assertContains(response, 'Kuryer')

    def test_director_dashboard_focuses_on_employee_control(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'Xodimlar holati')
        self.assertContains(response, reverse('users'))
        self.assertNotContains(response, reverse('sales'))
        self.assertNotContains(response, reverse('warehouse'))

    def test_director_cannot_create_sale(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse('sale_create'), {}, follow=True)
        self.assertRedirects(response, reverse('dashboard'))

    def test_director_cannot_manage_warehouse(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('warehouse'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_director_cannot_manage_products(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('products'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_director_cannot_accept_telegram_orders(self):
        profile = TelegramProfile.objects.create(chat_id=223344, chat_username='director_blocked')
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Blocked order',
            phone='+998901234560',
            total_amount=self.product.price,
            status='new',
        )
        self.client.force_login(self.director)
        response = self.client.post(reverse('telegram_order_update_status', args=[order.id]), {'status': 'confirmed'}, follow=True)
        self.assertRedirects(response, reverse('dashboard'))

    def test_seller_cannot_create_sale_without_open_shift(self):
        self.client.force_login(self.seller)
        response = self.client.post(
            reverse('sale_create'),
            {
                'client': str(self.client_obj.id),
                'notes': 'Test savdo',
                'product_id[]': [str(self.product.id)],
                'quantity[]': ['1'],
            },
            follow=True,
        )

        self.assertEqual(Sale.objects.count(), 0)
        self.assertContains(response, "avval smenani boshlang", html=False)

    def test_sale_create_reduces_stock_and_creates_transactions(self):
        SellerShift.objects.create(seller=self.seller)
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
        self.assertIsNotNone(sale.shift)
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(WarehouseTransaction.objects.filter(transaction_type='out').count(), 1)

    def test_director_can_start_shift_for_seller(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse('seller_shift_start', args=[self.seller.id]))

        self.assertRedirects(response, reverse('users'))
        self.assertTrue(SellerShift.objects.filter(seller=self.seller, ended_at__isnull=True).exists())

    def test_api_login_and_me_endpoints_work(self):
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'username': 'seller', 'password': 'testpass123'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        me_response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()['username'], 'seller')

    def test_api_seller_can_start_shift_and_create_sale(self):
        self.client.force_login(self.seller)

        shift_response = self.client.post('/api/v1/shifts/start/', data={}, content_type='application/json')
        self.assertEqual(shift_response.status_code, 201)

        sale_response = self.client.post(
            '/api/v1/sales/',
            data={
                'notes': 'API savdo',
                'items': [{'product_id': self.product.id, 'quantity': 2}],
            },
            content_type='application/json',
        )

        self.assertEqual(sale_response.status_code, 201)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(Sale.objects.count(), 1)

    def test_courier_api_login_returns_bearer_token(self):
        response = self.client.post(
            '/api/v1/courier/auth/login/',
            data={'username': 'courier', 'password': 'testpass123'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['token'])
        self.assertEqual(payload['user']['role'], 'courier')

    @patch('main.api_views.notify_order_profile')
    def test_courier_api_can_accept_confirmed_order(self, mock_notify):
        profile = TelegramProfile.objects.create(chat_id=45690, chat_username='courier_api_accept')
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Courier API Client',
            phone='+998901000001',
            comment='Namangan',
            total_amount=self.product.price,
            status='confirmed',
        )
        order.items.create(
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
        )

        login_response = self.client.post(
            '/api/v1/courier/auth/login/',
            data={'username': 'courier', 'password': 'testpass123'},
            content_type='application/json',
        )
        token = login_response.json()['token']

        response = self.client.post(
            f'/api/v1/courier/orders/{order.id}/accept/',
            data={},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'delivering')
        self.assertEqual(order.courier, self.courier_user)
        mock_notify.assert_called_once()

    @patch('main.api_views.notify_order_profile')
    def test_courier_api_can_complete_only_own_delivery(self, mock_notify):
        profile = TelegramProfile.objects.create(chat_id=45691, chat_username='courier_api_complete')
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Courier Complete Client',
            phone='+998901000002',
            comment='Fargona',
            total_amount=self.product.price,
            status='delivering',
            courier=self.courier_user,
        )
        order.items.create(
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
        )

        login_response = self.client.post(
            '/api/v1/courier/auth/login/',
            data={'username': 'courier', 'password': 'testpass123'},
            content_type='application/json',
        )
        token = login_response.json()['token']

        response = self.client.post(
            f'/api/v1/courier/orders/{order.id}/complete/',
            data={},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'completed')
        mock_notify.assert_called_once()

    def test_courier_api_orders_only_show_available_and_owned_deliveries(self):
        profile = TelegramProfile.objects.create(chat_id=45692, chat_username='courier_api_list')
        available_order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Available Client',
            phone='+998901000003',
            total_amount=self.product.price,
            status='confirmed',
        )
        owned_order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Owned Client',
            phone='+998901000004',
            total_amount=self.product.price,
            status='delivering',
            courier=self.courier_user,
        )
        hidden_order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Hidden Client',
            phone='+998901000005',
            total_amount=self.product.price,
            status='delivering',
            courier=self.supplier_user,
        )

        login_response = self.client.post(
            '/api/v1/courier/auth/login/',
            data={'username': 'courier', 'password': 'testpass123'},
            content_type='application/json',
        )
        token = login_response.json()['token']

        response = self.client.get(
            '/api/v1/courier/orders/',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {item['id'] for item in response.json()}
        self.assertIn(available_order.id, returned_ids)
        self.assertIn(owned_order.id, returned_ids)
        self.assertNotIn(hidden_order.id, returned_ids)

    def test_api_seller_cannot_create_sale_without_shift(self):
        self.client.force_login(self.seller)

        response = self.client.post(
            '/api/v1/sales/',
            data={
                'notes': 'API savdo',
                'items': [{'product_id': self.product.id, 'quantity': 1}],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)

    def test_closing_shift_redirects_to_report_with_sold_items(self):
        self.client.force_login(self.seller)
        start_response = self.client.post(reverse('shift_start'))
        self.assertRedirects(start_response, reverse('dashboard'))

        shift = SellerShift.objects.get(seller=self.seller, ended_at__isnull=True)
        sale = Sale.objects.create(
            client=None,
            seller=self.seller,
            shift=shift,
            total_amount=1500000,
            status='completed',
        )
        sale.items.create(
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
        )

        response = self.client.post(reverse('shift_end'), follow=True)
        shift.refresh_from_db()

        self.assertIsNotNone(shift.ended_at)
        self.assertTemplateUsed(response, 'shift_report.html')
        self.assertContains(response, "Sotilgan uskunalar ro'yxati", html=False)
        self.assertContains(response, self.product.name)

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

    @override_settings(APP_BASE_URL='https://crm.example.com')
    def test_start_menu_markup_contains_web_app_and_shortcuts(self):
        markup = build_main_menu_markup()

        self.assertTrue(markup['resize_keyboard'])
        self.assertEqual(markup['keyboard'][0][0]['text'], 'Buyurtma berish')
        self.assertEqual(
            markup['keyboard'][0][0]['web_app']['url'],
            'https://crm.example.com/mini-app/',
        )
        self.assertEqual(markup['keyboard'][1][0]['text'], '/stats')
        self.assertEqual(markup['keyboard'][1][1]['text'], '/me')

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
        self.assertEqual(len(payload['products']), 2)
        self.assertEqual(payload['products'][0]['name'], 'EKG apparati')
        self.assertTrue(payload['products'][0]['is_available'])
        self.assertEqual(payload['products'][1]['name'], 'Holter monitor')
        self.assertFalse(payload['products'][1]['is_available'])
        self.assertTrue(TelegramProfile.objects.filter(chat_id=123456).exists())

    def test_mini_app_catalog_returns_products_without_auth(self):
        response = self.client.get(reverse('mini_app_catalog'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(len(payload['products']), 2)
        self.assertEqual(payload['products'][0]['name'], 'EKG apparati')

    @override_settings(TELEGRAM_BOT_TOKEN='test-token')
    def test_mini_app_auth_requires_non_empty_init_data(self):
        response = self.client.post(
            reverse('mini_app_auth'),
            data={'initData': ''},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Telegram sessiyasi topilmadi. Bot ichidan qayta oching.')

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
                'address': 'Andijon shahar, Bobur ko\'chasi 12',
                'comment': 'Test order',
                'location': {'latitude': 40.782123, 'longitude': 72.344567},
                'items': [{'product_id': self.product.id, 'quantity': 2}],
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(TelegramOrder.objects.count(), 1)
        order = TelegramOrder.objects.first()
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.address, "Andijon shahar, Bobur ko'chasi 12")
        self.assertEqual(str(order.location_latitude), '40.782123')
        self.assertEqual(str(order.location_longitude), '72.344567')

    @override_settings(TELEGRAM_BOT_TOKEN='test-token')
    @patch('main.views.validate_init_data')
    def test_mini_app_can_list_order_history(self, mock_validate):
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
        profile = TelegramProfile.objects.get(chat_id=123456)
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Mini User',
            phone='+998901234567',
            address='Asaka tumani, Mustaqillik 5',
            location_latitude='40.700000',
            location_longitude='72.350000',
            comment='History test',
            status='new',
            total_amount=self.product.price,
        )
        order.items.create(
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
        )

        response = self.client.get(
            reverse('mini_app_orders'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(len(payload['orders']), 1)
        self.assertEqual(payload['orders'][0]['id'], order.id)
        self.assertEqual(payload['orders'][0]['address'], 'Asaka tumani, Mustaqillik 5')
        self.assertEqual(payload['orders'][0]['location']['latitude'], '40.700000')

    @patch('main.views.send_message')
    def test_confirming_telegram_order_creates_sale(self, mock_send_message):
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

        SellerShift.objects.create(seller=self.seller)
        self.client.force_login(self.seller)
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
        mock_send_message.assert_called_once()
        self.assertIn("Buyurtmangiz qabul qilindi", mock_send_message.call_args.args[1])

    def test_cancelling_confirmed_telegram_order_restores_stock(self):
        profile = TelegramProfile.objects.create(chat_id=12346, chat_username='customer2')
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Telegram Customer 2',
            phone='+998907778899',
            total_amount=3000000,
            status='confirmed',
        )
        order.items.create(
            product=self.product,
            quantity=2,
            unit_price=self.product.price,
            total_price=self.product.price * 2,
        )
        sale = Sale.objects.create(
            client=self.client_obj,
            seller=self.seller,
            total_amount=3000000,
            status='completed',
        )
        sale.items.create(
            product=self.product,
            quantity=2,
            unit_price=self.product.price,
            total_price=self.product.price * 2,
        )
        order.sale = sale
        order.save(update_fields=['sale'])
        self.product.stock = 8
        self.product.save(update_fields=['stock'])

        self.client.force_login(self.seller)
        self.client.post(
            reverse('telegram_order_update_status', args=[order.id]),
            {'status': 'cancelled'},
            follow=True,
        )

        order.refresh_from_db()
        sale.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(sale.status, 'cancelled')
        self.assertEqual(self.product.stock, 10)

    @override_settings(TELEGRAM_BOT_TOKEN='test-token')
    @patch('main.views.validate_init_data')
    def test_mini_app_does_not_create_order_when_stock_is_insufficient(self, mock_validate):
        mock_validate.return_value = {
            'user': {
                'id': 999001,
                'username': 'mini_user_2',
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
                'full_name': 'Mini User 2',
                'phone': '+998900000001',
                'address': 'Test manzil',
                'comment': '',
                'items': [{'product_id': self.product.id, 'quantity': 999}],
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TelegramOrder.objects.count(), 0)

    def test_supplier_detail_shows_location_but_manager_detail_does_not(self):
        profile = TelegramProfile.objects.create(chat_id=551122, chat_username='geo_user')
        order = TelegramOrder.objects.create(
            profile=profile,
            full_name='Geo Client',
            phone='+998900000222',
            address='Andijon, Amir Temur 10',
            location_latitude='40.765432',
            location_longitude='72.345678',
            comment='Geo test',
            total_amount=self.product.price,
            status='confirmed',
        )

        self.client.force_login(self.supplier_user)
        supplier_response = self.client.get(reverse('supplier_delivery_detail', args=[order.id]))
        self.assertContains(supplier_response, '40,765432')
        self.assertContains(supplier_response, 'maps.google.com')

        self.client.force_login(self.seller)
        manager_response = self.client.get(reverse('telegram_order_detail', args=[order.id]))
        self.assertContains(manager_response, 'Andijon, Amir Temur 10')
        self.assertNotContains(manager_response, '40,765432')
