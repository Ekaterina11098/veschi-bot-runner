import os,json,time,requests
from datetime import datetime,timezone
from urllib.parse import quote
from china_moysklad_read import read_stock
ROOT='china_agent:owner_two_budget_review:2026-11-12:v1:inputs'
SCOPE=[1473246056,1594295903,1473243442,1473243912,1473244000,1473244344,1473244989,1473246032,1473243827,1473243893,1473243895,1473244345,1473244988,1473245505,1473242579,1473244985,1473246039,1473246054,1473242577,1473243934,1473243937,1473244986,1473244987,1473246045,1473246055,1473242578,1473242756,1473242769,1473245001,1473245005,1473245007,1473246040,1473246042,1473242581,1473242761,1473242767,1473243935,1473243936,1473245008,1473246041,1473246043,1473242576,1473244983,1473246049,1473243891,1473242586,1473244340]
CHAT=-1004342917488
base=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'
key=os.environ['SUPABASE_SECRET_KEY'];sh={'apikey':key,'Content-Type':'application/json'}
if not key.startswith('sb_secret_'):sh['Authorization']='Bearer '+key
def dbget(path):
 r=requests.get(base+path,headers=sh,timeout=45,allow_redirects=False);r.raise_for_status();return r.json()
if dbget('telegram_api_cache?cache_key=eq.'+quote(ROOT,safe='')+'&select=cache_key'):
 print('Frozen exact result already exists; no repeated reads');raise SystemExit()
token=os.environ['WB_TOKEN_3']
def read(host,path,method='GET',body=None):
 if (host,path.split('?')[0],method) not in [('https://advert-api.wildberries.ru','/api/advert/v2/adverts','GET'),('https://advert-api.wildberries.ru','/api/advert/v2/budget','POST'),('https://discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter','GET')]:raise ValueError('Read route denied')
 time.sleep(1)
 r=requests.request(method,host+path,headers={'Authorization':token},json=body,timeout=60,allow_redirects=False)
 if not r.ok:raise ValueError('WB read HTTP '+str(r.status_code))
 j=r.json()
 if isinstance(j,dict)and j.get('error'):raise ValueError('WB read rejected')
 return j.get('data',j)if isinstance(j,dict)else j
campaigns=read('https://advert-api.wildberries.ru','/api/advert/v2/adverts?ids=41332083,41296363')
states=campaigns.get('adverts',campaigns if isinstance(campaigns,list)else [])
assert {c['id']for c in states}=={41332083,41296363}
assert {n['nm_id']for c in states for n in c['nm_settings']}<=set(SCOPE),'Campaign composition changed beyond explicit scope'
budgets=read('https://advert-api.wildberries.ru','/api/advert/v2/budget','POST',dict(advertIds=[41332083,41296363]))
goods=read('https://discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter?limit=1000&offset=0')['listGoods']
assert len(goods)<1000,'Price pagination incomplete'
prices=[p for p in goods if p['nmID']in SCOPE]
assert {p['nmID']for p in prices}==set(SCOPE)
assert all(p.get('currencyIsoCode4217')=='CNY'and p.get('editableSizePrice')is False for p in prices)
stock=read_stock([p['vendorCode']for p in prices]);assert stock['coverage_complete']
at=datetime.now(timezone.utc).isoformat()
payload=dict(status='verified',observed_at=at,campaigns=states,budgets=budgets,prices=prices,stock=stock,scope_nm_ids=SCOPE,wb_writes=0,moysklad_writes=0,telegram_calls=0,model_calls=0,run_id=os.environ['GITHUB_RUN_ID'])
r=requests.post(base+'telegram_api_cache?on_conflict=cache_key',headers={**sh,'Prefer':'resolution=ignore-duplicates,return=minimal'},json=dict(cache_key=ROOT,payload=payload,updated_at=at,expires_at='2036-11-12T00:00:00Z'),timeout=45);r.raise_for_status()
print('Two-campaign read-only preflight saved privately; no mutations or sends')
