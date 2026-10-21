import os,json
from datetime import datetime,timezone
from china_price_apply import IO
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from analytics.mpstats_recovery import BIDDER
io=IO();KEY='china_agent:seven_ad_diagnosis:2026-10-21:reads:v1'
state=io.get(KEY) or dict(status='collecting',observations=[],started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0)
if state.get('status')=='complete':print('already_collected');raise SystemExit()
if not io.get(KEY):io.create(KEY,state)
scope=[{"article":"122-EmraBag-red","nm":1473244336,"pid":149503459,"campaign_id":12314326},{"article":"552-AriadnaBag-brown","nm":1473243454,"pid":149503403,"campaign_id":12314326},{"article":"53-NoelBag-beige","nm":1473243826,"pid":149503417,"campaign_id":12299447},{"article":"604-SamiraBag-grey","nm":1473245512,"pid":149503530,"campaign_id":12299447},{"article":"688-PaolaBag-chocolate","nm":1473243098,"pid":149503385,"campaign_id":12314326},{"article":"545-GazelBag-darkbrown","nm":1473243452,"pid":149503401,"campaign_id":12314326},{"article":"626-AudreyBag-brown","nm":1473245003,"pid":149503505,"campaign_id":12299447}]
requests=[]
for cid in [12299447,12314326]:
 requests.append(dict(cabinet='token_3',tool='wbbidder_campaign',arguments=dict(campaign_id=cid),key=KEY+':config:'+str(cid)))
 for zone in ['search','recommendations']:
  requests.append(dict(cabinet='token_3',tool='wbbidder_campaign_stats',arguments=dict(campaign_id=cid,report='products',zone=zone,d1='2026-09-21',d2='2026-10-20'),key=KEY+':products:'+str(cid)+':'+zone))
for p in scope:
 requests.append(dict(cabinet='token_3',tool='wbbidder_clusters',arguments=dict(campaign_id=p['campaign_id'],nm_id=p['nm'],report='clusters',d1='2026-09-21',d2='2026-10-20',limit=100,sort='spending'),key=KEY+':clusters:'+str(p['nm'])))
done={x['request_key'] for x in state['observations'] if x.get('status')=='received'}
def save(cabinet,obs):
 state['observations']=[x for x in state['observations'] if x['request_key']!=obs['request_key']]+[dict(cabinet=cabinet,**obs)];io.put(KEY,state)
def reader(call,checks,known):
 return execute_reads(call,checks,known,[r for r in requests if r['key'] not in done],dict(token_3=dict(BIDDER['token_3'],campaign_ids=[12299447,12314326])),save,max_requests=13)
r=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader)
state['status']='complete' if len(state['observations'])==len(requests) and all(x['status']=='received' for x in state['observations']) else 'partial'
state['completed_at']=datetime.now(timezone.utc).isoformat();state['source_status']=r['status'];io.put(KEY,state)
print(json.dumps(dict(status=state['status'],reads=len(state['observations']),wb_writes=0,telegram_calls=0)))
