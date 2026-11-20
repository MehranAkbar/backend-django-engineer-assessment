"""Produce MOCKED examples and timings in an isolated temporary database.

Run: python scripts/generate_demo.py. Never changes imported stations.
"""
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, override_settings
from django.db import connections
from planner.models import Station

output=settings.BASE_DIR/'examples';output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    connections.close_all()
    settings.DATABASES['default']['NAME']=str(Path(temp)/'demo.sqlite3')
    connections['default'].settings_dict['NAME']=settings.DATABASES['default']['NAME']
    call_command('migrate',verbosity=0)
    for i,lon in enumerate([-106,-102,-98]):
        Station.objects.create(opis_id=f'MOCK-{i}',name=f'Synthetic station {i}',address='Illustrative address',city='Synthetic',state='KS',price=[3,4,3][i],longitude=lon,latitude=40,status='matched',source='MOCK ONLY',fingerprint='mock')
    report={'mode':'MOCKED routing, boundary and stations. Not verified real-world routes.','python':platform.python_version(),'django':django.get_version(),'platform':platform.platform(),'routes':{}}
    for name,distance,finish in [('mock-short',100,-108),('mock-multi-stop',1400,-96)]:
        payload={'start':{'latitude':40,'longitude':-110},'finish':{'latitude':40,'longitude':finish}}
        route={'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'LineString','coordinates':[[-110,40],[finish,40]]},'properties':{'summary':{'distance':distance*1609.344}}}]}
        cache.clear();observations=[]
        with override_settings(ORS_API_KEY='mock'),patch('planner.provider.validate_us',side_effect=lambda lon,lat:[lon,lat]),patch('planner.provider.requests.request',return_value=Mock(ok=True,status_code=200,json=lambda:route)):
            for temperature in ('cold','warm'):
                started=time.perf_counter();response=Client().post('/api/route-plan/',data=json.dumps(payload),content_type='application/json');elapsed=time.perf_counter()-started
                data=response.json();data['verification']='MOCKED illustration; not a live verified route'
                assert response.status_code==200,data
                (output/f'{name}-{temperature}.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
                observations.append({'cache':temperature,'seconds':round(elapsed,6),'upstream_calls':data['upstream_calls'],'fuel_stops':len(data['fuel_stops'])})
        report['routes'][name]={'request':payload,'observations':observations}
    (output/'mock-timings.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    connections.close_all()
print(json.dumps(report,indent=2))
