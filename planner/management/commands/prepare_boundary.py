import hashlib
import json
from pathlib import Path
import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

URL='https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_admin_0_countries.geojson'


class Command(BaseCommand):
    help='Download pinned Natural Earth 1:10m US boundary for offline endpoint validation.'
    def handle(self,**options):
        target=settings.BASE_DIR/'data/us_boundary.geojson'
        if target.exists():
            self.stdout.write('Boundary already exists.'); return
        try:
            response=requests.get(URL,timeout=90); response.raise_for_status()
            data=response.json()
            usa=next(f for f in data['features'] if f['properties'].get('ADM0_A3')=='USA')
        except (requests.RequestException,ValueError,StopIteration,KeyError) as exc:
            raise CommandError('Unable to download Natural Earth boundary; check network access.') from exc
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(usa),encoding='utf-8')
        (target.parent/'boundary-source.json').write_text(json.dumps({'url':URL,'license':'public domain','sha256':hashlib.sha256(response.content).hexdigest()},indent=2))
        self.stdout.write(str(target))
