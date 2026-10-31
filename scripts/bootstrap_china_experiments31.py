"""Private journal backfill only. No WB/TG/API model credentials or calls."""
import copy,json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache
from china_experiment_journal import ROOT,context,risk_limits
def main():
 c=Cache();key=ROOT+'bootstrap:2026-10-31:v1'
 if c.get(key):return
 class W:
  now=datetime.now(timezone.utc)
  def get(self,k):return c.get(k)
  def save(self,k,v,insert=False):
   if not k.startswith(ROOT):raise ValueError('Outside journal')
   return c.create(k,v)
  def db(self,method,table,params):
   if method!='GET' or table!='telegram_api_cache':raise ValueError('Read-only journal source')
   return c.req('GET',params)
  def catalog(self):return [(str(p['nmID']),p['vendorCode']) for p in (c.get('china_agent:prices:v1')or{}).get('rows',[])]
 journal=context(W(),[1473245494,1473243895,1473243904,1473244337])
 latest=journal['latest_by_nm']
 if latest['1473245494']['kind']!='price' or latest['1473245494']['after']!=495.55:raise ValueError('Latest143 price not verified')
 if latest['1473243895']['kind']!='bid' or latest['1473243895']['after']!=28:raise ValueError('Latest045 bid not verified')
 if latest['1473245494']['window']['first_full_day']!='2026-10-31' or latest['1473243895']['window']['first_full_day']!='2026-11-01':raise ValueError('MSK window mismatch')
 receipt=c.get('china_agent:owner_045_minimum31:v1:execution')
 sample=c.get(ROOT+'scenario:045-cohort')
 price=receipt['prices'][0]['sizes'][0]['discountedPrice']
 cost=receipt['stock']['rows'][0]['price']/100
 q=sample['paid']/sample['finished'];policy=c.get('china_agent:new_ad_economics_policy:v1')
 fx=policy['fx_rub_cny'];shipping=policy['logistics_by_nm']['1473243895']['delivery_cny']
 pre=q*(price*(1-(policy['commission_pct']+policy['tax_pct'])/100)-cost/fx)-shipping-policy['handling_rub']/fx
 limits=risk_limits(pre,q,sample['finished'],bid_cny=.28)
 result=dict(status='verified_private_journal',observed_at=datetime.now(timezone.utc).isoformat(),journal=journal,scenario045=dict(limits=limits,own_cohort_source=sample,fresh_state_source='china_agent:owner_045_minimum31:v1:execution',assumptions=policy,cohort_is_historical=True,not_fresh_recommendation=True),wb_requests=0,telegram_sends=0,grants_action_permission=False)
 if not c.create(key,result) or c.get(key)!=result:raise ValueError('Journal snapshot readback failed')
 print(json.dumps(dict(status=result['status'],journal_events=len(journal['events']),wb_requests=0,telegram_sends=0)))
if __name__=='__main__':main()
