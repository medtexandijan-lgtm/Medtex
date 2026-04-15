from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0012_merge_20260408_0001'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='payment_type',
            field=models.CharField(
                choices=[('cash', 'Naqd'), ('card', 'Karta')],
                default='cash',
                max_length=20,
                verbose_name="To'lov turi",
            ),
        ),
    ]
