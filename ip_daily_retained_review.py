"""Whole-assortment retained review adapter. No collector, writes, dispatcher or money caps."""
import copy,math
from datetime import datetime,timedelta
def num(v):return type(v) in (int,float) and math.isfinite(v) and v>=0
def shop_rows(payload):
 out=[]
 def walk(v):
  if isinstance(v,dict):
   if type(v.get('nm_id')) is int and v.get('sa_name') and 'orders_count' in v:out.append(v);return
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 walk(payload);return out
def restriction_signal(data,reference=None,peer_clicks_per_order=None):
 """Open evidence-based candidates, not mandatory removals or profit claims."""
 values=[(day,v)for day,v in sorted(data.items())if all(num(v.get(k))for k in('spend','orders','revenue'))]
 cost=sum(v['spend']for _,v in values);orders=sum(v['orders']for _,v in values);revenue=sum(v['revenue']for _,v in values)
 spent=[v for _,v in values if v['spend']>0]
 no_order_days=sum(v['spend']>0 and v['orders']==0 for _,v in values)
 high_days=sum(v['revenue']>0 and v['spend']/v['revenue']>.05 for _,v in values)
 clicks=sum(v['clicks']for _,v in values)if values and all(num(v.get('clicks'))for _,v in values)else None
 drr=100*cost/revenue if revenue>0 else None
 repeated=high_days+no_order_days>=2
 target_cpa=.05*reference if num(reference)and reference>0 else None
 comparable_traffic=clicks is not None and num(peer_clicks_per_order)and peer_clicks_per_order>0 and clicks>=peer_clicks_per_order
 meaningful_no_orders=orders==0 and cost>0 and ((target_cpa is not None and cost>=target_cpa)or comparable_traffic)
 severe_one_day=orders==0 and target_cpa is not None and cost>=2*target_cpa
 # No second 5%-of-order allowance on top of the actual excess. This was the hidden cliff.
 excess_with_orders=orders>0 and revenue>0 and cost>.05*revenue
 candidate=bool((excess_with_orders and repeated)or(meaningful_no_orders and(len(spent)>=2 or severe_one_day)))
 return dict(candidate=candidate,spend=cost,orders=orders,revenue=revenue,drr_pct=drr,clicks=clicks,decision_days=[d for d,_ in values],no_order_spend_days=no_order_days,above_target_days=high_days,
  comparable_clicks_per_order=peer_clicks_per_order,target_cpa_reference=target_cpa,reference_is_not_spend_cap=True,
  reason='repeated_above_target_or_zero_order_spend'if candidate else'limited_sample_or_isolated_ratio'if cost>0 else'no_observed_spend',profit_loss_not_established=True)

