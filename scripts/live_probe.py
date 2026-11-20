"""Attempt the configured ORS endpoint without logging the API key."""
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.conf import settings
from planner.provider import ORSClient
from planner.errors import PlanError
client=ORSClient();started=time.perf_counter()
try:
    result=client.request('POST',settings.ORS_BASE_URL+'/v2/directions/driving-car/geojson',json={'coordinates':[[-87.6298,41.8781],[-87.9065,43.0389]],'instructions':False})
    outcome={'success':True,'distance_meters':result['features'][0]['properties']['summary']['distance']}
except PlanError as exc:
    outcome={'success':False,'error':exc.code,'message':exc.message}
outcome.update(upstream_calls=client.calls,seconds=round(time.perf_counter()-started,6))
Path('reports').mkdir(exist_ok=True)
Path('reports/provider-probe.json').write_text(json.dumps(outcome,indent=2))
print(json.dumps(outcome,indent=2))
