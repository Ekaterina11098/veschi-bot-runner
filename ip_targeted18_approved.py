"""Owner-approved exact18Oct advertising/budget reads; no full collection, delivery or WB writes."""
import os,sys,json,copy,time,math,requests,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
sys.path.insert(0,'private-source')
from stock_deploy_support import seal,error
DAY='2026-10-18';OWNER_DAY='2026-10-19';PIN='2f798a9509b72030d6fb5ec68fb915c5d216c31b'
proof=dict(complete=False,period_from=DAY,period_to=DAY,wb_writes=0,telegram_calls=0,full_collection=False,
 original_run='39202750461:1',saved=[],reads=[],budget_reads=[],daily_claim_reset=False)
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
traffic={'calls':0,'decoded_response_bytes':0}
def guard(session,method,url,*args,**kw):
 u=urlparse(url)
 if u.hostname==host:
  if not u.path.startswith('/rest/v1/'):raise PermissionError('Supabase REST only')
 elif u.hostname=='mcp.mpstats.io' and method=='POST':
  b=kw.get('json') or {};m=b.get('method')
  if m=='tools/call':
   p=b.get('params') or {};name=p.get('name');a=p.get('arguments') or {}
   if name not in ('account_limits','lk_wb_cabinets','wbbidder_campaign_stats','wbbidder_campaigns'):raise PermissionError('Unapproved MPStats tool')
   if name=='lk_wb_cabinets' and a.get('action')!='list':raise PermissionError('Cabinet changes not needed')
   if name=='wbbidder_campaign_stats' and (a.get('report')!='products' or a.get('d1')!=DAY or a.get('d2')!=DAY):raise PermissionError('Exact18Oct products only')
   if name=='wbbidder_campaigns' and (a.get('report')!='state' or a.get('start_row')!=100 or a.get('tokens')!=[152922]):raise PermissionError('Exact known budget catalog page only')
  elif m not in ('initialize','notifications/initialized','tools/list'):raise PermissionError('MPStats method forbidden')
 elif u.hostname=='advert-api.wildberries.ru' and method=='GET' and u.path=='/adv/v1/budget':
  proof['budget_reads'].append({'campaign_id':(kw.get('params') or {}).get('id'),'at':datetime.now(timezone.utc).isoformat()})
  if len(proof['budget_reads'])>1:raise PermissionError('Existing single budget step only')
 else:raise PermissionError('External destination or write forbidden')
 if traffic['decoded_response_bytes']>=25000000:raise RuntimeError('25MB targeted response cap')
 r=native(session,method,url,*args,**kw);traffic['calls']+=1;traffic['decoded_response_bytes']+=len(r.content);return r
