"""Read-only minimum confirmation for one additional unapproved traffic-test candidate."""
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
KEY='china_agent:two_campaign_extra423_proposal:2026-10-28:v1'
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write or (method!='GET' and not(method=='POST' and path=='/api/advert/v1/bids/min')):raise ValueError('Read only')
  return super().req(path,method,body,False)
def main():
 c=Cache()
 if c.get(KEY):return
 w=ReadWB();validate_identity(c,w);out=dict(status='collecting',wb_writes=0,telegram_sends=0,created_at=stamp())
 try:
  parent=c.get('china_agent:owner_two_smalltest_apply28:2026-10-28:v1:execution') or {}
  if parent.get('status')!='verified':raise ValueError('Previous approved execution not verified')
  if (datetime.now(timezone.utc)-datetime.fromisoformat(parent['verified_at'])).total_seconds()>1800:raise ValueError('Preflight source over30minutesold')
  nm=1473242568;cid=41296359;article='423-AndreaBag-blue'
  ec=next(x for x in parent['extra_economics'] if x['nm_id']==nm)
  if ec['status']!='preliminary' or ec['available']<5 or parent['published_stock_by_nm'].get(str(nm),0)<=0:raise ValueError('Own economics or stock unavailable')
  now=w.campaigns([cid])[str(cid)];state=next(n for n in now['nm_settings'] if n['nm_id']==nm)
  if now['status']!=9 or state['bids_kopecks']['recommendations']!=28:raise ValueError('Current state changed')
  minimum=w.minimums(cid,[nm],'recommendations')[nm]
  cfg=parent['config'];step=cfg.get('cpcStep')
  if minimum>31 or type(step)is not int or step<=0 or 31%step or 31>cfg.get('cpcMaxBid',0):raise ValueError('Target outside current minimum/config')
  source=c.get('china_agent:new_ad_source:v1:2026-10-28');p=next(x for x in source['products'] if x['nm_id']==nm)
  log=source['policy']['logistics_by_nm'][str(nm)]['delivery_cny'];price=ec['seller_price_cny']
  profit=.5*(price*(1-p['total_commission_without_spp_in_sales']/100-.05*p['price_after_spp']/p['price_after_discount'])-ec['cogs_kopecks']/1200)-log-10/12-.05*price
  if profit<=0:raise ValueError('Conservative economics nonpositive')
  out.update(status='proposal_only',article=article,nm_id=nm,campaign_id=cid,placement='recommendations',old_minor=28,target_minor=31,minimum_minor=minimum,available_msk=ec['available'],published_wb=parent['published_stock_by_nm'][str(nm)],price_cny=price,conservative_profit_per_order_at5=round(profit,2),scenario_buyout=.5,own_paid=ec['paid'],own_finished=ec['finished'],rating='unconfirmed_no_received_reviews',approval=False,source_parent='china_agent:owner_two_smalltest_apply28:2026-10-28:v1:execution',expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),observed_at=stamp())
 except Exception as e:out.update(status='blocked',reason=str(e) if isinstance(e,(ValueError,RuntimeError)) else type(e).__name__,observed_at=stamp())
 c.put(KEY,out);print(out['status'])
if __name__=='__main__':main()
