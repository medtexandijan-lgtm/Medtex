from django.db import migrations
from django.contrib.auth.hashers import make_password


def seed_default_users(apps, schema_editor):
    User = apps.get_model('main', 'User')
    if User.objects.exists():
        return

    users = [
        {
            'username': 'admin',
            'password': 'admin12345',
            'role': 'director',
            'first_name': 'Admin',
            'is_staff': True,
            'is_superuser': True,
        },
        {
            'username': 'seller1',
            'password': 'seller12345',
            'role': 'seller',
            'first_name': 'Sotuvchi',
            'is_staff': False,
            'is_superuser': False,
        },
        {
            'username': 'omborchi1',
            'password': 'ombor12345',
            'role': 'warehouse',
            'first_name': 'Omborchi',
            'is_staff': False,
            'is_superuser': False,
        },
    ]

    for payload in users:
        password = payload.pop('password')
        user = User(**payload)
        user.password = make_password(password)
        user.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('main', '0006_sellershift_sale_shift'),
    ]

    operations = [
        migrations.RunPython(seed_default_users, noop_reverse),
    ]
