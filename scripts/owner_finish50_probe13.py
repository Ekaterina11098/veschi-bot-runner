"""Owner13Nov: inspect only remaining confirmed addition/funding. No mutations."""
import json,os
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
ROOT='china_agent:owner_finish50_funding:2026-11-13:v1'
def main():
 c=Cache();w=WB();validate_identity(c,w)
 out=dict(observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0)
 out['campaigns']=w.campaigns([40933588,41055480,41332083])
 try:out['target_quote']=w.minimums(41332083,[1473243824],'search')
 except Exception as e:out['quote_error']=str(e)
 out['budgets']=w.req('/api/advert/v2/budget','POST',dict(advertIds=[40933588,41055480,40964981,41270309,41298169]))
 c.put(ROOT+':probe',out)
 print(json.dumps(dict(status='readback_saved',quote=out.get('target_quote'),quote_error=out.get('quote_error'),wb_writes=0)))
if __name__=='__main__':main()
