"""Idempotent CSV import and Census batch geocoding, outside request path."""
import csv
import hashlib
import io
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from planner.models import Station
from planner.geography import validate_us
from planner.errors import PlanError

STATES=set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC'.split())
CENSUS='https://geocoding.geo.census.gov/geocoder/locations/addressbatch'


class Command(BaseCommand):
    help='Import fuel CSV; optionally geocode with Census. Repeated unchanged imports preserve matches.'
    def add_arguments(self,parser):
        parser.add_argument('csv_path',nargs='?',default='fuel-prices-for-be-assessment.csv')
        parser.add_argument('--geocode',action='store_true')
        parser.add_argument('--pilot',action='store_true',help='Geocode 5 street addresses and 5 highway descriptions')
        parser.add_argument('--report',default='reports/import.json')
        parser.add_argument('--coordinates',help='Verified overrides CSV: opis_id,latitude,longitude,source')

    def handle(self,*args,**options):
        path=Path(options['csv_path']); report_path=Path(options['report']); report_path.parent.mkdir(parents=True,exist_ok=True)
        rejected=[]; duplicates=0; seen={}; raw_count=0
        try:
            with path.open(encoding='utf-8-sig',newline='') as handle:
                reader=csv.DictReader(handle)
                required={'OPIS Truckstop ID','Truckstop Name','Address','City','State','Retail Price'}
                if not required.issubset(reader.fieldnames or []): raise CommandError('Missing required CSV headers.')
                for line,row in enumerate(reader,2):
                    raw_count+=1
                    try:
                        price=Decimal(row['Retail Price']); opis=row['OPIS Truckstop ID'].strip()
                        if not opis or not price.is_finite() or price<=0 or price>=100 or row['State'] not in STATES: raise ValueError()
                        if not all(row[k].strip() for k in ('Truckstop Name','Address','City')): raise ValueError()
                        record={'name':row['Truckstop Name'].strip(),'address':row['Address'].strip(),'city':row['City'].strip(),'state':row['State'],'price':price}
                        if opis in seen:
                            duplicates+=1
                            old=seen[opis]
                            if any(old[k].casefold()!=record[k].casefold() for k in ('address','city','state')):
                                rejected.append({'line':line,'opis_id':opis,'reason':'conflicting duplicate location; first row retained'})
                            continue
                        seen[opis]=record
                    except (ValueError,InvalidOperation,AttributeError):
                        rejected.append({'line':line,'reason':'invalid required fields, US state or price'})
        except OSError as exc: raise CommandError(str(exc))
        with transaction.atomic():
            # Dataset replacement marks absent stations ineligible, preserving audit history.
            Station.objects.exclude(opis_id__in=seen).update(status='inactive')
            for opis,record in seen.items():
                fingerprint=hashlib.sha256(json.dumps({k:record[k] for k in ('address','city','state')},sort_keys=True).encode()).hexdigest()
                obj,created=Station.objects.get_or_create(opis_id=opis,defaults={**record,'fingerprint':fingerprint})
                if not created:
                    if obj.fingerprint!=fingerprint or obj.status=='inactive':
                        obj.latitude=obj.longitude=None; obj.status='unresolved'; obj.source=''
                        obj.verified_address = ''
                    for key,value in record.items(): setattr(obj,key,value)
                    obj.fingerprint=fingerprint; obj.save()
        if options['coordinates']:
            with open(options['coordinates'],newline='',encoding='utf-8-sig') as handle:
                for row in csv.DictReader(handle):
                    try:
                        lon,lat=validate_us(float(row['longitude']),float(row['latitude']))
                        if not row['source'].strip(): raise ValueError()
                        Station.objects.filter(opis_id=row['opis_id']).update(longitude=lon,latitude=lat,status='matched',source=row['source'])
                    except (KeyError,ValueError,PlanError): raise CommandError('Invalid coordinate override; provide verified US coordinates and source.')
        geocode_error=None; pilot=[]; batch_calls=0
        unresolved=list(Station.objects.filter(status='unresolved').order_by('opis_id'))
        street=lambda s: bool(re.match(r'^\d+\s+[A-Za-z]',s.address))
        if options['pilot']:
            pending=[s for s in unresolved if street(s)][:5]+[s for s in unresolved if not street(s)][:5]
        else: pending=[s for s in unresolved if street(s)]
        if options['geocode'] or options['pilot']:
            for start in range(0,len(pending),1000):
                batch=pending[start:start+1000]; buffer=io.StringIO(); writer=csv.writer(buffer)
                for s in batch: writer.writerow([s.opis_id,s.address,s.city,s.state,''])
                try:
                    batch_calls+=1
                    response=requests.post(CENSUS,files={'addressFile':('addresses.csv',buffer.getvalue(),'text/csv')},data={'benchmark':'Public_AR_Current'},timeout=(10,180))
                    response.raise_for_status()
                    results=list(csv.reader(io.StringIO(response.text)))
                    for row in results:
                        if len(row)<3: continue
                        matched=False
                        if row[2]=='Match' and len(row)>5:
                            try:
                                lon,lat=validate_us(*map(float,row[5].split(',')))
                                # Census interpolates address ranges; not verified pump entrances.
                                Station.objects.filter(opis_id=row[0]).update(longitude=lon,latitude=lat,status='matched',source='US Census Public_AR_Current; interpolated address')
                                matched=True
                            except (ValueError,PlanError): pass
                        pilot.append({'opis_id':row[0],'result':row[2],'accepted':matched})
                except requests.RequestException:
                    geocode_error='Census batch request failed (network, timeout or provider status). No synthetic coordinates substituted.'
                    break
        unresolved_rows=list(Station.objects.filter(status='unresolved').values('opis_id','name','address','city','state'))
        with report_path.with_suffix('.unresolved.csv').open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=['opis_id','name','address','city','state']); writer.writeheader(); writer.writerows(unresolved_rows)
        report={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'input_rows':raw_count,'unique_stations':len(seen),'duplicates':duplicates,
                'matched':Station.objects.filter(status='matched').count(),'unresolved':len(unresolved_rows),'rejected':rejected,
                'geocoding_attempted':bool(options['geocode'] or options['pilot']),'geocode_error':geocode_error,'batch_results':pilot,
                'batch_calls':batch_calls,'selected_for_geocoding':len(pending),
                'pilot_inputs':[{'opis_id':s.opis_id,'address':s.address,'city':s.city,'state':s.state,'category':'street' if street(s) else 'highway_or_other'} for s in pending] if options['pilot'] else [],
                'method':'First valid OPIS row wins. Census street-address interpolation; highway descriptions remain unresolved unless matched in pilot or manually verified.'}
        report['coverage_percent']=round(100*report['matched']/max(len(seen),1),2)
        report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps({k:v for k,v in report.items() if k not in ('rejected','batch_results','pilot_inputs')},indent=2))
        if geocode_error: raise CommandError(geocode_error)
