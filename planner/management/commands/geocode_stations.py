"""Optional quota-bounded ORS preprocessing; never called by the API."""
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from planner.models import Station
from planner.geoapify import GeoapifyClient, accept_station
from planner.provider import ORSClient
from planner.geography import validate_us, us_boundary
from planner.errors import PlanError


def accept_match(station,feature):
    """Reject city centroids, vague road results and mismatched station names."""
    p=feature.get('properties',{})
    if p.get('country_a') not in ('US','USA') or p.get('region_a')!=station.state: return False
    if p.get('layer') not in ('venue','address') or p.get('confidence',0)<.9: return False
    if p.get('locality','').casefold()!=station.city.casefold(): return False
    if p['layer']=='venue':
        norm=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
        return SequenceMatcher(None,norm(station.name),norm(p.get('name',''))).ratio()>=.75
    number=re.match(r'^(\d+)\s',station.address)
    return bool(number and str(p.get('housenumber',''))==number[1])


class Command(BaseCommand):
    help='Resolve stations with Geoapify or ORS under an explicit call budget.'
    def add_arguments(self,parser):
        parser.add_argument('--limit',type=int,default=10)
        parser.add_argument('--pilot',action='store_true')
        parser.add_argument('--retry-unmatched',action='store_true')
        parser.add_argument('--provider',choices=['geoapify','ors'])
        parser.add_argument('--states', nargs='+', type=str.upper, help='Restrict matching to these state codes.')
        parser.add_argument('--report')
    def handle(self,**options):
        if not 1<=options['limit']<=1000: raise CommandError('Limit must be 1..1000; respect remaining account quota.')
        provider = options['provider'] or ('geoapify' if settings.GEOAPIFY_API_KEY else 'ors')
        geoapify = provider == 'geoapify'
        if geoapify and not settings.GEOAPIFY_API_KEY:
            raise CommandError('Set GEOAPIFY_API_KEY in .env.')
        label = 'Geoapify' if geoapify else 'ORS'
        try:us_boundary()
        except PlanError as exc:raise CommandError(exc.message)
        query=Station.objects.filter(status='unresolved').order_by('opis_id')
        if options['states']:
            query = query.filter(state__in=options['states'])
        if not options['retry_unmatched']:query=query.exclude(source__startswith=label+' unmatched')
        if options['pilot']:
            rows=list(query);street=lambda s:bool(re.match(r'^\d+\s',s.address))
            pending=([s for s in rows if street(s)][:5]+[s for s in rows if not street(s)][:5])[:options['limit']]
        else:pending=list(query[:options['limit']])
        client=GeoapifyClient() if geoapify else ORSClient()
        results=[];failure=None
        for station in pending:
            if client.calls:time.sleep(.25 if geoapify else .65)
            try:
                if geoapify:
                    data = client.search(station)
                    accepted = [f for f in data['features'] if accept_station(station, f)]
                else:
                    data=client.request('GET',settings.ORS_GEOCODE_URL+'/search',params={'text':f'{station.name}, {station.address}, {station.city}, {station.state}','boundary.country':'USA','size':3})
                    accepted=[f for f in data.get('features',[]) if accept_match(station,f)]
                if len(accepted)==1:
                    lon,lat=validate_us(*accepted[0]['geometry']['coordinates'][:2])
                    station.longitude=lon;station.latitude=lat;station.status='matched'
                    props = accepted[0]['properties']
                    if geoapify:
                        station.source = f"Geoapify; {props.get('datasource', {}).get('attribution', '')}; {props.get('formatted', '')}"[:200]
                    else:
                        station.source='ORS Pelias venue/address; CC BY-SA 4.0; '+props.get('label','')
                else:station.source=label+' unmatched or ambiguous; manual verification required'
                updated = Station.objects.filter(pk=station.pk, status='unresolved', fingerprint=station.fingerprint).update(
                    longitude=station.longitude, latitude=station.latitude, status=station.status, source=station.source)
                row = {'opis_id':station.opis_id,'status':station.status if updated else 'changed_since_lookup','source':station.source}
                if geoapify:
                    row['candidates'] = [f['properties'].get('formatted') for f in data['features']]
                    row['candidate_details'] = [
                        {**{key: f['properties'].get(key) for key in
                            ('formatted', 'result_type', 'category', 'name', 'city', 'state_code', 'street', 'housenumber', 'rank')},
                         'coordinates': f.get('geometry', {}).get('coordinates'),
                         'passed_match_rules': f in accepted}
                        for f in data['features']]
                results.append(row)
            except (PlanError,KeyError,TypeError,ValueError) as exc:
                failure=exc.code if isinstance(exc,PlanError) else 'invalid_provider_response';break
        report={'upstream_calls':client.calls,'results':results,'error':failure,'matched_total':Station.objects.filter(status='matched').count(),'unresolved_total':Station.objects.filter(status='unresolved').count()}
        path=Path(options['report'] or f'reports/{provider}-stations.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps(report,indent=2))
        if failure:raise CommandError(f'Geocoding stopped: {failure}. Progress was persisted.')
