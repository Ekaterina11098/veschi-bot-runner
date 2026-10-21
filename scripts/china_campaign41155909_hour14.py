"""One hourly read-only campaign snapshot; no WB/Telegram writes."""
import os,json
from datetime import datetime,timezone
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from analytics.mpstats_recovery import BIDDER
from china_price_apply import IO
KEY='china_agent:campaign_monitor:41155909:2026-10-21T14:v1'
io=IO();old=io.get(KEY)
if old and old.get('status')=='complete':
 print(json.dumps(dict(status='already_collected')));raise SystemExit()
if old:raise RuntimeError('Incomplete hour requires review')
state=dict(status='collecting',campaign_wb_id=41155909,campaign_id=12325936,cabinet='token_3',observations=[],started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0)
if not io.create(KEY,state):raise RuntimeError('Concurrent snapshot')
def save(cabinet,obs):
 state['observations'].append(dict(cabinet=cabinet,**obs));io.put(KEY,state)
def reader(call,checks,known):
 mapping=dict(token_3=dict(BIDDER['token_3'],campaign_ids=[12325936]))
 requests=[]
 for tool,args in [('wbbidder_campaign',dict(campaign_id=12325936)),('wbbidder_campaign_stats',dict(campaign_id=12325936,report='days',d1='2026-10-20',d2='2026-10-21')),('wbbidder_campaign_stats',dict(campaign_id=12325936,report='products',d1='2026-10-21',d2='2026-10-21'))]:
  requests.append(dict(cabinet='token_3',tool=tool,arguments=args,key=KEY+':'+tool+':'+args.get('report','config')))
 return execute_reads(call,checks,known,requests,mapping,save,max_requests=3)
result=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader)
if len(state['observations'])!=3 or any(x.get('status')!='received' for x in state['observations']):
 state['status']='partial';state['source_status']=result['status'];io.put(KEY,state);raise RuntimeError('Hourly source incomplete')
c=state['observations'][0]['data'];settings=c.get('campaign',{}).get('settings') or []
if c.get('campaign',{}).get('wb_id')!=41155909 or c.get('budget',{}).get('currency')!='CNY' or {x['nm'] for s in settings for x in s.get('skus',[])}!={1473243898}:raise RuntimeError('Campaign scope changed')
state['current_price']=io.prices(['1473243898'])['1473243898']
if state['current_price']['vendorCode']!='119-NoelBag-darkblack' or state['current_price']['currencyIsoCode4217']!='CNY':raise RuntimeError('Price scope mismatch')
state['status']='complete';state['completed_at']=datetime.now(timezone.utc).isoformat();io.put(KEY,state)
print(json.dumps(dict(status='complete',observations=3,wb_writes=0,telegram_calls=0)))
