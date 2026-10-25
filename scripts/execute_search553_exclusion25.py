"""Execute one exact human-approved search SKU exclusion; journal and verify."""
import os,time,json,requests
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO();K='china_agent:codex_search_exclude553:2026-10-25:v1';E=K+':execution'
assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
p=io.get(K)
assert p['source']=='explicit_human_codex_message' and p['status']=='approved'
assert p['campaign_id']==41298169 and p['nm_id']==1473243455
assert datetime.now(timezone.utc)<datetime.fromisoformat(p['expires_at'])
def get():
 r=requests.get('https://advert-api.wildberries.ru/api/advert/v2/adverts?ids=41298169',headers={'Authorization':io.token},timeout=50);r.raise_for_status()
 a=r.json()['adverts'];assert len(a)==1 and a[0]['id']==41298169
 return a[0]
def members(c):return {n['nm_id'] for n in c['nm_settings']}
e=io.get(E)
if e and e.get('status')=='verified':
 print(json.dumps(dict(status='already_verified',wb_writes=0)));raise SystemExit()
c=get()
assert c['currency']=='CNY' and c['settings']['placements']==dict(search=True,recommendations=False)
if e:
 assert e['status'] in ['submitting','accepted','uncertain']
 assert members(c)==set(e['before_members'])-{1473243455},'Uncertain execution; do not retry PATCH'
else:
 assert 1473243455 in members(c)
 e=dict(status='submitting',campaign_id=41298169,nm_id=1473243455,before_members=sorted(members(c)),before=c,started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
 assert io.create(E,e)
 try:
  r=requests.patch('https://advert-api.wildberries.ru/adv/v0/auction/nms',headers={'Authorization':io.token},json=dict(nms=[dict(advert_id=41298169,nms=dict(add=[],delete=[1473243455]))]),timeout=50)
  e.update(http=r.status_code,status='accepted' if r.ok else 'rejected',wb_writes=1);io.put(E,e)
  r.raise_for_status()
 except Exception:
  if e['status']=='submitting':e['status']='uncertain';io.put(E,e)
  raise
 for _ in range(8):
  time.sleep(4);c=get()
  if 1473243455 not in members(c):break
 assert members(c)==set(e['before_members'])-{1473243455}
assert c['status']==e['before']['status']
assert {n['nm_id']:n['bids_kopecks'] for n in c['nm_settings']}=={n['nm_id']:n['bids_kopecks'] for n in e['before']['nm_settings'] if n['nm_id']!=1473243455}
e.update(status='verified',after=c,verified_at=datetime.now(timezone.utc).isoformat(),telegram_sends=0);io.put(E,e)
t=io.get('china_agent:search_test:2026-10-25:tracking:v1')
if t:
 t.setdefault('owner_changes',[]).append(dict(kind='sku_exclusion',campaign_id=41298169,nm_id=1473243455,execution_key=E,verified_at=e['verified_at']))
 io.put('china_agent:search_test:2026-10-25:tracking:v1',t)
print(json.dumps(dict(status='verified',remaining_count=len(members(c)),wb_writes=e['wb_writes'])))
