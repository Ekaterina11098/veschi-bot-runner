"""Reconcile only WB-verified changes selected in the companion report by the same human."""
import copy,hashlib
def reconcile(io,evidence,before):
 from china_loss_control import PLAN,APPROVAL
 from china_execution_notice import proven
 p=getattr(io,'daily_report_plan',{});a=getattr(io,'daily_report_approval',{})
 def base(v):return v.get('report_generation','').removesuffix('-'+v.get('family',''))
 pointer=io.get('china_agent:daily_ad_current_report:v1:drr')or{};parent=io.get(PLAN+pointer.get('plan_id',''))or{}
 if not a.get('sender_id')or not base(p)or base(parent)!=base(p)or parent.get('period_to')!=p.get('period_to'):raise ValueError('Composition changed outside the confirmed report pair')
 token=hashlib.sha256((parent['plan_id']+':'+parent['plan_sha256']+':drr').encode()).hexdigest()[:24]+'-'+str(a['sender_id'])
 c=io.get('china_agent:report_buttons:v1:confirmation:'+token)or{}
 if c.get('status')!='confirmed'or c.get('sender_id')!=a['sender_id']or c.get('plan_sha256')!=parent['plan_sha256']:raise ValueError('Companion human confirmation missing')
 child=io.get(PLAN+parent['plan_id']+'-buttons-'+token)or{};approval=io.get(APPROVAL+str(c.get('job_id')))or{}
 if child.get('selected_ids',c.get('selected_ids'))!=c.get('selected_ids')or approval.get('plan_id')!=child.get('plan_id')or approval.get('sender_id')!=a['sender_id']or approval.get('status')not in('approved','completed'):raise ValueError('Companion approval changed')
 key='china_agent:daily_ad_execution:v2:'+child['plan_id'];execution=io.get(key)or{}
 if execution.get('plan_sha256')!=child.get('plan_sha256'):raise ValueError('Companion execution hash missing')
 items={i['id']:i for i in child.get('items',[])if i['campaign_id']==before['id']}
 states=[s for s in execution.get('items',[])if s['id']in items]
 if not items or len(states)!=len(items)or any(not proven(items[s['id']],s)for s in states):raise ValueError('Companion campaign changes not all WB verified')
 out=copy.deepcopy(evidence);expected=copy.deepcopy(out['expected_bids'])
 def bids(c):return {str(n['nm_id']):n['bids_kopecks']for n in c['nm_settings']}
 for state in states:
  item=items[state['id']]
  if bids(state['before'])!=expected:raise ValueError('Unapproved composition change between verified steps')
  expected=bids(state['after'])
  if item['kind']=='ad_add_sku':
   e=item.get('growth_evidence')or{};nm=str(item['nm_id'])
   needed=['seller_price_cny','own_cogs_rub','fx_rub_per_cny','stock_free','published_stock']
   if any(type(e.get(k))not in(int,float)for k in needed)or e.get('expected_margin_before_ads_cny',0)<=0:raise ValueError('Confirmed addition economics missing')
   out['member_inputs'][nm]=dict(article=item['article'],price=e['seller_price_cny'],cost=e['own_cogs_rub'],buyout=e.get('buyout'),fx=e['fx_rub_per_cny'],stock_free=e['stock_free'],published_stock=e['published_stock'])
 if expected!=bids(before):raise ValueError('Current composition is not the exact verified companion result')
 out['expected_bids']=expected
 out['confirmed_state_reconciliation']=dict(execution_key=key,verified_item_ids=list(items),original_report_model_unchanged=True,no_new_attributed_profit_credit=True)
 return out
