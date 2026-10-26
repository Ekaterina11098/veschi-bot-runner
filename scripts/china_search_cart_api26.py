"""Owner-requested one-off read-only China search funnel. No WB mutations/TG."""
import os,time,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
KEY='china_agent:search_cart_api:2026-10-26:v1'
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(KEY):print('Saved search read exists; no repeat');return
 body=dict(currentPeriod=dict(start='2026-10-20',end='2026-10-26'),pastPeriod=dict(start='2026-10-13',end='2026-10-19'),orderBy=dict(field='avgPosition',mode='asc'),positionCluster='all',includeSubstitutedSKUs=True,includeSearchTexts=True,limit=1000,offset=0)
 state=dict(status='reading',cabinet='token_3',period_from='2026-10-20',period_to='2026-10-26',observed_at=datetime.now(timezone.utc).isoformat(),request=body,wb_writes=0,telegram_calls=0,endpoint='/api/v2/search-report/table/details')
 if not c.create(KEY,state):return
 try:
  r=requests.post('https://seller-analytics-api.wildberries.ru'+state['endpoint'],headers={'Authorization':w.token},json=body,timeout=60)
  state['http_status']=r.status_code
  if not r.ok:
   try:j=r.json()
   except Exception:j={}
   # Keep business error fields only, never headers/requests/tokens.
   state.update(status='unavailable',error={k:str(j[k])[:500].replace(w.token,'[redacted]') for k in ['title','detail','error','message','status','statusText'] if k in j})
   c.put(KEY,state);print('Search API unavailable HTTP '+str(r.status_code));return
  j=r.json();rows=j.get('data',{}).get('products')
  if not isinstance(rows,list):raise RuntimeError('Unknown search report response shape')
  state.update(status='complete' if len(rows)<1000 else 'partial',rows=rows,currency=j.get('data',{}).get('currency'),pagination_complete=len(rows)<1000)
  # Fresh composition only if search data available.
  inv=w.req('/adv/v1/promotion/count')
  ids=sorted({x['advertId'] for g in inv.get('adverts',[]) if g['status'] in [4,9,11] for x in g.get('advert_list',[])})
  campaigns={}
  for pos in range(0,len(ids),50):campaigns.update(w.campaigns(ids[pos:pos+50]))
  state['campaigns']=campaigns;state['completed_at']=datetime.now(timezone.utc).isoformat();c.put(KEY,state)
  print('Search API read complete: '+str(len(rows))+' items. No mutations.')
 except Exception as ex:
  state.update(status='failed',error_type=type(ex).__name__);c.put(KEY,state);raise
if __name__=='__main__':run()
