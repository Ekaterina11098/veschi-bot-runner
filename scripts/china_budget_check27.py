"""Owner-requested one current budget audit. All marketplace calls are reads."""
import os,json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
KEY='china_agent:owner_budget_check:2026-10-27:manual-refresh:v1'
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:raise PermissionError('Budget audit read-only')
  return super().req(path,method,body,write=False)
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 c=Cache()
 if c.get(KEY):print('Audit exists; no repeat reads');return
 w=ReadWB();validate_identity(c,w)
 inv=w.req('/adv/v1/promotion/count')
 ids=sorted({x['advertId'] for g in inv.get('adverts',[]) if g.get('status') in [9,11] for x in g.get('advert_list',[])})
 if not ids or len(ids)>50:raise ValueError('Unexpected campaign scope')
 campaigns=w.campaigns(ids);budgets=w.req('/api/advert/v2/budget','POST',dict(advertIds=ids))
 stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-24&endDate=2026-10-27')
 if {b['advertId'] for b in budgets.get('adverts',[])}!=set(ids) or any(b.get('currency')!='CNY' for b in budgets['adverts']):raise ValueError('Budget currency/scope incomplete')
 rows=[]
 for cid in ids:
  state=campaigns[str(cid)];st=next((s for s in stats if s['advertId']==cid),None)
  days={}
  if st:
   if st.get('currency') not in (None,'CNY'):raise ValueError('Statistics currency mismatch')
   for d in st.get('days',[]):days[d['date'][:10]]={k:d.get(k) for k in ['sum','sum_price','orders','clicks']}
  rows.append(dict(id=cid,name=state['settings']['name'],status=state['status'],placements=state['settings']['placements'],member_count=len(state['nm_settings']),balance=next(b['total'] for b in budgets['adverts'] if b['advertId']==cid),days=days,stats_present=st is not None,started_at=state.get('timestamps',{}).get('started')))
 out=dict(status='complete',observed_at=datetime.now(timezone.utc).isoformat(),period_from='2026-10-24',period_to='2026-10-27',rows=rows,campaigns=campaigns,stats=stats,budgets=budgets,wb_writes=0,telegram_calls=0)
 if not c.create(KEY,out):raise ValueError('Concurrent audit')
 print(json.dumps(dict(status='complete',campaigns=len(rows),wb_writes=0,telegram_calls=0)))
if __name__=='__main__':main()
