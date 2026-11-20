from django.db import models


class Station(models.Model):
    opis_id = models.CharField(max_length=40, primary_key=True)
    name = models.CharField(max_length=250)
    address = models.CharField(max_length=500)
    verified_address = models.CharField(max_length=500, blank=True)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    price = models.DecimalField(max_digits=14, decimal_places=8)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    status = models.CharField(max_length=30, default='unresolved', db_index=True)
    source = models.CharField(max_length=200, blank=True)
    fingerprint = models.CharField(max_length=64)
