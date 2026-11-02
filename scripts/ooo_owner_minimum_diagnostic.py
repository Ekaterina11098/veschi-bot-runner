"""Read-only OOO minimum-bid rejection diagnostic. No advertising writes."""
import os,sys,json,time,requests,hashlib,datetime
from pathlib import Path
sys.path.insert(0,str(Path('private-source').resolve()))
from analytics.collect import database
ROOT='ooo_agent:full_ad_plan:2026-11-02:v1'
KEY=ROOT+':minimum_diagnostic'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def get(k):
 r=database('GET','telegram_api_cache',params={'cache_key':'eq.'+k,'select':'payload','limit':1}) or []
 return r[0]['payload'] if r else None
def save(v):
 database('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':KEY,'payload':v,'updated_at':now(),'expires_at':'2036-11-02T00:00:00Z'})
a=get(ROOT+':authorization')
prior=get(KEY)
if prior:print('Existing diagnostic preserved');sys.exit(0)
state=get(ROOT+':apply_all') or {}
if state.get('status')!='attention' or state.get('error')!='WB HTTP 400 at /api/advert/v1/bids/min':raise RuntimeError('Unexpected execution state')
if not a or a.get('status')!='approved' or a.get('cabinet')!='token_1':raise RuntimeError('Owner scope required')
token=os.environ['WB_TOKEN_1'];p='/api/advert/v1/bids/min'
pausekey='wb-pause:'+hashlib.sha256((token+'advert-api.wildberries.ru'+p).encode()).hexdigest()
wait=float((get(pausekey) or {}).get('until',0))-time.time()
if wait>0:save({'status':'cooldown','resume_epoch':time.time()+wait});sys.exit(0)
ids={r['nm'] for r in a['approved_candidates'] if r['group']=='G05' or (r['group']=='G01' and '-Zont-' not in r['article'])}|{851316021}
body=dict(advert_id=39605581,nm_ids=sorted(ids),payment_type='cpc',placement_types=['search','recommendation'])
save({'status':'submitted','started_at':now(),'request':body})
r=requests.post('https://advert-api.wildberries.ru'+p,headers={'Authorization':token},json=body,timeout=(10,60),allow_redirects=False)
try:value=r.json()
except ValueError:value={'message':r.text[:1500]}
save({'status':'received','http_status':r.status_code,'observed_at':now(),'request':body,'response':value,'retry_after':r.headers.get('Retry-After') or r.headers.get('X-Ratelimit-Retry') or r.headers.get('X-Ratelimit-Reset')})
print('Read-only diagnostic saved privately; no WB mutations')
