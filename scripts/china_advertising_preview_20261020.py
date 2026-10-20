"""China advertising preview: read-only collection, no WB/Telegram mutations."""
import os,json,copy
from datetime import datetime,timedelta,timezone
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from analytics.mpstats_recovery import BIDDER
from china_price_apply import IO
KEY='china_agent:advertising_preview:2026-10-20:v1'
def main():
 io=IO();old=io.get(KEY)
 if old and old.get('status')=='complete':print(json.dumps(dict(status='already_collected',key=KEY,observations=len(old['observations']))));return
 now=datetime.now(timezone.utc);end='2026-10-19';start='2026-10-13'
 state=dict(status='collecting',cabinet='token_3',observed_at=now.isoformat(),period_from=start,period_to=end,observations=[],wb_writes=0,telegram_calls=0)
 if old:raise RuntimeError('Existing incomplete collection requires review, not blind rerun')
 if not io.create(KEY,state):raise RuntimeError('Concurrent collection')
 def save(cabinet,obs):
  state['observations'].append(dict(cabinet=cabinet,**obs));io.put(KEY,state)
 def req(tool,args):return dict(cabinet='token_3',tool=tool,arguments=args,key='china-preview:'+tool+':'+json.dumps(args,sort_keys=True))
 def reader(call,checks,known):
  mapping=dict(token_3=dict(BIDDER['token_3'],campaign_ids=[]))
  execute_reads(call,checks,known,[dict(cabinet='shared',tool='wbbidder_cabinets',arguments={},key='china-preview:cabinets')],mapping,save,max_requests=1)
  obs=state['observations'][-1]
  if obs.get('status')!='received':raise RuntimeError('Cabinets not received')
  body=obs['data'];cabs=body if isinstance(body,list) else body.get('data',[])
  exact=[x for x in cabs if x.get('id')==939742]
  if len(exact)!=1 or exact[0].get('name')!='VESCHI Гонконг':raise RuntimeError('China advertising cabinet mismatch')
  state['identity']=exact[0];io.put(KEY,state)
  requests=[]
  for report,a,b in [('state',start,end),('stats',end,end),('stats',start,end)]:
   args=dict(tokens=[939742],report=report,limit=100,start_row=0,bidder_only=False,sort='wb_id',sort_dir='asc')
   if report=='stats':args.update(d1=a,d2=b)
   requests.append(req('wbbidder_campaigns',args))
  execute_reads(call,checks,known,requests,mapping,save,max_requests=3)
  lists=[x for x in state['observations'] if x['tool']=='wbbidder_campaigns']
  if len(lists)!=3 or any(x.get('status')!='received' for x in lists):raise RuntimeError('Catalogue requests incomplete')
  ids=set()
  for obs in lists:
   data=obs['data'];rows=data.get('data')
   if not isinstance(rows,list) or data.get('total')!=len(rows) or len(rows)!=data.get('returned'):raise RuntimeError('Catalogue pagination incomplete')
   ids.update(x['id'] for x in rows)
  mapping['token_3']['campaign_ids']=sorted(ids);state['campaign_ids']=sorted(ids);io.put(KEY,state)
  pending=[]
  for cid in sorted(ids):
   pending.extend([req('wbbidder_campaign',dict(campaign_id=cid)),req('wbbidder_campaign_stats',dict(campaign_id=cid,report='days',d1=start,d2=end)),req('wbbidder_campaign_stats',dict(campaign_id=cid,report='products',d1=end,d2=end))])
  state['expected_requests']=len(pending);io.put(KEY,state)
  return execute_reads(call,checks,known,pending,mapping,save,max_requests=120)
 result=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader)
 complete=(result.get('connected') is True and len(state['observations'])==4+state.get('expected_requests',-100) and all(x.get('status')=='received' for x in state['observations']))
 state['status']='complete' if complete else 'partial';state['discovery_status']=result.get('status');state['completed_at']=datetime.now(timezone.utc).isoformat();io.put(KEY,state)
 print(json.dumps(dict(status=state['status'],key=KEY,observations=len(state['observations']),campaigns=len(state.get('campaign_ids',[])),wb_writes=0,telegram_calls=0)))
if __name__=='__main__':main()
