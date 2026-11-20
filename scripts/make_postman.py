import json
from pathlib import Path
routes=[('Short route (live verification pending)',{'start':{'latitude':41.8781,'longitude':-87.6298},'finish':{'latitude':43.0389,'longitude':-87.9065}}),
 ('Multi-stop route (live verification pending)',{'start':{'latitude':40.7608,'longitude':-111.891},'finish':{'latitude':41.8781,'longitude':-87.6298}}),
 ('Text endpoints',{'start':'Chicago, IL','finish':'Milwaukee, WI'}),
 ('Outside USA (expect 400)',{'start':{'latitude':51.5074,'longitude':-.1278},'finish':'Chicago, IL'})]
items=[]
for name,body in routes:
    items.append({'name':name,'request':{'method':'POST','header':[{'key':'Content-Type','value':'application/json'}],'body':{'mode':'raw','raw':json.dumps(body,indent=2),'options':{'raw':{'language':'json'}}},'url':'{{base_url}}/api/route-plan/'},'event':[{'listen':'test','script':{'type':'text/javascript','exec':['const data = pm.response.json();','pm.test("Structured response", () => pm.expect(data).to.have.property("upstream_calls"));','if (pm.response.code === 200) {','  pm.test("Call budget", () => pm.expect(data.upstream_calls).to.be.at.most(3));','  pm.test("Costs reconcile", () => {','    const cents = data.fuel_stops.reduce((n,s) => n + Math.round(Number(s.stop_cost)*100), 0);','    pm.expect(Math.round(Number(data.total_fuel_spend_usd)*100)).to.eql(cents);','  });','}']}}]})
collection={'info':{'name':'Spotter Fuel Route Planner','description':'Local assessment API. Live routes require imported matched stations, US boundary and ORS key. Examples marked MOCKED are illustrative only.','schema':'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'},'variable':[{'key':'base_url','value':'http://127.0.0.1:8000'}],'item':items}
Path('postman').mkdir(exist_ok=True)
Path('postman/Spotter.postman_collection.json').write_text(json.dumps(collection,indent=2),encoding='utf-8')
