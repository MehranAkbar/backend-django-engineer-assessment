from unittest import TestCase
from planner.locations import input_state
from planner.errors import PlanError


class LocationTests(TestCase):
    def test_us_forms(self):
        for text in ('Chicago, IL','Chicago, Illinois','123 Main, Chicago, IL 60601, USA'):
            self.assertEqual(input_state(text),'IL')
    def test_foreign_or_ambiguous(self):
        for text in ('Toronto, Canada','London, UK','Springfield','Paris, France'):
            with self.assertRaises(PlanError):input_state(text)
