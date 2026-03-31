from django.contrib.auth.hashers import make_password
from django.db import migrations


def seed_supplier_user(apps, schema_editor):
    User = apps.get_model('main', 'User')
    if User.objects.filter(username='supplier1').exists():
        return

    User.objects.create(
        username='supplier1',
        password=make_password('supplier12345'),
        role='supplier',
        first_name='Yetkazib beruvchi',
        is_staff=False,
        is_superuser=False,
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('main', '0008_alter_user_role'),
    ]

    operations = [
        migrations.RunPython(seed_supplier_user, noop_reverse),
    ]
