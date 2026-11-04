"""Bind every displayed budget amount without pretending a conditional reserve is a deposit."""
import copy,math
def owner_policy(io,bundle):
 out=copy.deepcopy(bundle);policy=io.get('china_agent:budget_owner_policy:v1')or{}
 for c in out['campaigns']:
  if str(c['id']) in policy.get('do_not_fund',{}):
   c['owner_budget_refused']=True;c['budget_action']=None
 return out
def page_action(c,bundle):
 """A displayed reserve is a recommendation, never an implied amount approval."""
 if c.get('owner_budget_refused')or bundle.get('view_only'):return None
 action=c.get('budget_action')
 return copy.deepcopy(action)if action and action.get('kind')=='topup_campaign'else None
