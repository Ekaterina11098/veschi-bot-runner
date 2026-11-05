"""Read-only confirmation of owner's single manual exclusion. No WB write methods."""
import copy,os,datetime
from ip_apply_nine_20261103 import SixTransport,projection,stamp,HOST
KEY='ip_agent:png17:2026-11-05:v1:manual19-readback'
PARENT='ip_agent:png17:2026-11-05:v1:execution'
class ReadOnly(SixTransport):
 def raw(self,url,headers,method='GET',body=None):
  if url.startswith(HOST) and (method!='GET' or not url.startswith(HOST+'/api/advert/v2/adverts?ids=40192945')):raise PermissionError('Only exact campaign GET allowed')
  return super().raw(url,headers,method,body)
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise PermissionError('Public runner only')
 t=ReadOnly();state=dict(status='reading',run_id=os.environ['GITHUB_RUN_ID'],started_at=stamp(),wb_writes=0,actor='owner_manual',campaign=40192945,nm=493953813)
 if not t.create(KEY,state):return
 def progress(path,until):
  state.update(status='waiting_provider_cooldown',next_allowed_at=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());t.save(KEY,state)
 t.progress=progress
 try:
  t.identity();parent=t.get(PARENT) or {}
  if parent.get('status')!='partial_verified' or len([i for i in parent.get('items',[]) if i['status']=='verified'])!=16:raise ValueError('Prior16 proof missing')
  prior=parent['after']['40192945'];current=t.configs([40192945])['40192945']
  state.update(readback_at=stamp(),after=current,absent=not any(n['nm_id']==493953813 for n in current['nm_settings']))
  expected=copy.deepcopy(prior);expected['nm_settings']=[n for n in expected['nm_settings'] if n['nm_id']!=493953813]
  state['other_campaign_members_settings_unchanged']=projection(current)==projection(expected)
  state['status']='verified' if state['absent'] else 'still_present'
  if state['status']=='verified':
   state['combined_verified_actions']=17
   state['previous16_readback_at']=parent['readback_at']
  t.save(KEY,state)
 except Exception as e:
  state.update(status='attention',error=str(e) if isinstance(e,(ValueError,PermissionError)) else type(e).__name__);t.save(KEY,state)
 finally:
  state['finished_at']=stamp();t.save(KEY,state)
 print({k:v for k,v in state.items() if k!='after'})
 if state['status']!='verified':raise SystemExit(1)
if __name__=='__main__':main()
