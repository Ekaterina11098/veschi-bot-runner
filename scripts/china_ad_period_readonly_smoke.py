import os,json,sys
sys.path[:0]=['scripts','source']
from conversion_watches import runtime,saved_network_guard
from china_ad_rule import reads,minimums
from china_loss_ads import current
from china_price_apply import IO
w=runtime()
with saved_network_guard():
 with reads() as scope:
  io=IO();campaigns=current(io);scope.update({cid:{n['nm_id'] for n in c.get('nm_settings',[])} for cid,c in campaigns.items()});mins={}
  for cid,c in campaigns.items():
   if c.get('status')!=9 or c.get('currency')!='CNY' or c.get('settings',{}).get('payment_type')!='cpc':continue
   ids=sorted(scope[cid]);out={}
   for start in range(0,len(ids),100):out.update(minimums(io,cid,set(ids[start:start+100])))
   mins[str(cid)]={str(nm):v for nm,v in out.items()}
  result=dict(status='verified_readonly',observed_at=w.now.isoformat(),campaigns={str(cid):c for cid,c in campaigns.items()},minimums=mins,wb_writes=0,telegram_calls=0)
  w.save('china_agent:all_campaign_minima:2026-10-23:v1',result)
print(json.dumps(dict(status=result['status'],campaigns=len(campaigns),minimum_skus=sum(len(v) for v in mins.values()),wb_writes=0,telegram_calls=0)))
