from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0010_alter_telegramorder_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('director', 'Direktor'),
                    ('seller', 'Sotuvchi'),
                    ('warehouse', 'Omborchi'),
                    ('supplier', 'Yetkazib beruvchi'),
                    ('courier', 'Kuryer'),
                ],
                default='seller',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='telegramorder',
            name='courier',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'role__in': ['supplier', 'courier']},
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='courier_orders',
                to='main.user',
            ),
        ),
    ]