requests.sessions.Session.request=guard
def checkpoint():proof['traffic']=traffic;seal('ip-targeted18',proof)
try:
 from advertising_agent import agent_store as store,collect_ip as c
 from analytics.payload_storage import decode_rows
 from analytics.mpstats_recovery import normalize,BIDDER
 from analytics.mpstats_probe import discover
 from analytics.mpstats_gaps import execute_reads
 now=datetime.now(timezone.utc);local=now.astimezone(ZoneInfo('Europe/Moscow'))
 if local.date().isoformat()!=OWNER_DAY:raise PermissionError('Approved day expired')
 reg=store.registration();proof['registration']=reg
 # Address/source pin only; preserve all approved rollout fields and read back.
 rows=store.db('GET','telegram_api_cache',params={'cache_key':'eq.advertising:ip:daily_rollout:v1','select':'payload,updated_at','limit':1}) or []
 if len(rows)!=1:raise RuntimeError('Daily approval missing')
 old=rows[0]['payload']
 if old.get('owner_id')!=reg['registered_by_user_id'] or old.get('chat_id')!=reg['chat_id']:raise PermissionError('Owner/chat changed')
 if old.get('source_sha') not in ('d71a576d55f4e9c89aaa5fb5cc2177722c6176f9',PIN):raise PermissionError('Unexpected deployed source pin')
 if old.get('source_sha')!=PIN:
  updated=copy.deepcopy(old);updated['source_sha']=PIN
  store.db('PATCH','telegram_api_cache',params={'cache_key':'eq.advertising:ip:daily_rollout:v1','updated_at':'eq.'+rows[0]['updated_at']},body={'payload':updated,'updated_at':now.isoformat()})
  if store.cache_get('advertising:ip:daily_rollout:v1')!=updated:raise RuntimeError('Daily pin CAS readback failed')
 proof['daily_rollout_pin']=PIN
 claim=store.cache_get('advertising:ip:daily_run:v1:'+OWNER_DAY)
 if not claim or claim.get('run_id')!='39202750461:1' or claim.get('status')!='failed':raise PermissionError('Original failed daily claim changed')
 proof['original_claim_status']=claim['status']
 config=decode_rows(store.db('GET','analytics_snapshots',params={'source':'eq.advertising_active_configuration','cabinet':'eq.token_2','select':'id,payload,collected_at','order':'id.desc','limit':1}) or [])
 if len(config)!=1:raise RuntimeError('Saved active scope missing')
 cfg=config[0];active=sorted(cfg['payload']['campaign_ids'])
 proof['configuration']={'id':cfg['id'],'collected_at':cfg['collected_at'],'campaign_ids':active}
 index=store.cache_get('mpstats:agent_reports:token_2:v1') or {};catalogs=[x.get('report') or {} for x in index.get('reports',{}).values() if x.get('source')=='mpstats_campaign_catalog']
 mapping={}
 for cat in sorted(catalogs,key=lambda x:x.get('observed_at') or ''):
  for row in cat.get('rows') or []:
   if row.get('wb_id') in active:mapping[row['wb_id']]=row['id']
 if set(mapping)!=set(active):raise RuntimeError('Saved WB/MPStats campaign mapping incomplete')
 proof['mapping']=mapping
 bidder=copy.deepcopy(BIDDER);bidder['token_2']['campaign_ids']=list(mapping.values())
 reports={};budget_catalog=[]
 existing=decode_rows(store.db('GET','analytics_snapshots',params={'source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','period_from':'eq.'+DAY,'period_to':'eq.'+DAY,'select':'id,payload,collected_at','order':'id.desc','limit':100}) or [])
 for snap in existing:
  for p in snap.get('payload') or []:
   if p.get('campaign_id') in mapping.values() and p.get('report')=='products' and p.get('scope_nm_id') is None and p.get('spending_reconciled') is True:
    reports.setdefault(p['campaign_id'],dict(p,normalized_snapshot_id=snap['id']))
 def save(cabinet,obs):
  if cabinet!='token_2':raise PermissionError('Wrong cabinet')
  a=obs['arguments'];fields=dict(cabinet='token_2',run_id=os.environ['GITHUB_RUN_ID'],period_from=DAY,period_to=DAY)
  raw=store.db('POST','analytics_snapshots',body=dict(fields,source='mpstats_'+obs['tool'],status='complete' if obs['status']=='received' else 'partial',payload=[obs],detail='Owner approved exact18Oct ads/current budgets; no full source run'),prefer='return=representation') or []
  if len(raw)!=1:raise RuntimeError('Raw source persistence missing')
  if not store.db('GET','analytics_snapshots',params={'id':'eq.'+str(raw[0]['id']),'select':'id','limit':1}):raise RuntimeError('Raw readback missing')
  proof['saved'].append({'id':raw[0]['id'],'key':obs['request_key'],'status':obs['status']})
  if obs.get('retry_after'):
   until=datetime.now(timezone.utc)+timedelta(seconds=int(obs['retry_after']))
   store.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':'mpstats:cooldown','payload':{'pending':True,'retry_after':obs['retry_after']},'expires_at':until.isoformat()},prefer='resolution=merge-duplicates')
  if obs['status']=='received':
   source,p=normalize(obs,cabinet);p['raw_snapshot_id']=raw[0]['id']
   norm=store.db('POST','analytics_snapshots',body=dict(fields,source=source,status='complete',payload=[p],detail='Exact18Oct targeted normalized read'),prefer='return=representation') or []
   if len(norm)!=1:raise RuntimeError('Normalized source persistence missing')
   got=decode_rows(store.db('GET','analytics_snapshots',params={'id':'eq.'+str(norm[0]['id']),'select':'id,payload','limit':1}) or [])
   if not got or got[0]['payload']!=[p]:raise RuntimeError('Normalized source full readback mismatch')
   if source=='mpstats_campaign_report':reports[p['campaign_id']]=dict(p,normalized_snapshot_id=norm[0]['id'])
   elif source=='mpstats_campaign_catalog':budget_catalog.extend(p.get('rows') or [])
  checkpoint()
 plan=[]
 for wb,mp in sorted(mapping.items()):
  if mp not in reports:plan.append(dict(cabinet='token_2',tool='wbbidder_campaign_stats',key='approved18:'+str(wb)+':products',priority=90,arguments={'campaign_id':mp,'report':'products','d1':DAY,'d2':DAY}))
 plan.append(dict(cabinet='token_2',tool='wbbidder_campaigns',key='approved19:budget-state:page100',priority=100,arguments={'tokens':[152922],'report':'state','limit':100,'start_row':100,'bidder_only':False,'sort':'wb_id','sort_dir':'asc'}))
 pause=store.db('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+now.isoformat(),'select':'expires_at','limit':1}) or []
 if pause:
  wait=max(0,(datetime.fromisoformat(pause[0]['expires_at'].replace('Z','+00:00'))-now).total_seconds())
  if wait>600:raise RuntimeError('Shared MPStats RetryAfter exceeds bounded targeted window')
  if wait:time.sleep(wait+2)
 tools=store.db('GET','analytics_snapshots',params={'source':'eq.mpstats_connection','cabinet':'eq.shared','select':'tools:payload->0->tools','order':'id.desc','limit':1}) or []
 catalog=(tools[0].get('tools') if tools else None)
 def reader(call,checks,known):return execute_reads(call,checks,known,plan,bidder,save,max_requests=len(plan))
 proof['provider']=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,catalog=catalog,extra_reader=reader)
 # Existing WB collector, one due step only, shared stored cooldown remains authoritative.
 c.NOW=datetime.now(timezone.utc);c.TODAY=c.NOW.astimezone(ZoneInfo('Europe/Moscow')).date()
 try:
  if (c.NOW-datetime.fromisoformat(cfg['collected_at'].replace('Z','+00:00'))).total_seconds()<=21600:c.collect_campaign_budgets(os.environ['WB_TOKEN_2'],active)
  else:proof['budget_limitation']='Saved membership older than6h; no unscoped WB budget call'
 except Exception as exc:proof['budget_error']=error(exc)
 latest=c.latest('advertising_campaign_budgets',status=None) or {}
 wb_budgets={r['campaign_id']:r for r in (latest.get('payload') or {}).get('items',[])}
 mp_budgets={r['wb_id']:r for r in budget_catalog if r.get('wb_id') in active}
 from business_agents.data import Data
 cards=Data('operations',lambda t,p:store.db('GET',t,params=p)).snapshot('cards','token_2')
 articles={int(r['nmID']):r['vendorCode'] for r in cards.get('rows',[]) if r.get('nmID') and r.get('vendorCode')}
 result=[]
 for wb in active:
  p=reports.get(mapping[wb]);rows=p.get('rows',[]) if p else [];totals=p.get('totals') or {} if p else {}
  valid=bool(p) and p.get('spending_reconciled') is True and p.get('period_from')==DAY and p.get('period_to')==DAY
  cost=totals.get('ac_spending_sum') if valid else None
  # Campaign associated orders are already included in totals; do not add them again.
  amount=totals.get('ac_orders_sum') if valid else None;orders=totals.get('ac_orders') if valid else None
  above=[];within=[];zero=[];unknown=[]
  for r in rows:
   nm=r.get('nm_id');article=articles.get(nm) or 'nm'+str(nm)
   s=r.get('ac_spending_sum');v=r.get('ac_orders_sum');o=r.get('ac_orders')
   if not all(type(x) in (int,float) and math.isfinite(x) and x>=0 for x in (s,v,o)):unknown.append(article);continue
   if v>0 and o>0:
    item=dict(article=article,nm_id=nm,spend=s,orders=o,revenue=v,drr=100*s/v)
    (above if item['drr']>5 else within).append(item)
   elif s>0:zero.append(dict(article=article,spend=s,orders=o))
  wbv=wb_budgets.get(wb,{});mpv=mp_budgets.get(wb,{})
  candidates=[]
  if type(wbv.get('total')) in (int,float) and wbv.get('observed_at'):candidates.append(dict(balance=wbv['total'],observed_at=wbv['observed_at'],source='WB',valid=bool(wbv.get('available'))))
  if type(mpv.get('current_budget')) in (int,float) and mpv.get('current_budget_updated_at'):candidates.append(dict(balance=mpv['current_budget'],observed_at=mpv['current_budget_updated_at'],source='MPStats',parsed_at=mpv.get('last_parsed_at'),valid=True))
  candidates.sort(key=lambda r:r['observed_at'],reverse=True);balance=candidates[0] if candidates else {}
  try:
   stamp=datetime.fromisoformat(balance['observed_at'].replace('Z','+00:00'));balance['today_observation']=stamp.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()==OWNER_DAY and stamp<=datetime.now(timezone.utc)
  except (KeyError,ValueError):balance['today_observation']=False
  hours=balance['balance']/cost*24 if valid and type(cost) in (int,float) and cost>0 and balance.get('today_observation') and balance.get('valid') else None
  result.append(dict(campaign_id=wb,source_snapshot_id=p.get('normalized_snapshot_id') if p else None,period_from=DAY,period_to=DAY,
   metrics_complete=valid,spend=cost,orders=orders,revenue=amount,drr=100*cost/amount if valid and amount and amount>0 else None,
   campaign_basis='total_orders_including_associated_once',sku_basis=p.get('sku_order_basis') if p else None,
   above5=sorted(above,key=lambda x:-x['drr']),within5_count=len(within),zero_orders=zero,unknown=unknown,budget=balance,
   conditional_hours_at_18Oct_spend=hours,capacity_note='Balance at observed time /18Oct full-day spend; not guaranteed, spending since observation not deducted',
   no_actual_change=True))
 proof['campaigns']=result;proof['budget_catalog']=budget_catalog
 proof['complete']=len(result)==len(active) and all(r['metrics_complete'] for r in result)
 proof['budget_complete']=all(r['budget'].get('today_observation') and r['budget'].get('valid') for r in result)
 # Durable targeted result linked to original day; never replace failed full-analysis state.
 value=dict(original_run=proof['original_run'],target_run=os.environ['GITHUB_RUN_ID'],period_from=DAY,period_to=DAY,
  status='complete' if proof['complete'] else 'incomplete',budgets_complete=proof['budget_complete'],campaigns=result,
  source_snapshot_ids=[r['id'] for r in proof['saved']],telegram_calls=0,wb_writes=0)
 store.cache_set('advertising:ip:targeted18:2026-10-19',value,ttl_days=365)
 if store.cache_get('advertising:ip:targeted18:2026-10-19')!=value:raise RuntimeError('Targeted result readback missing')
 proof['target_result_saved']=True
except Exception as exc:proof['error']=error(exc)
finally:
 checkpoint()
 print(json.dumps({k:proof.get(k) for k in ('complete','budget_complete','target_result_saved','wb_writes','telegram_calls','full_collection')}))
 if proof.get('error'):print(json.dumps({'error_type':proof['error']['type']}))
