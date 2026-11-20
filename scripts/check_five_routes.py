"""Verify five candidate requests using the current database and real provider."""
import json
import os
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.test import Client
from planner.models import Station

routes = [
    ('short-chicago-milwaukee', (41.8781, -87.6298), (43.0389, -87.9065)),
    ('short-denver-colorado-springs', (39.7392, -104.9903), (38.8339, -104.8214)),
    ('long-denver-kansas-city', (39.7392, -104.9903), (39.0997, -94.5786)),
    ('long-denver-omaha', (39.7392, -104.9903), (41.2565, -95.9345)),
    ('long-kansas-city-colorado-springs', (39.0997, -94.5786), (38.8339, -104.8214)),
]
output = Path('reports/five-routes')
output.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('--retry-failed', action='store_true')
parser.add_argument('--refresh', help='Recheck this named route even if previously successful')
parser.add_argument('--http', action='store_true', help='Call the running localhost:8000 server')
options = parser.parse_args()
old = {}
if options.retry_failed and (output / 'summary.json').exists():
    old = {r['name']: r for r in json.loads((output / 'summary.json').read_text())['routes']}
report = {'matched_stations': Station.objects.filter(status='matched').count(), 'routes': []}
for name, start, finish in routes:
    if old.get(name, {}).get('http_status') == 200 and name != options.refresh:
        report['routes'].append(old[name])
        continue
    payload = {'start': dict(zip(('latitude', 'longitude'), start)),
               'finish': dict(zip(('latitude', 'longitude'), finish))}
    started = time.perf_counter()
    if options.http:
        import requests
        response = requests.post('http://127.0.0.1:8000/api/route-plan/', json=payload, timeout=(5,90))
    else:
        response = Client().post('/api/route-plan/', data=json.dumps(payload), content_type='application/json')
    data = response.json()
    (output / f'{name}.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    summary = {'name': name, 'request': payload, 'http_status': response.status_code,
               'seconds': round(time.perf_counter()-started, 3),
               'distance_miles': data.get('route_distance_miles'),
               'fuel_spend_usd': data.get('total_fuel_spend_usd'),
               'stops': [s['opis_id'] for s in data.get('fuel_stops', [])],
               'error': data.get('error')}
    report['routes'].append(summary)
    print(json.dumps(summary), flush=True)
(output / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
