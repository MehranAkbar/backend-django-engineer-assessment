from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from planner.geography import nearby_stations, validate_us
from planner.errors import PlanError


class GeographyTests(TestCase):
    def test_segment_midpoint(self):
        station=SimpleNamespace(opis_id='1',longitude=-99.5,latitude=40,price=3)
        found,details=nearby_stations([[-100,40],[-99,40]],100,[station],.1,1.5)
        self.assertEqual(len(found),1);self.assertAlmostEqual(found[0].mile,50)
    def test_off_corridor(self):
        station=SimpleNamespace(opis_id='1',longitude=-99.5,latitude=41,price=3)
        found,_=nearby_stations([[-100,40],[-99,40]],100,[station],1,1.5)
        self.assertEqual(found,[])
    @patch('planner.geography.us_boundary',return_value={'type':'Polygon','coordinates':[[[-100,30],[-90,30],[-90,40],[-100,40],[-100,30]]]})
    def test_country_polygon_not_bounding_box(self,boundary):
        self.assertEqual(validate_us(-95,35),[-95,35])
        with self.assertRaises(PlanError):validate_us(-80,35)
