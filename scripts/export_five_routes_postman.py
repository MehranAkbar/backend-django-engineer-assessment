"""Export checked requests and actual responses for Postman."""
import json
from datetime import datetime, timezone
from pathlib import Path

folder = Path('reports/five-routes')
summary = json.loads((folder / 'summary.json').read_text())
items = []
for row in summary['routes']:
    request = {
        'method': 'POST',
        'header': [{'key': 'Content-Type', 'value': 'application/json'}],
        'url': '{{base_url}}/api/route-plan/',
        'body': {'mode': 'raw', 'raw': json.dumps(row['request'], indent=2),
                 'options': {'raw': {'language': 'json'}}},
    }
    data = json.loads((folder / (row['name'] + '.json')).read_text())
    items.append({
        'name': row['name'],
        'request': request,
        'response': [{'name': 'Recorded live response', 'originalRequest': request,
                      'status': 'OK' if row['http_status'] == 200 else 'Failed verification',
                      'code': row['http_status'],
                      'header': [{'key': 'Content-Type', 'value': 'application/json'}],
                      'body': json.dumps(data, indent=2)}],
    })
collection = {
    'info': {'name': 'Spotter — Five checked routes',
             'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
             'description': 'Actual provider responses using the local imported station database. '
                            'Recorded ' + datetime.now(timezone.utc).isoformat() +
                            '. Costs exclude the initial full tank and include estimated detours. '
                            'Provider availability and routes may change.'},
    'variable': [{'key': 'base_url', 'value': 'http://127.0.0.1:8000'}],
    'item': items,
}
Path('postman/Five-Checked-Routes.postman_collection.json').write_text(
    json.dumps(collection, indent=2), encoding='utf-8')
print(json.dumps({'saved_requests': len(items),
                  'successful': sum(r['http_status'] == 200 for r in summary['routes'])}))
