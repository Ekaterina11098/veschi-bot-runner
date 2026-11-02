"""Owner-requested one-off read-only China search funnel. No WB mutations/TG."""
import os,time,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
KEY='china_agent:jam_access_probe:2026-11-02:v1'
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(KEY):print('Saved search read exists; no repeat');return
 body=dict(currentPeriod=dict(start='2026-11-01',end='2026-11-01'),pastPeriod=dict(start='2026-10-31',end='2026-10-31'),orderBy=dict(field='avgPosition',mode='asc'),positionCluster='all',includeSubstitutedSKUs=True,includeSearchTexts=True,limit=1,offset=0)
 state=dict(status='reading',cabinet='token_3',period_from='2026-11-01',period_to='2026-11-01',observed_at=datetime.now(timezone.utc).isoformat(),request=body,wb_writes=0,telegram_calls=0,endpoint='/api/v2/search-report/table/details')
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
  state.update(status='available',row_count=len(rows),completed_at=datetime.now(timezone.utc).isoformat(),grants_action_permission=False)
  c.put(KEY,state)
  if c.get(KEY)!=state:raise RuntimeError('Private receipt readback mismatch')
  print('Jam endpoint access verified; no mutations or TG')
 except Exception as ex:
  state.update(status='failed',error_type=type(ex).__name__);c.put(KEY,state);raise
if __name__=='__main__':run()
