"""Saved-data replay of staged financial-risk code. No collection or delivery."""
import os,sys,json,contextlib,io,copy,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report=dict(wb_calls=0,telegram_calls=0,source_calls=0,canonical_decisions_modified=False)
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  import requests
  from urllib.parse import urlsplit
  native=requests.sessions.Session.request;host=urlsplit(os.environ['SUPABASE_URL']).hostname
  def guard(session,method,url,*a,**kw):
   write=(os.getenv('FOCUS_FOLLOWUP')=='true' and method.upper()=='POST' and urlsplit(url).path=='/rest/v1/telegram_api_cache' and isinstance(kw.get('json'),dict) and kw['json'].get('cache_key')=='advertising:ip:focus_preparation:20261016')
   if urlsplit(url).hostname!=host or (method.upper()!='GET' and not write):raise RuntimeError('Saved-data investigation transport boundary')
   return native(session,method,url,*a,**kw)
  requests.sessions.Session.request=guard
  from analytics.stage_one import read
  if os.getenv('FOCUS_FOLLOWUP')=='true':
   import statistics
   from datetime import datetime,timezone,timedelta
   cat=read('analytics_snapshots',dict(source='eq.mpstats_campaign_catalog',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=5))
   mapping={}
   for snap in cat:
    for pack in snap['payload']:
     for item in pack.get('rows',[]):mapping.setdefault(item['wb_id'],item['id'])
   budget=read('analytics_snapshots',dict(id='eq.17735',select='id,payload,collected_at'))[0]
   rows=read('analytics_snapshots',{'source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','payload->0->>report':'eq.days','select':'id,payload,collected_at,period_from,period_to','order':'id.desc','limit':1000})
   daily={}
   for snap in rows:
    for pack in snap['payload']:
     if pack.get('scope_nm_id') is not None:continue
     for day in pack.get('rows',[]):
      stamp=str(day.get('date',''))[:10];spend=day.get('ac_spending_sum')
      if stamp and type(spend) in (int,float):daily.setdefault((pack.get('campaign_id'),stamp),dict(spend=spend,snapshot_id=snap['id'],observed_at=snap['collected_at']))
   stats=[]
   for b in budget['payload']['items']:
    cid=b['campaign_id'];internal=mapping.get(cid)
    observed=[dict(day=d,**daily[(internal,d)]) for d in ['2026-10-%02d'%n for n in range(9,16)] if (internal,d) in daily]
    vals=[x['spend'] for x in observed];mean=statistics.mean(vals) if vals else None;sd=statistics.pstdev(vals) if vals else None
    base=datetime.fromisoformat(b['observed_at']);scenarios={}
    for label,rate in [('mean',mean),('observed_max',max(vals) if vals else None),('observed_min',min(vals) if vals else None)]:
     scenarios[label]=dict(rub_per_day=rate,exhaustion_at=(base+timedelta(days=b['total']/rate)).isoformat() if rate and rate>0 else None)
    stats.append(dict(campaign_id=cid,mpstats_id=internal,balance=b['total'],balance_at=b['observed_at'],days=observed,
      coverage=len(vals),mean=mean,min=min(vals) if vals else None,max=max(vals) if vals else None,sd=sd,cv=sd/mean if mean else None,
      last_retained_day=max((d for (i,d) in daily if i==internal),default=None),
      current_day_evidence=[dict(day=d,**v) for (i,d),v in daily.items() if i==internal and d=='2026-10-16'],
      scenario_only=True,scenarios=scenarios,current_rate_verified=False))
   finance=[]
   for day in ['2026-10-%02d'%n for n in range(9,16)]:
    snaps=read('analytics_snapshots',dict(source='eq.mpstats_products_validated',cabinet='eq.token_2',period_from='eq.'+day,period_to='eq.'+day,select='id,payload,collected_at',order='id.desc',limit=1))
    for snap in snaps:
     for pack in snap['payload']:
      for p in pack.get('products',[]):
       if p.get('nm_id') in (1123677454,320248210,1007948808):finance.append(dict(day=day,snapshot_id=snap['id'],observed_at=snap['collected_at'],nm_id=p['nm_id'],article=p.get('article'),advertisement=p.get('advertisement'),for_pay=p.get('for_pay')))
   sku=[]
   for nm in (1123677454,320248210,1007948808):
    exact={}
    for snap in rows:
     for pack in snap['payload']:
      if pack.get('scope_nm_id')!=nm:continue
      for d in pack.get('rows',[]):
       day=str(d.get('date',''))[:10]
       if '2026-10-09'<=day<='2026-10-15':exact.setdefault((pack.get('campaign_id'),day),dict(day=day,mpstats_id=pack.get('campaign_id'),snapshot_id=snap['id'],spend=d.get('ac_spending_sum')))
    sku.append(dict(nm_id=nm,daily_ad_statistics=list(exact.values()),daily_finance=[x for x in finance if x['nm_id']==nm]))
   raw=read('analytics_snapshots',dict(id='eq.17557',select='id,payload,collected_at'))[0]
   bidder=[{k:x.get(k) for k in ('id','wb_id','auto_bidding_activated','schedule_enabled','scenario_enabled','last_parsed_at')} for x in raw['payload'][0]['data']['data'] if x.get('wb_id')==39410834]
   report.update(mode='focus_followup',result=dict(budget_snapshot_id=17735,period_from='2026-10-09',period_to='2026-10-15',budget_pacing=stats,
    sku_reconciliation=sku,bidder_history=dict(snapshot_id=17557,observed_at=raw['collected_at'],rows=bidder),
    external_calls=0,wb_writes=0,telegram_calls=0,forecasts_enabled=False,test_authorized=False))
   one=read('analytics_snapshots',{'source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','period_from':'eq.2026-10-10','period_to':'eq.2026-10-10','payload->0->>report':'eq.products','select':'id,payload,collected_at','order':'id.desc','limit':1000})
   matched={}
   for snap in one:
    for pack in snap['payload']:
     for item in pack.get('rows',[]):
      if item.get('nm_id') in (1123677454,320248210):
       matched.setdefault((pack['campaign_id'],item['nm_id']),dict(campaign_id=pack['campaign_id'],nm_id=item['nm_id'],spend=item.get('ac_spending_sum'),snapshot_id=snap['id']))
   report['result']['same_day_20261010']=[dict(nm_id=nm,campaign_rows=[v for (cid,n),v in matched.items() if n==nm],campaign_sum=sum(v['spend'] for (cid,n),v in matched.items() if n==nm and type(v['spend']) in (int,float)),finance=next(x['advertisement'] for x in finance if x['nm_id']==nm and x['day']=='2026-10-10')) for nm in (1123677454,320248210)]
   report['result']['capability57_reference']=dict(run_id=38887156360,nm_id=1007948808,campaign_id=39410834,min_bid_kopecks=10500,current_bid_kopecks=10500,eligible=True,minus_items=[],membership_count=44,can_change_nms=True,executor_verified=False,test_authorized=False)
   key='advertising:ip:focus_preparation:20261016'
   old=read('telegram_api_cache',dict(cache_key='eq.'+key,select='payload',limit=1))
   if not old:raise RuntimeError('Existing focus investigation missing')
   original_memory=old[0]['payload'];updated=copy.deepcopy(original_memory)
   updated['followup_20261016']=report['result']
   report['prior_memory_sha256']=hashlib.sha256(json.dumps(original_memory,sort_keys=True).encode()).hexdigest()
   response=requests.post(os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache',
    headers={'apikey':os.environ['SUPABASE_SECRET_KEY'],'Authorization':'Bearer '+os.environ['SUPABASE_SECRET_KEY'],'Prefer':'resolution=merge-duplicates'},
    params={'on_conflict':'cache_key'},json=dict(cache_key=key,payload=updated,updated_at=datetime.now(timezone.utc).isoformat(),expires_at=(datetime.now(timezone.utc)+timedelta(days=365)).isoformat()),timeout=45)
   response.raise_for_status()
   after=read('telegram_api_cache',dict(cache_key='eq.'+key,select='payload',limit=1))[0]['payload']
   assert after==updated
   report['existing_investigation_full_readback']=True
   raise SystemExit(0)

  from analytics.collect import database
  from analytics.ip_financial_risk import risk_register,expense_test
  from datetime import datetime,timezone
  rows=read('analytics_snapshots',dict(id='eq.'+('17624' if os.getenv('BUDGET_REASSESSMENT')=='true' else '17603'),cabinet='eq.token_2',select='payload,period_from,period_to,id'))
  assert rows==read('analytics_snapshots',dict(id='eq.'+('17624' if os.getenv('BUDGET_REASSESSMENT')=='true' else '17603'),cabinet='eq.token_2',select='payload,period_from,period_to,id'))
  full=rows[0]['payload'][0]
  if os.getenv('BUDGET_REASSESSMENT')=='true':
   from analytics.ip_daily_recommendations import budget_analysis
   budget=read('analytics_snapshots',dict(id='eq.17735',cabinet='eq.token_2',select='id,payload,collected_at,status'))[0]
   assert budget['payload']['complete'] and len(budget['payload']['items'])==12
   ids=budget['payload']['campaign_ids']
   now=datetime.now(timezone.utc)
   assessed=budget_analysis(dict(campaigns=[dict(wb_campaign_id=cid,active_catalog_verified=True) for cid in ids],budgets=[budget],current_day_campaign_spend={}),now)
   assert len(assessed)==12 and all(x['balance'] is not None for x in assessed)
   daily=full['daily']
   report.update(mode='budget_reassessment',source_snapshot_id=17624,budget_snapshot=budget,
    evaluated_at=now.isoformat(),period_from=rows[0]['period_from'],period_to=rows[0]['period_to'],
    budget_before=daily.get('budget_analysis'),budget_after=assessed,
    campaign_summary=full.get('campaign_summary'),summary=full.get('summary'),
    pair_decision_trace=daily.get('pair_decision_trace'),actions=daily.get('actions'),
    investigations=None,financial_risk={k:v for k,v in (daily.get('financial_risk') or {}).items() if k!='risks'},
    test_candidates=daily.get('expense_test_candidates'),
    new_budget_actions=[],reason='All balances known and positive; no verified current-day spend rate; no replenishment amount or exhaustion horizon inferred',
    forecasts_enabled=False,wb_writes=0,canonical_decisions_modified=False)
   risks=(daily.get('financial_risk') or {}).get('risks',[])
   report['risk_by_campaign']={str(cid):sorted([dict(article=r.get('article'),nm_id=r.get('nm_id'),net_profit=r.get('net_profit'),reason=r.get('reason'),pairs=[p for p in r.get('pairs',[]) if p.get('campaign_id')==cid]) for r in risks if any(p.get('campaign_id')==cid for p in r.get('pairs',[]))],key=lambda x:x.get('net_profit') or 0)[:5] for cid in ids}
   report['pair_decision_trace']=[{k:p.get(k) for k in ('article','nm_id','campaign_id','final_status','reason','actions','blockers','shop_profit','advertising_profit')} for p in (daily.get('pair_decision_trace') or [])]
   assert report['actions']==daily.get('actions')
   raise SystemExit(0)
  inv=full['investigations']
  risk=risk_register(inv['investigations'],rows[0]['period_from'],rows[0]['period_to'],inv['campaigns'])
  assert risk['risk_sku_count']==137 and abs(risk['negative_sku_total']+119871.65)<.01
  config=read('analytics_snapshots',dict(source='eq.advertising_active_configuration',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1))[0]
  ads=config['payload'];ads=ads[0] if isinstance(ads,list) else ads
  focus_names={'685-CelineaBag-black','57-NoelBag-burgundy','141-PamelaBag-brown'}
  focus=[r for r in risk['risks'] if r['article'] in focus_names]
  plans=[]
  for r in focus:
   for p in r['pairs']:
    adv=next((a for a in ads['adverts'] if a['id']==p['campaign_id']),{})
    setting=next((n for n in adv.get('nm_settings',[]) if n['nm_id']==r['nm_id']),{})
    payment=(adv.get('settings') or {}).get('payment_type')
    placement='recommendations' if payment=='cpm' else 'search'
    current=(setting.get('bids_kopecks') or {}).get(placement)
    ev=dict(cabinet='token_2',nm_id=r['nm_id'],campaign_id=p['campaign_id'],currency=adv.get('currency'),
      current_bid_kopecks=current,observed_at=config['collected_at'],payment_type=payment,
      source_verified=True,membership_verified=bool(setting),all_sku_campaigns_covered=True)
    plan=expense_test(r,ev,datetime.now(timezone.utc))
    plan.update(article=r['article'],configuration_snapshot_id=config['id'],placement=placement,
      arithmetic_10pct_candidate_unvalidated=round(current*.9) if isinstance(current,int) else None,
      candidate_is_not_supported_bid=True)
    plans.append(plan)
  report.update(source_snapshot_id=17603,risk=risk,focus=focus,expense_test_drafts=plans,
    ready_real_employee_actions=sum(p['ready'] for p in plans),preview_only=True)
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-risk-preview',report)
 print(json.dumps(dict(risk_count=(report.get('risk') or {}).get('risk_sku_count'),ready_actions=report.get('ready_real_employee_actions'),
  error_type=(report.get('error') or {}).get('type'),source_calls=0,telegram_calls=0)))
