"""Describe sales-growth hypotheses separately from reserve maintenance; no execution."""
import copy

def attach(bundle):
 out=copy.deepcopy(bundle);directions=out.get('recommendation_directions',{})
 ready={key:[copy.deepcopy(r)for r in directions.get(key,{}).get('rows',[])if r.get('ready')is True and r.get('action')]for key in ['raise','add','reduce','exclude']}
 full=out.get('full_cabinet_growth_review')or out.get('growth_review')or{}
 complete=full.get('status')=='complete' and all(directions.get(k,{}).get('status')!='unavailable'for k in ['raise','add'])
 out['sales_growth_review']=dict(status='complete'if complete else'incomplete',growth=ready['raise']+ready['add'],cost_control=ready['reduce']+ready['exclude'],budget_support=[copy.deepcopy(c['budget_action'])for c in out['campaigns']if c.get('budget_action')],funding_is_growth=False,causal_sales_lift_proven=False,execution_authorized=False,scope=full,empty_growth_means_no_ready_proposal=complete)
 return out
