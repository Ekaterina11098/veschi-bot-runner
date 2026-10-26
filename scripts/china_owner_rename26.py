"""One-off owner-authorized renaming of two China search campaigns."""
import os,json,copy,time,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
KEY='china_agent:owner_rename:2026-10-26:v1:execution'
PLAN={41325637:('Китай поиск 26.10 · 61 · owner21','Китай · Поиск · Зонты · 26.10'),41325622:('Китай поиск 26.10 · 255 · owner21','Китай · Поиск · Панамы · 26.10')}
def stable(c):
 c=copy.deepcopy(c);c.pop('timestamps',None);c['settings'].pop('name',None)
 c['nm_settings']=sorted(c['nm_settings'],key=lambda n:n['nm_id'])
 return c
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 cache=Cache();wb=WB();validate_identity(cache,wb)
 if cache.get(KEY):raise RuntimeError('Receipt exists: no repeat writes')
 before=wb.campaigns(list(PLAN))
 for cid,(old,new) in PLAN.items():
  b=before[str(cid)]
  if b['currency']!='CNY' or b['settings']['name']!=old or b['settings']['placements']!={'search':True,'recommendations':False}:raise RuntimeError('Exact campaign scope changed')
 e=dict(status='prepared',owner_id=5122667182,owner_quote='отредактируй на понятные названия',created_at=datetime.now(timezone.utc).isoformat(),before=before,steps={},telegram_sends=0)
 if not cache.create(KEY,e):raise RuntimeError('Concurrent rename')
 try:
  for cid,(old,new) in PLAN.items():
   e['steps'][str(cid)]=dict(status='sending',old=old,new=new);cache.put(KEY,e)
   time.sleep(1.5)
   r=requests.post('https://advert-api.wildberries.ru/adv/v0/rename',headers={'Authorization':wb.token},json={'advertId':cid,'name':new},timeout=55)
   if not r.ok:raise RuntimeError('Rename HTTP '+str(r.status_code))
   e['steps'][str(cid)]['status']='accepted';cache.put(KEY,e)
  after=wb.campaigns(list(PLAN))
  for cid,(old,new) in PLAN.items():
   b=before[str(cid)];a=after[str(cid)]
   if a['settings']['name']!=new or stable(a)!=stable(b):raise RuntimeError('Readback mismatch')
   child=KEY+':'+str(cid)
   cache.put(child,dict(status='verified',before=b,after=a,items=[dict(kind='rename',old=old,new=new)],verified_at=datetime.now(timezone.utc).isoformat()))
   reg=cache.get('china_agent:verified_campaign_state:v1') or {};reg[str(cid)]=child;cache.put('china_agent:verified_campaign_state:v1',reg)
   e['steps'][str(cid)]['status']='verified'
  e.update(status='verified',after=after,verified_at=datetime.now(timezone.utc).isoformat());cache.put(KEY,e)
  print('Two campaign names verified; all other campaign settings preserved.')
 except Exception as exc:
  e.update(status='uncertain',error=type(exc).__name__+': '+str(exc));cache.put(KEY,e);raise
if __name__=='__main__':run()
