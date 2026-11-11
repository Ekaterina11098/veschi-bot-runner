"""Final reviewed budget recommendations; never a marketplace permission."""
import copy
def apply_review(bundle):
 review=bundle.get('owner_final_budget_review')or{}
 if review.get('owner_id')!=5122667182:return bundle
 out=copy.deepcopy(bundle)
 for c in out['campaigns']:
  selected=review.get('campaigns',{}).get(str(c['id']))
  if not selected:continue
  if selected['decision']=='no_fund':
   c.update(budget_action=None,budget_reserve_amount=None,budget_review_required=True,budget_audit_state='owner_decided_no_fund',budget_short_note=selected['text'],budget_recommendation=selected['text'])
   if selected.get('reference_cny')is not None:
    c.update(budget_reference_need=selected['reference_cny'],budget_cash_gap=max(0,selected['reference_cny']-c['balance']),budget_average_daily=selected['reference_cny']/3)
   if selected.get('hide'):c['budget_review_required']=False
  elif selected['decision']=='limited_test_topup':
   e=copy.deepcopy(selected['evidence']);assert e['status']=='positive'and e['ready']and e['stress_after_ads_cny']>0
   a=copy.deepcopy(selected['action']);assert a['kind']=='topup_campaign'and a['campaign_id']==c['id']and a['amount_cny']>0
   c.update(budget_action=a,budget_reserve_amount=a['amount_cny'],budget_reference_need=selected['reference_cny'],budget_cash_gap=max(0,selected['reference_cny']-c['balance']),budget_average_daily=selected['reference_cny']/3,budget_review_required=True,budget_audit_state='topup_ready',budget_short_note=selected['text'],budget_economics_status='positive',campaign_budget_economics=e)
  else:raise ValueError('Unknown final budget decision')
 return out
