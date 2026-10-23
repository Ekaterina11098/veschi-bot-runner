import os,sys,json
from datetime import datetime,timezone
sys.path.insert(0,'scripts')
from china_price_apply import IO
from china_loss_ads import current
from china_ad_rule import minimums
io=IO();out=dict(observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0,minimums={},errors={})
campaigns=current(io,[40933588,40811856]);out['campaigns']=campaigns
for cid,ids in [(40933588,{1473243900,1473243913}),(40811856,{1556488184})]:
 try:out['minimums'][str(cid)]={str(k):v for k,v in minimums(io,cid,ids).items()}
 except Exception as ex:out['errors'][str(cid)]=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__
io.create('china_agent:growth_candidate_minima:2026-10-23:v1',out)
print(json.dumps(out['minimums']));print(json.dumps(out['errors']))
