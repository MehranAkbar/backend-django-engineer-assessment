import json
from unittest.mock import patch, Mock
import requests
from django.test import TestCase, override_settings
from django.core.cache import cache
from planner.provider import ORSClient
from planner.errors import PlanError
from planner.models import Station


def route(miles=100):
    return {'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'LineString','coordinates':[[-100,40],[-90,40]]},'properties':{'summary':{'distance':miles*1609.344}}}]}


@override_settings(ORS_API_KEY='test-only')
class APITests(TestCase):
    def setUp(self):
        cache.clear()
        self.boundary=patch('planner.provider.validate_us',side_effect=lambda lon,lat:[lon,lat]);self.boundary.start();self.addCleanup(self.boundary.stop)
    def post(self,body): return self.client.post('/api/route-plan/',data=json.dumps(body),content_type='application/json')
    @patch('planner.provider.requests.request')
    def test_verified_station_address_skips_geocoding(self, request):
        Station.objects.create(opis_id='verified', name='Fuel', address='Exit 7', city='Town',
                               state='KS', verified_address='123 Main St, Town, KS',
                               latitude=39, longitude=-98, price=3, status='matched')
        self.assertEqual(ORSClient().endpoint('123 MAIN ST, Town, KS'), [-98, 39])
        request.assert_not_called()
    @patch('planner.provider.requests.request')
    def test_coordinate_budget_and_cache(self,request):
        request.return_value=Mock(ok=True,status_code=200,json=lambda:route())
        body={'start':{'latitude':40,'longitude':-100},'finish':{'latitude':40,'longitude':-90}}
        cold=self.post(body);warm=self.post(body)
        self.assertEqual(cold.status_code,200);self.assertEqual(cold.json()['upstream_calls'],1)
        self.assertEqual(warm.json()['upstream_calls'],0);self.assertEqual(request.call_count,1)
        self.assertEqual(cold.json()['total_fuel_spend_usd'],'0.00')
    @patch('planner.provider.requests.request')
    def test_text_budget_normalization(self,request):
        def geo(lon):return {'features':[{'geometry':{'coordinates':[lon,40]},'properties':{'country_a':'USA','confidence':1}}]}
        request.side_effect=[Mock(ok=True,status_code=200,json=lambda:geo(-100)),Mock(ok=True,status_code=200,json=lambda:geo(-90)),Mock(ok=True,status_code=200,json=lambda:route())]
        cold=self.post({'start':' City, KS ','finish':'Other, IL'})
        self.assertEqual(cold.status_code,200);self.assertEqual(cold.json()['upstream_calls'],3)
        warm=self.post({'start':'city, ks','finish':'other, il'})
        self.assertEqual(warm.json()['upstream_calls'],0);self.assertEqual(request.call_count,3)
    @patch('planner.provider.requests.request')
    def test_rate_limit(self,request):
        request.return_value=Mock(status_code=429)
        response=self.post({'start':'City, KS','finish':'Other, IL'})
        self.assertEqual(response.status_code,429);self.assertEqual(response.json()['upstream_calls'],1)
    @patch('planner.provider.requests.request',side_effect=requests.Timeout)
    def test_timeout(self,request):
        response=self.post({'start':'City, KS','finish':'Other, IL'})
        self.assertEqual(response.status_code,504);self.assertEqual(request.call_count,1)
    def test_invalid_input(self):
        for body in ([],{}, {'start':True,'finish':'City, KS'},{'start':{'latitude':True,'longitude':2},'finish':'City, KS'}):
            self.assertEqual(self.post(body).status_code,400)
    @patch('planner.provider.requests.request')
    def test_ambiguous(self,request):
        request.return_value=Mock(ok=True,status_code=200,json=lambda:{'features':[{'properties':{'country_a':'USA','confidence':.2}}]})
        response=self.post({'start':'Springfield, IL','finish':'Other, IL'})
        self.assertEqual(response.json()['error']['code'],'ambiguous_location')
    @patch('planner.provider.requests.request')
    def test_unroutable(self,request):
        request.return_value=Mock(status_code=404)
        response=self.post({'start':{'latitude':40,'longitude':-100},'finish':{'latitude':40,'longitude':-90}})
        self.assertEqual(response.status_code,422)
    @patch('planner.provider.requests.request')
    def test_no_feasible_gap(self,request):
        request.return_value=Mock(ok=True,status_code=200,json=lambda:route(900))
        response=self.post({'start':{'latitude':40,'longitude':-100},'finish':{'latitude':40,'longitude':-90}})
        self.assertEqual(response.json()['error']['code'],'no_feasible_plan')
        self.assertEqual(request.call_count,1)
    def test_map(self): self.assertContains(self.client.get('/'),'openrouteservice')

    @patch('planner.provider.requests.request')
    def test_stops_costs_and_unresolved_exclusion(self,request):
        from decimal import Decimal
        for opis,lon,price,status in [('a',-95.5555555556,4,'matched'),('b',-93.3333333333,2,'matched'),('unresolved',-96,0.01,'unresolved')]:
            Station.objects.create(opis_id=opis,name=opis,address='123 Main',city='Town',state='KS',price=price,longitude=lon,latitude=40,status=status,fingerprint='test')
        request.return_value=Mock(ok=True,status_code=200,json=lambda:route(900))
        response=self.post({'start':{'latitude':40,'longitude':-100},'finish':{'latitude':40,'longitude':-90}})
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual([s['opis_id'] for s in data['fuel_stops']],['a','b'])
        self.assertEqual(sum(Decimal(s['stop_cost']) for s in data['fuel_stops']),Decimal(data['total_fuel_spend_usd']))
        self.assertEqual(data['total_fuel_spend_usd'],'100.00')
        self.assertEqual(request.call_count,1)

    @patch('planner.provider.requests.request')
    def test_malformed_geometry(self,request):
        data=route();data['features'][0]['geometry']['coordinates'][0]=['bad',40]
        request.return_value=Mock(ok=True,status_code=200,json=lambda:data)
        response=self.post({'start':{'latitude':40,'longitude':-100},'finish':{'latitude':40,'longitude':-90}})
        self.assertEqual(response.status_code,502)
