"""Bind every displayed budget amount without pretending a conditional reserve is a deposit."""
import copy,math
def owner_policy(io,bundle):
 out=copy.deepcopy(bundle);policy=io.get('china_agent:budget_owner_policy:v1')or{}
 for c in out['campaigns']:
  if str(c['id']) in policy.get('do_not_fund',{}):
   c['owner_budget_refused']=True;c['budget_action']=None
   c.update(budget_audit_state='owner_hold',budget_review_required=False,budget_short_note='Не пополнять: '+str(policy['do_not_fund'][str(c['id'])]))
   if str(c['id'])in out.get('budget_audit',{}):out['budget_audit'][str(c['id'])].update(status='owner_hold',review_required=False,amount_cny=None,reason=c['budget_short_note'])
 return out
def page_action(c,bundle):
 """A displayed reserve is a recommendation, never an implied amount approval."""
 if bundle.get('view_only'):return None
 if (c.get('financial_action')or{}).get('kind')=='recover_campaign':return dict(copy.deepcopy(c['financial_action']),selection_family='budgets')
 if c.get('owner_budget_refused'):return None
 action=c.get('budget_action')
 return copy.deepcopy(action)if action and action.get('kind')=='topup_campaign'else None


