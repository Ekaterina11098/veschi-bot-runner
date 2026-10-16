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
   if urlsplit(url).hostname!=host or method.upper()!='GET':raise RuntimeError('Saved-data replay permits Supabase GET only')
   return native(session,method,url,*a,**kw)
  requests.sessions.Session.request=guard
  from analytics.stage_one import read
  from analytics.collect import database
  from analytics.ip_financial_risk import risk_register,expense_test
  from datetime import datetime,timezone
  rows=read('analytics_snapshots',dict(id='eq.17603',cabinet='eq.token_2',select='payload,period_from,period_to,id'))
  assert rows==read('analytics_snapshots',dict(id='eq.17603',cabinet='eq.token_2',select='payload,period_from,period_to,id'))
  full=rows[0]['payload'][0];inv=full['investigations']
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
