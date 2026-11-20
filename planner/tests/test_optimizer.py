import itertools
import random
from unittest import TestCase
from planner.optimizer import Stop, optimize
from planner.errors import PlanError


class OptimizerTests(TestCase):
    def test_unused_station_solver_residue_is_not_a_stop(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        # Arcs: start-a, start-b, a-b, a-finish, b-finish.
        values = [0.0] * 14
        values[1] = values[4] = 1
        values[6] = 50
        values[9] = 20
        values[11] = 2.9e-7  # numerical residue at unused station a
        values[12] = 10
        with patch('planner.optimizer.milp', return_value=SimpleNamespace(status=0, success=True, x=values)):
            purchases, traveled = optimize(600, [Stop('a',100,3),Stop('b',400,3)])
        self.assertEqual([s.id for s,q in purchases], ['b'])
        self.assertEqual(traveled,600)

    def feasible(self,distance,stations):
        purchases,traveled=optimize(distance,stations)
        fuel=50.; previous=0.; previous_detour=0.
        for stop,amount in purchases:
            fuel-=(stop.mile-previous+previous_detour+stop.detour)/10
            self.assertGreaterEqual(fuel,-1e-6)
            fuel+=amount; self.assertLessEqual(fuel,50+1e-6)
            previous=stop.mile; previous_detour=stop.detour
        fuel-=(distance-previous+previous_detour)/10
        self.assertGreaterEqual(fuel,-1e-6)
        self.assertAlmostEqual(traveled,distance+sum(2*s.detour for s,q in purchases),places=5)
        return purchases

    def test_under_range(self): self.assertEqual(optimize(120,[]),([],120))
    def test_exact_range(self): self.assertEqual(optimize(500,[]),([],500))
    def test_multiple_stops(self):
        plan=self.feasible(1400,[Stop('a',400,3),Stop('b',800,4),Stop('c',1200,3)])
        self.assertGreaterEqual(len(plan),2)
        self.assertAlmostEqual(sum(q for s,q in plan),90)
    def test_partial_fill(self):
        plan=self.feasible(600,[Stop('a',400,3)])
        self.assertAlmostEqual(plan[0][1],10)
    def test_cheapest_first_counterexample(self):
        plan=self.feasible(1100,[Stop('cheap',100,1),Stop('bridge',450,4),Stop('later',900,3)])
        self.assertIn('bridge',[s.id for s,q in plan])
    def test_lookahead_purchase(self):
        plan=self.feasible(900,[Stop('a',400,4),Stop('b',600,2)])
        self.assertEqual([s.id for s,q in plan],['a','b'])
        self.assertAlmostEqual(plan[0][1],10)
        self.assertAlmostEqual(plan[1][1],30)
    def test_detour_adjusted_gap(self):
        with self.assertRaises(PlanError): optimize(900,[Stop('a',495,1,10)])
    def test_detour_can_outweigh_cheap_price(self):
        plan=self.feasible(600,[Stop('cheap',400,2,100),Stop('near',410,3)])
        self.assertEqual([s.id for s,q in plan],['near'])
    def test_unreachable_gap(self):
        with self.assertRaises(PlanError) as error: optimize(1200,[Stop('a',300,3),Stop('b',900,2)])
        self.assertEqual(error.exception.code,'no_feasible_plan')
    def test_no_destination_purchase(self):
        with self.assertRaises(PlanError): optimize(600,[Stop('finish',600,1)])
    def test_detour_consumption(self):
        plan=self.feasible(600,[Stop('a',400,3,2)])
        self.assertAlmostEqual(plan[0][1],10.4)

    def test_small_cases_against_exhaustive_paths(self):
        # Independent oracle: enumerate all subsets and greedily buy on each
        # fixed path. Compare with MILP choosing the path and amounts together.
        rng=random.Random(47)
        for _ in range(12):
            stations=[Stop(str(i),m,rng.randint(2,6),rng.randint(0,10)) for i,m in enumerate([180,360,540,720])]
            best=float('inf')
            for flags in itertools.product([False,True],repeat=4):
                path=[s for s,use in zip(stations,flags) if use]
                nodes=[Stop('start',0,0)]+path+[Stop('end',900,0)]
                legs=[(b.mile-a.mile+a.detour+b.detour)/10 for a,b in zip(nodes,nodes[1:])]
                if any(x>50 for x in legs): continue
                fuel=50; cost=0
                for i in range(1,len(nodes)-1):
                    fuel-=legs[i-1]; need=0
                    for j in range(i+1,len(nodes)):
                        need+=legs[j-1]
                        if need>50: need=50; break
                        if nodes[j].price<nodes[i].price: break
                    buy=max(0,need-fuel);cost+=buy*nodes[i].price;fuel+=buy
                best=min(best,cost)
            plan=self.feasible(900,stations)
            self.assertAlmostEqual(sum(s.price*q for s,q in plan),best,places=5)
