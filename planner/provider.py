import hashlib
import json
import math
import re
import requests
from django.conf import settings
from django.core.cache import cache
from .errors import PlanError
from .geography import validate_us, haversine
from .locations import input_state
from .models import Station


class ORSClient:
    def __init__(self):
        self.calls = 0

    def request(self, method, url, **kwargs):
        if not settings.ORS_API_KEY:
            raise PlanError('provider_not_configured', 'Set ORS_API_KEY in .env.', 503)
        self.calls += 1
        try:
            response = requests.request(method,url,headers={'Authorization': settings.ORS_API_KEY},timeout=(5,30),**kwargs)
        except requests.Timeout:
            raise PlanError('provider_timeout', 'Routing provider timed out; retry later.', 504)
        except requests.RequestException:
            raise PlanError('provider_unavailable', 'Cannot connect to routing provider.', 502)
        if response.status_code == 429:
            raise PlanError('provider_rate_limit', 'Provider quota exceeded; retry later.', 429)
        if response.status_code in (401,403):
            raise PlanError('provider_auth', 'Provider rejected the configured API key.', 503)
        if response.status_code in (400,404):
            raise PlanError('unroutable', 'Provider could not resolve or route these endpoints.', 422)
        if not response.ok:
            raise PlanError('provider_unavailable', 'Routing provider returned an error.', 502)
        try: return response.json()
        except ValueError: raise PlanError('provider_response', 'Provider returned invalid JSON.', 502)

    def endpoint(self,value):
        if isinstance(value,dict) and set(value) == {'latitude','longitude'}:
            lat,lon = value['latitude'],value['longitude']
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (lat,lon)) or not (-90<=lat<=90 and -180<=lon<=180):
                raise PlanError('invalid_coordinates', 'Use finite numeric latitude and longitude.', 400)
            return validate_us(lon,lat)
        if not isinstance(value,str) or not 3<=len(value.strip())<=300:
            raise PlanError('invalid_endpoint', 'Use a US city/state or address string, or {latitude, longitude}.',400)
        normalized = re.sub(r'\s+',' ',value.strip()).casefold()
        state=input_state(normalized)
        known = list(Station.objects.filter(
            status='matched', state=state, verified_address__iexact=normalized,
            longitude__isnull=False, latitude__isnull=False,
        ).values_list('longitude', 'latitude').distinct()[:2])
        if len(known) == 1:
            return validate_us(*known[0])
        if ',' not in normalized:
            raise PlanError('ambiguous_location','Include city and state, separated by a comma.',400)
        key = 'geo:'+hashlib.sha256(normalized.encode()).hexdigest()
        cached = cache.get(key)
        if cached is not None: return cached
        data = self.request('GET',settings.ORS_GEOCODE_URL+'/search',params={'text':normalized,'boundary.country':'USA','size':3})
        features = data.get('features',[])
        if not features:
            raise PlanError('location_not_found','No US location matched the input.',400)
        first=features[0]; props=first.get('properties',{})
        if props.get('region_a') and props['region_a']!=state:
            raise PlanError('ambiguous_location','Matched state differs from the requested state; use coordinates.',400)
        if props.get('country_a') not in ('USA','US') or props.get('confidence',0)<.8:
            raise PlanError('ambiguous_location','Location match is uncertain; provide a full address or coordinates.',400)
        coord=first.get('geometry',{}).get('coordinates',[])
        if len(coord)!=2: raise PlanError('provider_response','Invalid geocoding coordinates.',502)
        if len(features)>1:
            second=features[1]
            if second.get('properties',{}).get('confidence',0)>=props.get('confidence',0)-.05 and haversine(coord,second['geometry']['coordinates'])>5:
                raise PlanError('ambiguous_location','Multiple locations matched; provide explicit coordinates.',400)
        result=validate_us(*coord)
        cache.set(key,result,settings.CACHE_TTL)
        return result

    def route(self,start,finish):
        key='route:'+hashlib.sha256(json.dumps([settings.ORS_BASE_URL,start,finish]).encode()).hexdigest()
        result=cache.get(key)
        if result is not None: return result
        result=self.request('POST',settings.ORS_BASE_URL+'/v2/directions/driving-car/geojson',json={'coordinates':[start,finish],'instructions':False,'options':{'avoid_borders':'all'}})
        try:
            feature=result['features'][0]
            assert feature['geometry']['type']=='LineString'
            coords=feature['geometry']['coordinates']
            assert isinstance(coords,list) and len(coords)>=2
            assert all(isinstance(p,list) and len(p)>=2 and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in p[:2]) and -180<=p[0]<=180 and -90<=p[1]<=90 for p in coords)
            distance=feature['properties']['summary']['distance']
            assert math.isfinite(distance) and distance>0
        except (KeyError,IndexError,TypeError,AssertionError,ValueError):
            raise PlanError('provider_response','Provider returned malformed route geometry.',502)
        if distance>6000000: raise PlanError('route_too_long','Hosted provider supports routes up to 6,000 km.',422)
        cache.set(key,result,settings.CACHE_TTL)
        return result
