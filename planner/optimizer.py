"""Exact minimum-cost path with continuous fuel and optional station detours.

Binary arc flow selects a forward path. Continuous arc flow is departure fuel.
Conservation at stations buys the difference; capacity and arrival constraints
prevent borrowing fuel. HiGHS proves optimality, or we return an explicit error.
No Django or provider dependency.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix
from .errors import PlanError


@dataclass(frozen=True)
class Stop:
    id: str
    mile: float
    price: float
    detour: float = 0  # one-way estimated miles from route to pump


def optimize(distance, stations):
    if distance < 0 or not np.isfinite(distance):
        raise ValueError('Distance must be finite and nonnegative')
    if distance <= 500:
        return [], distance
    stops = sorted([s for s in stations if 0 < s.mile < distance], key=lambda s: (s.mile, s.id))
    if any(s.price <= 0 or s.detour < 0 or not all(np.isfinite(v) for v in (s.mile, s.price, s.detour)) for s in stops):
        raise ValueError('Invalid station')
    if len(stops) > 250:
        raise PlanError('too_many_candidates', 'More than 250 eligible stations; reduce CORRIDOR_MILES.', 422)
    nodes = [Stop('start', 0, 0)] + stops + [Stop('finish', distance, 0)]
    n = len(nodes)
    arcs = [(i, j, (nodes[j].mile - nodes[i].mile + nodes[i].detour + nodes[j].detour)/10)
            for i in range(n-1) for j in range(i+1, n)
            if nodes[j].mile > nodes[i].mile and nodes[j].mile-nodes[i].mile+nodes[i].detour+nodes[j].detour <= 500+1e-9]
    m = len(arcs)
    if not m:
        raise PlanError('no_feasible_plan', 'No reachable fuel stops bridge this route.')
    # Variables: selected arcs x[m], departure fuel f[m], purchases q[n].
    a = lil_matrix((2*n+2*m, 2*m+n)); lower = np.zeros(a.shape[0]); upper = np.zeros(a.shape[0])
    for k, (i, j, burn) in enumerate(arcs):
        a[i,k] += 1; a[j,k] -= 1
        a[n+i,m+k] += 1; a[n+j,m+k] -= 1; a[n+j,k] += burn
        a[2*n+k,m+k] = 1; a[2*n+k,k] = -50
        lower[2*n+k] = -np.inf
        a[2*n+m+k,m+k] = 1; a[2*n+m+k,k] = -burn
        upper[2*n+m+k] = np.inf
    lower[0] = upper[0] = 1; lower[n-1] = upper[n-1] = -1
    lower[n] = upper[n] = 50
    # Destination may retain fuel; no purchase there.
    lower[2*n-1] = -50; upper[2*n-1] = 0
    for i in range(1,n-1): a[n+i,2*m+i] = -1
    ub = np.r_[np.ones(m), np.full(m,50), np.full(n,50)]
    ub[2*m] = ub[-1] = 0
    result = milp(c=np.r_[np.zeros(2*m), [s.price for s in nodes]],
                  integrality=np.r_[np.ones(m), np.zeros(m+n)],
                  bounds=Bounds(np.zeros(2*m+n),ub),
                  constraints=LinearConstraint(a.tocsr(),lower,upper),
                  options={'time_limit': 20, 'mip_rel_gap': 0})
    if result.status == 2:
        raise PlanError('no_feasible_plan', 'Fuel gap exceeds the 500-mile range including estimated detours.')
    if not result.success:
        raise PlanError('optimizer_limit', 'Optimizer could not prove an optimal plan within 20 seconds.', 503)
    # Solver feasibility tolerance can leave tiny purchases at unused nodes.
    # Only stations on the selected path are actual stops.
    visited = {i for k, (i, j, burn) in enumerate(arcs) if result.x[k] > .5}
    purchases = [(nodes[i], float(result.x[2*m+i])) for i in range(1,n-1)
                 if i in visited and result.x[2*m+i] > 1e-7]
    traveled = sum(burn*10 for k, (_,_,burn) in enumerate(arcs) if result.x[k] > .5)
    return purchases, traveled
