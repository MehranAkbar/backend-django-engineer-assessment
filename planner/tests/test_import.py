import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import patch,Mock
from django.test import TestCase
from django.core.management import call_command
from planner.models import Station


class ImportTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'fuel.csv';self.report=Path(self.tmp.name)/'report.json'
        with self.path.open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['OPIS Truckstop ID','Truckstop Name','Address','City','State','Retail Price'])
            w.writerows([['1','One','123 Main St','Town','KS','3.12345678'],['1','Alias','123 Main St','Town','KS','3.12345678'],['2','Bad','Main','Town','KS','NaN'],['3','Highway','I-70 EXIT 1','Town','KS','3.5']])
    def run_import(self,**kwargs):call_command('import_stations',str(self.path),report=str(self.report),verbosity=0,**kwargs)
    def test_idempotent_and_rejections(self):
        self.run_import();self.run_import()
        self.assertEqual(Station.objects.count(),2)
        report=json.loads(self.report.read_text());self.assertEqual(report['duplicates'],1);self.assertEqual(len(report['rejected']),1)
        self.assertEqual(report['matched'],0)
    def test_preserve_coordinates(self):
        self.run_import();Station.objects.filter(opis_id='1').update(latitude=39,longitude=-98,status='matched')
        self.run_import();self.assertEqual(Station.objects.get(opis_id='1').status,'matched')
    @patch('planner.management.commands.import_stations.validate_us',side_effect=lambda lon,lat:[lon,lat])
    @patch('planner.management.commands.import_stations.requests.post')
    def test_census_batch_pilot(self,post,validate):
        post.return_value=Mock(text='"1","123 Main","Match","Exact","123 MAIN ST","-98,39","1","L"\n"3","I-70 EXIT 1","No_Match"',raise_for_status=lambda:None)
        self.run_import(pilot=True)
        self.assertEqual(Station.objects.get(opis_id='1').status,'matched')
        self.assertEqual(Station.objects.get(opis_id='3').status,'unresolved')
        self.assertEqual(post.call_count,1)
