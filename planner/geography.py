import json
import math
from functools import lru_cache
from django.conf import settings
from .errors import PlanError


@lru_cache(maxsize=1)
def us_boundary():
    path = settings.BASE_DIR / 'data/us_boundary.geojson'
    if not path.exists():
        raise PlanError('boundary_missing', 'Run python manage.py prepare_boundary first.', 503)
    return json.loads(path.read_text())['geometry']


def in_ring(lon,lat,ring):
    inside=False
    for a,b in zip(ring,ring[1:]):
        x1,y1=a[:2];x2,y2=b[:2]
        if min(x1,x2)<=lon<=max(x1,x2) and min(y1,y2)<=lat<=max(y1,y2) and abs((lon-x1)*(y2-y1)-(lat-y1)*(x2-x1))<1e-12:
            return True
        if (y1>lat)!=(y2>lat) and lon<(x2-x1)*(lat-y1)/(y2-y1)+x1:
            inside=not inside
    return inside


def validate_us(lon, lat):
    geometry=us_boundary()
    polygons=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
    if not any(in_ring(lon,lat,polygon[0]) and not any(in_ring(lon,lat,hole) for hole in polygon[1:]) for polygon in polygons):
        raise PlanError('outside_us', 'Endpoint must be within the United States land boundary.', 400)
    return [lon, lat]


def haversine(a,b):
    lon1,lat1,lon2,lat2 = map(math.radians, (*a,*b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 3958.7613 * 2 * math.asin(min(1, math.sqrt(h)))


def nearby_stations(coords, distance, stations, corridor, factor):
    """Project on every segment, not just vertices; scale chainage to ORS miles.

    Local equirectangular projection per segment; nearest occurrence only.
    Intended for ordinary road segments, not antimeridian routes.
    """
    from .optimizer import Stop
    import numpy as np
    points=np.array(coords,dtype=float)[:,:2]; a=points[:-1]; b=points[1:]
    lengths=np.array([haversine(x,y) for x,y in zip(a,b)])
    total = float(sum(lengths))
    if total <= 0:
        raise PlanError('invalid_route', 'Provider returned a zero-length geometry.', 502)
    cumulative=np.r_[0,np.cumsum(lengths)[:-1]]
    scales=np.cos(np.radians((a[:,1]+b[:,1])/2))
    bx=(b[:,0]-a[:,0])*scales; by=b[:,1]-a[:,1]
    squared=bx*bx+by*by
    candidates, details = [], {}
    for station in stations:
        px=(station.longitude-a[:,0])*scales; py=station.latitude-a[:,1]
        t=np.clip(np.divide(px*bx+py*by,squared,out=np.zeros_like(squared),where=squared>0),0,1)
        projected=a+t[:,None]*(b-a)
        rad=np.radians(projected); lon,lat=map(math.radians,(station.longitude,station.latitude))
        h=np.sin((rad[:,1]-lat)/2)**2+np.cos(lat)*np.cos(rad[:,1])*np.sin((rad[:,0]-lon)/2)**2
        off=3958.7613*2*np.arcsin(np.sqrt(np.clip(h,0,1)))
        idx=int(np.argmin(off))
        best=(float(off[idx]),float((cumulative[idx]+t[idx]*lengths[idx])*distance/total),projected[idx].tolist())
        if best[0] <= corridor and 0 < best[1] < distance:
            candidates.append(Stop(station.opis_id,best[1],float(station.price),best[0]*factor))
            details[station.opis_id] = (station,best[2])
    return candidates, details