def review(store,view,configs,authorized,protected_additions=None,pending_nms=None,pair_changes=None,sku_changes=None):
 from analytics.payload_storage import decode_rows
 end=view['period'];coverage=dict(period_to=end,existing_pairs=0,own_articles=0,directions={k:dict(checked=0,ready=0,gaps=0) for k in ('raise','add','reduce','exclude')},new_campaign_projects=[],limitations=[],restriction_audit=[])
 reports=decode_rows(store.db('GET','analytics_snapshots',params={'source':'in.(ip_limited_working_review,ip_working_mode_replay)','cabinet':'eq.token_2','select':'id,payload','order':'id.desc','limit':4}) or [])
 daily=None
 for snap in reports:
  for p in snap.get('payload') or []:
   d=p.get('daily') if isinstance(p,dict) else None
   if d and d.get('period_to')==end:daily=d;break
  if daily:break
 if not daily:coverage['limitations'].append('Saved complete analytical review ending '+end+' not found; no finance values invented')
 profit=((daily or {}).get('campaign_review') or {}).get('sku_profit_index') or {}
 saved_models=store.cache_get('advertising:ip:saved-unit-economics:v1') or {};models=saved_models.get('models') or {};economic_basis={}
 fby={(r['campaign_id'],r['nm_id']):r.get('facts',{}) for r in (daily or {}).get('full_pair_analysis',[])}
 own=decode_rows(store.db('GET','analytics_snapshots',params={'source':'eq.mpstats_lk_wb_products','cabinet':'eq.token_2','period_from':'eq.'+end,'period_to':'eq.'+end,'status':'eq.complete','select':'id,payload','order':'id.desc','limit':1}) or [])
 rows=shop_rows(own[0]['payload']) if own else [];stock={};demand={};labels={}
 for r in rows:
  nm=r['nm_id'];labels[nm]=r['sa_name'];q=stock.setdefault(nm,{'fbo':0,'fbs':0,'known':True,'subject':r.get('subject_id')});fbo=r.get('stock_api_stock_count');fbs=r.get('fbs_stock')
  if not num(fbo) or not num(fbs):q['known']=False
  else:q['fbo']+=fbo;q['fbs']+=fbs
  d=demand.setdefault(nm,{'orders':0,'revenue':0})
  if num(r.get('orders_count')) and num(r.get('orders_sum')):d['orders']+=r['orders_count'];d['revenue']+=r['orders_sum']
 coverage['own_articles']=len(labels)
 if not rows:coverage['limitations'].append('Exact-day full own product slice unavailable; no growth/additions inferred from stock absence')
 root=store.cache_get('ip_agent:expanded98:2026-11-02:v1:execution:optimized2') or {}
 minima={(r['subject'],r['payment_type'],r['placement'],r['currency'],r['bid_type']):r['minimum_minor'] for r in root.get('category_minimum_reuse',[])}
 allviews=sorted((view.get('_recent_views') or [])+[view],key=lambda v:v['period'])
 pairdata={};spending_nms=set();pair_changes=pair_changes or {};sku_changes=sku_changes or {}
 for v in allviews:
  for c in v['campaigns']:
   for r in c.get('sku_rows') or []:
    nm=r.get('nm_id')
    if type(nm) is not int or not all(num(r.get(k)) for k in ('ac_spending_sum','ac_orders','ac_orders_sum')):continue
    if r['ac_spending_sum']>0:spending_nms.add(nm)
    changed=max(pair_changes.get((c['campaign_id'],nm),''),sku_changes.get(nm,''))
    cfg=configs.get(c['campaign_id'],{});started=cfg.get('timestamps',{}).get('started')
    if started:
     from zoneinfo import ZoneInfo
     changed=max(changed,datetime.fromisoformat(started.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat())
    if changed and v['period']<=changed:continue # Never mix the change day into effect-based recommendations.
    pairdata.setdefault((c['campaign_id'],nm),{})[v['period']]=dict(spend=r['ac_spending_sum'],orders=r['ac_orders'],revenue=r['ac_orders_sum'],clicks=r.get('ac_clicks'),views=r.get('ac_views'))
 active={n['nm_id'] for c in configs.values() if c.get('status') in (9,11) for n in c.get('nm_settings',[])}
 result=[];protected_additions=set(protected_additions or []);pending_nms=set(pending_nms or [])
 from statistics import median
 refs={};peer_clicks={}
 for (cid,nm),values in pairdata.items():
  c=configs.get(cid);n=next((n for n in (c or {}).get('nm_settings',[]) if n['nm_id']==nm),None)
  if not n:continue
  for v in values.values():
   if v['orders']>0 and v['revenue']>0:
    refs.setdefault(n['subject']['id'],[]).append(v['revenue']/v['orders'])
    if num(v.get('clicks'))and v['clicks']>0:
     key=(n['subject']['id'],c['settings']['payment_type'],tuple(sorted(c['settings'].get('placements',{}).items())))
     peer_clicks.setdefault(key,[]).append(v['clicks']/v['orders'])
 def economy(nm,cid):
  p=profit.get(str(nm),{});f=fby.get((cid,nm),{})
  if (p.get('status')=='preliminary' and p.get('period_to')==end and num(p.get('after_ads')) and p['after_ads']>0) or (f.get('positive_entry_economics') is True and num(f.get('entry_net_profit')) and f['entry_net_profit']>0):
   economic_basis[nm]={'kind':'existing_saved_economics','period_to':end};return True
  # A dated successful-buyout scenario is usable only for a small research proposal,
  # with an observed unchanged order price. Never silently substitute a buyout rate,
  # current-period profit, raw MPStats profit, or an unobserved selling price.
  m=models.get(str(nm),{});own=demand.get(nm,{})
  if num(m.get('scenario_one_buyout_after_assumed_5pct_ad')) and m['scenario_one_buyout_after_assumed_5pct_ad']>0 and num(m.get('historical_order_price')) and m['historical_order_price']>0 and own.get('orders',0)>0 and abs(own['revenue']/own['orders']-m['historical_order_price'])<=1:
   economic_basis[nm]=dict(kind='dated_conditional_single_buyout_scenario',model=m,buyout_rate_unknown=True,current_order_price=own['revenue']/own['orders'],not_current_period_profit=True);return True
  return False
 def has_stock(nm,subject):
  q=stock.get(nm,{})
  return q.get('known') and (q['fbo']>0 if subject in (51,57,255,756) else q['fbo']+q['fbs']>0)
 def base(c,nm,kind):
  criterion='Три полных дня после изменения: охват, общие заказы и ДРР. Не повышать повторно при росте расхода без заказов. Выручка/прибыль не гарантированы.'
  if economic_basis.get(nm,{}).get('kind')=='dated_conditional_single_buyout_scenario':criterion+=' Экономика — датированный сценарий одной выкупленной продажи при той же наблюдаемой цене, а не доказанная прибыль следующего заказа; доля выкупа неизвестна.'
  return dict(ready=True,sku=labels[nm],nm=nm,campaign=c['id'],kind=kind,baseline=copy.deepcopy(c),period_to=end,source='Existing retained daily report/product slice and dated verified WB category minimum; no new source requests',criterion=criterion,economic_basis=copy.deepcopy(economic_basis.get(nm)),campaign_name=c['settings'].get('name',''),daily=pairdata.get((c['id'],nm),{}),placement_label='Ставка поиска',placement='search')
 for cid,c in configs.items():
  if c.get('status')!=9 or c.get('currency')!='RUB' or c.get('bid_type')!='manual':continue
  for n in c.get('nm_settings',[]):
   nm=n['nm_id'];coverage['existing_pairs']+=1
   for k in ('raise','reduce','exclude'):coverage['directions'][k]['checked']+=1
   audit=dict(campaign=cid,nm=nm,sku=labels.get(nm),status='checking');coverage['restriction_audit'].append(audit)
   if nm not in labels or (cid,nm) in authorized or nm in pending_nms:
    audit['status']='owner_protected_pending_or_own_label_missing';continue
   if cid==40428689 and 'orange' in labels[nm].lower():audit['status']='orange_protected';continue
   data=pairdata.get((cid,nm),{});latest=data.get(end)
   if not latest:
    for k in ('raise','reduce','exclude'):coverage['directions'][k]['gaps']+=1
    audit['status']='latest_sku_row_missing_after_verified_change';continue
   subject=n['subject']['id'];pay=c['settings']['payment_type'];place='search' if pay=='cpc' else 'recommendations';floor=minima.get((subject,pay,'search' if pay=='cpc' else 'recommendation','RUB','manual'));old=n.get('bids_kopecks',{}).get(place)
   if type(old)is not int or old<=0:
    audit['status']='stored_bid_unknown';coverage['directions']['reduce']['gaps']+=1;coverage['directions']['exclude']['gaps']+=1;continue
   values=list(data.values());cost=sum(v['spend'] for v in values);orders=sum(v['orders'] for v in values);revenue=sum(v['revenue'] for v in values)
   own=demand.get(nm,{});reference=revenue/orders if orders else own.get('revenue',0)/own['orders'] if own.get('orders') else median(refs[subject]) if refs.get(subject) else None
   peerkey=(subject,pay,tuple(sorted(c['settings'].get('placements',{}).items())));peer=median(peer_clicks[peerkey])if len(peer_clicks.get(peerkey,[]))>=3 else None
   signal=restriction_signal(data,reference,peer);audit.update(status=signal['reason'],evidence=signal)
   if signal['candidate']:
    target=max(floor,math.floor(old*.95))if type(floor)is int else old
    if target<old:
     a=base(c,nm,'lower_bid');a.update(stored_bid_minor=old,target_bid_minor=target,minimum_bid_minor=floor,placement=place,placement_label='Ставка поиска' if pay=='cpc' else 'Ставка за 1 000 показов',restriction_evidence=signal);result.append(a);coverage['directions']['reduce']['ready']+=1;audit['status']='lower_bid_candidate'
    elif len(c['nm_settings'])>1 and c.get('restrictions',{}).get('can_change_nms'):
     a=base(c,nm,'remove');a['restriction_evidence']=dict(signal,minimum_known=type(floor)is int,at_saved_minimum=bool(type(floor)is int and old<=floor));result.append(a);coverage['directions']['exclude']['ready']+=1;audit['status']='scoped_exclusion_candidate'
    else:audit['status']='last_sku_or_membership_change_not_allowed';coverage['directions']['exclude']['gaps']+=1
   elif type(floor)is int and pay=='cpc' and ((orders>0 and revenue>0 and cost/revenue<=.05) or (orders==0 and own.get('orders',0)>0 and reference is not None and cost<.05*reference)) and has_stock(nm,subject) and economy(nm,cid):
    a=base(c,nm,'raise_bid');a.update(stored_bid_minor=old,target_bid_minor=math.floor(old*1.05),positive_stock_verified=True,positive_fbo_verified=stock[nm]['fbo']>0,subject=subject,research_test=True);result.append(a);coverage['directions']['raise']['ready']+=1
   elif type(floor)is int and pay=='cpc' and orders>0 and revenue>0 and cost/revenue<=.05:coverage['directions']['raise']['gaps']+=1
 planned_additions={}
 for nm in labels:
  coverage['directions']['add']['checked']+=1
  if nm in active or nm in spending_nms or nm in protected_additions or nm in pending_nms or not demand.get(nm,{}).get('orders'):continue
  subject=stock[nm]['subject']
  if not has_stock(nm,subject) or not economy(nm,None):coverage['directions']['add']['gaps']+=1;continue
  destinations=[c for c in configs.values() if c.get('status')==9 and c.get('currency')=='RUB' and c.get('bid_type')=='manual' and c['settings'].get('payment_type')=='cpc' and c['settings'].get('placements')=={'search':True,'recommendations':False} and c.get('restrictions',{}).get('can_change_nms') and len(c['nm_settings'])+planned_additions.get(c['id'],0)<50 and {n['subject']['id'] for n in c['nm_settings']}=={subject}]
  floor=minima.get((subject,'cpc','search','RUB','manual'))
  if not destinations or type(floor)is not int:coverage['new_campaign_projects'].append(dict(nm=nm,sku=labels[nm],reason='No evidenced free matching campaign/minimum; no new campaign action created'));continue
  c=min(destinations,key=lambda c:len(c['nm_settings']));a=base(c,nm,'add');a.update(target_bid_minor=floor,minimum_bid_minor=floor,subject=subject,positive_stock_verified=True,positive_fbo_verified=stock[nm]['fbo']>0,research_test=True);result.append(a);coverage['directions']['add']['ready']+=1
  planned_additions[c['id']]=planned_additions.get(c['id'],0)+1
 from collections import Counter
 coverage['restriction_summary']=dict(Counter(r['status']for r in coverage['restriction_audit']))
 coverage['whole_own_slice_available']=bool(rows);coverage['financial_model_available']=bool(profit);coverage['dated_conditional_unit_models']=len(models);coverage['conditional_basis_used']=sum(a.get('economic_basis',{}).get('kind')=='dated_conditional_single_buyout_scenario' for a in result if a.get('economic_basis'));coverage['complete_existing_campaign_review']=bool(configs) and bool(rows)
 return result,coverage
