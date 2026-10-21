"""One hourly read-only campaign snapshot; no WB/Telegram writes."""
import os,json
from datetime import datetime,timezone
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from analytics.mpstats_recovery import BIDDER
from china_price_apply import IO
KEY='china_agent:review17_diagnosis:2026-10-21:v1'
SCOPE=[{"article":"144-SamiraBag-brown","nm":"1473245495","barcode":"2042639145019"},{"article":"594-NoelBag-green","nm":"1473243904","barcode":"2048187323879"},{"article":"39-FurManizhka-black","nm":"1560345290","barcode":"2050881014069"},{"article":"52-NoelBag-fuchsia","nm":"1473243825","barcode":"2050815810736"},{"article":"57-NoelBag-burgundy","nm":"1473243909","barcode":"2051011186359"},{"article":"59-NoelBag-grey","nm":"1473243911","barcode":"2051011189411"},{"article":"63-NoelBag-zdarkblue","nm":"1473243915","barcode":"2052007050845"},{"article":"64-NoelBag-zchocolate","nm":"1473243916","barcode":"2052007102391"},{"article":"045-NoelBag-ginger","nm":"1473243895","barcode":"2041312319433"},{"article":"044-NoelBag-black","nm":"1473243894","barcode":"2041312229060"},{"article":"64-Zont-cream-beige","nm":"1556488185","barcode":"2040983897141"},{"article":"61-Zont-blue-pink","nm":"1556488186","barcode":"2041194379839"},{"article":"121-Zont-beige","nm":"1556488209","barcode":"2048374300294"},{"article":"102-Zont-beige","nm":"1556488137","barcode":"2048374249760"},{"article":"3-FurPanama-coffee","nm":"1535337771","barcode":"2045291539974"},{"article":"6-FurPanama-burgundy","nm":"1535337774","barcode":"2045291540000"},{"article":"9-FurPanama-lblue","nm":"1535337777"}]
CIDS=[12282366,12292691,12299447,12301223,12301224]
io=IO();old=io.get(KEY)
if old and old.get('status')=='complete':print('already_collected');raise SystemExit()
if old:raise RuntimeError('Partial audit needs review')
state=dict(status='collecting',cabinet='token_3',started_at=datetime.now(timezone.utc).isoformat(),observations=[],wb_writes=0,telegram_calls=0)
if not io.create(KEY,state):raise RuntimeError('Concurrent audit')
def save(cabinet,obs):
 state['observations'].append(dict(cabinet=cabinet,**obs));io.put(KEY,state)
def reader(call,checks,known):
 mapping=dict(token_3=dict(BIDDER['token_3'],campaign_ids=CIDS))
 requests=[]
 for cid in CIDS:
  requests.append(dict(cabinet='token_3',tool='wbbidder_campaign',arguments=dict(campaign_id=cid),key=KEY+':config:'+str(cid)))
  for start,end in [('2026-10-11','2026-10-14'),('2026-10-17','2026-10-20')]:
   requests.append(dict(cabinet='token_3',tool='wbbidder_campaign_stats',arguments=dict(campaign_id=cid,report='products',d1=start,d2=end),key=KEY+':products:'+str(cid)+':'+start))
 return execute_reads(call,checks,known,requests,mapping,save,max_requests=15)
result=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader)
state['source_status']=result['status']
state['prices']=io.prices([x['nm'] for x in SCOPE])
import requests
skus=[x['barcode'] for x in SCOPE if x.get('barcode')]
response=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':io.token},json={'skus':skus},timeout=40)
if response.status_code!=200:raise RuntimeError('Stock read HTTP '+str(response.status_code))
state['stocks']=response.json();state['stock_observed_at']=datetime.now(timezone.utc).isoformat()
state['status']='complete' if len(state['observations'])==15 and all(x.get('status')=='received' for x in state['observations']) else 'partial'
state['completed_at']=datetime.now(timezone.utc).isoformat();io.put(KEY,state)
print(json.dumps(dict(status=state['status'],observations=len(state['observations']),wb_writes=0,telegram_calls=0)))
