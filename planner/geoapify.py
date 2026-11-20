"""Station search, used only during database preparation."""
import re

import requests
from django.conf import settings

from .errors import PlanError


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', (value or '').casefold())


def store_number(name):
    match = re.search(r'#\s*(\d+)', name or '')
    return match.group(1) if match else None


def street_key(address):
    words = re.findall(r'[a-z0-9]+', address.casefold())
    aliases = {'street': 'st', 'road': 'rd', 'avenue': 'ave', 'lane': 'ln',
               'north': 'n', 'south': 's', 'east': 'e', 'west': 'w'}
    return tuple(aliases.get(word, word) for word in words)


def accept_station(station, feature):
    p = feature['properties']
    if p.get('country_code', '').lower() != 'us' or p.get('state_code') != station.state:
        return False
    if normalized(station.city) != normalized(p.get('city')):
        return False

    # A nearby road or interchange is useful for review only.
    if p.get('result_type') == 'amenity':
        name = p.get('name', '')
        if not name:
            return False
        source_number = store_number(station.name)
        raw = p.get('datasource', {}).get('raw') or {}
        result_number = store_number(name) or str(raw.get('ref') or '').strip() or None
        if source_number and result_number and source_number != result_number:
            return False
        if 'fuel' not in (p.get('category') or '').split('.') and raw.get('amenity') != 'fuel':
            return False
        station_name = normalized(re.sub(r'#\s*\d+', '', station.name))
        candidate_name = normalized(re.sub(r'#\s*\d+', '', name))
        same_name = station_name == candidate_name
        if source_number and result_number:
            return same_name or station_name == normalized(raw.get('brand'))
        # A branch number lost in search results cannot distinguish chain outlets.
        return same_name and not source_number and len(normalized(name)) >= 9

    if p.get('result_type') != 'building':
        return False
    street = ' '.join([str(p.get('housenumber') or ''), p.get('street') or ''])
    return (bool(p.get('housenumber') and p.get('street'))
            and street_key(station.address) == street_key(street)
            and p.get('rank', {}).get('confidence', 0) >= 0.8)


class GeoapifyClient:
    def __init__(self):
        self.calls = 0

    def search(self, station):
        # Numbered addresses can resolve to buildings. For exits, search the venue.
        numbered = re.match(r'^\d+\s', station.address)
        subject = station.address if numbered else station.name
        params = {'text': f'{subject}, {station.city}, {station.state}, USA',
                  'filter': 'countrycode:us', 'limit': 5, 'format': 'geojson',
                  'apiKey': settings.GEOAPIFY_API_KEY}
        self.calls += 1
        try:
            response = requests.get('https://api.geoapify.com/v1/geocode/search',
                                    params=params, timeout=(5, 15))
        except requests.RequestException:
            # requests exceptions can contain the API key in the URL.
            raise PlanError('geoapify_unavailable', 'Could not reach Geoapify.', 502) from None
        if response.status_code != 200:
            raise PlanError(f'geoapify_http_{response.status_code}', 'Geoapify rejected the request.')
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get('features'), list):
            raise ValueError('Invalid Geoapify response')
        return data
