"""One read of the newly completed day; never WB writes."""
import os,json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:full_experiment_review:2026-10-31:day30'
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:raise ValueError('Read only')
  return super().req(path,method,body,False)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache()
 if c.get(ROOT):print('Existing observation preserved');return
 q=c.get('china_agent:full_experiment_review:2026-10-30:v2:read_request')or{}
 if q.get('status')!='approved_read_only' or q.get('owner_user_id')!=5122667182 or datetime.now(timezone.utc)>=datetime.fromisoformat(q['expires_at']):raise ValueError('Read authorization expired')
 previous=c.get('china_agent:full_experiment_review:2026-10-30:v2:snapshot')or{}
 ids=previous.get('stats_campaign_ids',[])
 if len(ids)!=20 or len(set(ids))!=20:raise ValueError('Historical cohort mismatch')
 w=ReadWB();validate_identity(c,w)
 stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,sorted(ids)))+'&beginDate=2026-10-30&endDate=2026-10-30')
 if not isinstance(stats,list):raise ValueError('Statistics response invalid')
 value={'status':'observed','observed_at':stamp(),'period_from':'2026-10-30','period_to':'2026-10-30','stats':stats,'requested_ids':ids,'reported_ids':[s['advertId']for s in stats],'missing_campaigns':sorted(set(ids)-{s['advertId']for s in stats}),'cabinet':'token_3','wb_writes':0,'telegram_calls':0,'limitation':'First observation just after calendar close; attribution may still revise.'}
 if not c.create(ROOT,value):raise ValueError('Read observation collision')
 print(json.dumps({'status':'observed','wb_writes':0,'telegram_calls':0,'campaign_rows':len(stats)}))
if __name__=='__main__':run()
