from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0010_alter_telegramorder_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramorder',
            name='address',
            field=models.TextField(blank=True, verbose_name='Manzil'),
        ),
        migrations.AddField(
            model_name='telegramorder',
            name='location_latitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                verbose_name='Lokatsiya latitude',
            ),
        ),
        migrations.AddField(
            model_name='telegramorder',
            name='location_longitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                verbose_name='Lokatsiya longitude',
            ),
        ),
    ]
