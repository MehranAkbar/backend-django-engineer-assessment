from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(name='Station', fields=[
        ('opis_id', models.CharField(max_length=40, primary_key=True, serialize=False)),
        ('name', models.CharField(max_length=250)),
        ('address', models.CharField(max_length=500)),
        ('city', models.CharField(max_length=120)),
        ('state', models.CharField(max_length=2)),
        ('price', models.DecimalField(max_digits=14, decimal_places=8)),
        ('latitude', models.FloatField(null=True)),
        ('longitude', models.FloatField(null=True)),
        ('status', models.CharField(db_index=True, default='unresolved', max_length=30)),
        ('source', models.CharField(blank=True, max_length=200)),
        ('fingerprint', models.CharField(max_length=64)),
    ])]
