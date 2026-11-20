"""Require an explicit US state so country-filtered searches cannot silently
reinterpret an explicitly foreign address as a similarly named US place.
"""
import re
from .errors import PlanError

STATE_NAMES = dict(pair.split(':') for pair in (
    'AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|'
    'CT:Connecticut|DE:Delaware|FL:Florida|GA:Georgia|HI:Hawaii|ID:Idaho|'
    'IL:Illinois|IN:Indiana|IA:Iowa|KS:Kansas|KY:Kentucky|LA:Louisiana|'
    'ME:Maine|MD:Maryland|MA:Massachusetts|MI:Michigan|MN:Minnesota|'
    'MS:Mississippi|MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|'
    'NH:New Hampshire|NJ:New Jersey|NM:New Mexico|NY:New York|'
    'NC:North Carolina|ND:North Dakota|OH:Ohio|OK:Oklahoma|OR:Oregon|'
    'PA:Pennsylvania|RI:Rhode Island|SC:South Carolina|SD:South Dakota|'
    'TN:Tennessee|TX:Texas|UT:Utah|VT:Vermont|VA:Virginia|WA:Washington|'
    'WV:West Virginia|WI:Wisconsin|WY:Wyoming|DC:District of Columbia'
).split('|'))


def input_state(text):
    parts=[part.strip().casefold() for part in text.split(',')]
    if parts[-1] in ('us','usa','united states','united states of america'):
        parts.pop()
    if len(parts)<2:
        raise PlanError('ambiguous_location','Include city and US state, separated by a comma.',400)
    state=re.sub(r'\s+\d{5}(?:-\d{4})?$','',parts[-1])
    for code,name in STATE_NAMES.items():
        if state in (code.casefold(),name.casefold()):return code
    raise PlanError('invalid_us_state','End the address with a valid US state name or abbreviation, optionally ZIP and USA.',400)
