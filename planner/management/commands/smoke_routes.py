import json
import platform
import time
from pathlib import Path
from django import get_version
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.test import Client
from planner.models import Station

ROUTES={
 'short':{'start':{'latitude':41.8781,'longitude':-87.6298},'finish':{'latitude':43.0389,'longitude':-87.9065}},
 'multi-stop':{'start':{'latitude':40.7608,'longitude':-111.8910},'finish':{'latitude':41.8781,'longitude':-87.6298}},
}


class Command(BaseCommand):
    help='Live cold/warm smoke checks; save actual responses, never label failed routes verified.'
    def add_arguments(self,parser):parser.add_argument('--output',default='reports/live')
    def handle(self,**options):
        output=Path(options['output']);output.mkdir(parents=True,exist_ok=True)
        report={'mode':'LIVE provider, imported data','python':platform.python_version(),'django':get_version(),'platform':platform.platform(),'matched_stations':Station.objects.filter(status='matched').count(),'routes':{}}
        client=Client()
        for name,payload in ROUTES.items():
            cache.clear();observations=[]
            for temperature in ('cold','warm'):
                started=time.perf_counter();response=client.post('/api/route-plan/',data=json.dumps(payload),content_type='application/json')
                elapsed=time.perf_counter()-started;data=response.json()
                (output/f'{name}-{temperature}.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
                verified=response.status_code==200 and (name=='short' or len(data.get('fuel_stops',[]))>=2)
                observations.append({'cache':temperature,'seconds':round(elapsed,6),'status':response.status_code,'upstream_calls':data.get('upstream_calls'),'verified_for_demo':verified})
            report['routes'][name]={'request':payload,'observations':observations}
        (output/'timings.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps(report,indent=2))
