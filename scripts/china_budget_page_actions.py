"""Bind every displayed budget amount without pretending a conditional reserve is a deposit."""
import copy,math
def owner_policy(io,bundle):
 out=copy.deepcopy(bundle);policy=io.get('china_agent:budget_owner_policy:v1')or{}
 for c in out['campaigns']:
  if str(c['id']) in policy.get('do_not_fund',{}):
   c['owner_budget_refused']=True;c['budget_action']=None
 return out
def page_action(c,bundle):
 if c.get('owner_budget_refused') or bundle.get('view_only'):return None
 if c.get('budget_action'):return copy.deepcopy(c['budget_action'])
 amount=c.get('budget_reserve_amount')
 if c.get('status')!=9 or not c.get('budget_review_required') or type(amount)not in(int,float) or not math.isfinite(amount) or amount<=0:return None
 return dict(id='reserve:'+str(c['id']),kind='approve_budget_reserve',campaign_id=c['id'],amount_cny=int(amount),completed_days=list(bundle.get('budget_days',[])),conditions_reason=c.get('budget_economics_reason')or c.get('budget_short_note')or 'Сначала исполнение рекомендаций и свежая проверка условий.',requires_verified_campaign_changes=True,requires_fresh_balance_and_members=True,requires_remaining_sku_economics=True)
