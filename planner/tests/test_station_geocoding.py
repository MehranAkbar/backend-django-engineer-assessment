from types import SimpleNamespace
from unittest import TestCase
from planner.management.commands.geocode_stations import accept_match
from planner.geoapify import accept_station


class StationGeocodingTests(TestCase):
    def setUp(self):
        self.station=SimpleNamespace(name='PILOT TRAVEL CENTER',address='I-70 EXIT 3',city='Town',state='KS')
        self.props={'country_a':'USA','region_a':'KS','locality':'Town','confidence':1,'layer':'venue','name':'Pilot Travel Center'}
    def test_station_venue(self):self.assertTrue(accept_match(self.station,{'properties':self.props}))
    def test_city_centroid_rejected(self):
        self.props['layer']='locality';self.assertFalse(accept_match(self.station,{'properties':self.props}))
    def test_wrong_station_rejected(self):
        self.props['name']='Different Restaurant';self.assertFalse(accept_match(self.station,{'properties':self.props}))
    def test_highway_address_guess_rejected(self):
        self.props.update(layer='address',housenumber='123');self.assertFalse(accept_match(self.station,{'properties':self.props}))

    def test_geoapify_distinguishes_branches_and_road_results(self):
        self.station.name = 'Pilot #302'
        props = {'country_code': 'us', 'state_code': 'KS', 'city': 'Town',
                 'name': 'Pilot', 'result_type': 'amenity', 'category': 'service.vehicle.fuel',
                 'datasource': {'raw': {'ref': '302'}}}
        self.assertTrue(accept_station(self.station, {'properties': props}))
        props['datasource']['raw']['ref'] = '303'
        self.assertFalse(accept_station(self.station, {'properties': props}))
        props.update(result_type='street', rank={'confidence': 1})
        self.assertFalse(accept_station(self.station, {'properties': props}))

    def test_geoapify_requires_full_numbered_address(self):
        self.station.address = '225 Main Street'
        props = {'country_code': 'us', 'state_code': 'KS', 'city': 'Town',
                 'result_type': 'building', 'housenumber': '225', 'street': 'Main Street',
                 'rank': {'confidence': .95}}
        self.assertTrue(accept_station(self.station, {'properties': props}))
        props['street'] = 'Oak Street'
        self.assertFalse(accept_station(self.station, {'properties': props}))

    def test_abbreviations_preserve_direction(self):
        self.station.address = '1020 N 5TH ST'
        props = {'country_code': 'us', 'state_code': 'KS', 'city': 'Town',
                 'result_type': 'building', 'housenumber': '1020', 'street': 'North 5th Street',
                 'rank': {'confidence': .95}}
        self.assertTrue(accept_station(self.station, {'properties': props}))
        props['street'] = 'South 5th Street'
        self.assertFalse(accept_station(self.station, {'properties': props}))
