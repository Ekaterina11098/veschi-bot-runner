"""Owner-requested missing-day IP reads and retained report only; no WB/TG routes."""
import os,sys,json,copy,time,hashlib,contextlib,io
from pathlib import Path
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parent/'private-source'))
from analytics.collect import database,RUN_ID
from analytics.payload_storage import decode_rows
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads,period
from analytics.mpstats_recovery import normalize,BIDDER
from advertising_budget_evidence import load_daily_table_view
KEY='advertising:ip:morning_recovery:2026-11-04:v1'
DAY='2026-11-03'
NOW=datetime.now(timezone.utc)
def get(k):
 r=database('GET','telegram_api_cache',params={'cache_key':'eq.'+k,'select':'payload','limit':1}) or []
 return r[0]['payload'] if r else None
def put(k,p):database('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':k,'payload':p,'updated_at':datetime.now(timezone.utc).isoformat(),'expires_at':'2027-11-03T00:00:00Z'})
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
state={'status':'starting','report_day':'2026-11-04','data_day':DAY,'run_id':RUN_ID,'started_at':NOW.isoformat(),'saved':[],'reused':[],'normalization_errors':[],'wb_calls':0,'wb_writes':0,'telegram_calls':0,'decoded_response_bytes':0}
def save():put(KEY,state)
def snapshot(source,p,a,b,status='complete'):
 database('POST','analytics_snapshots',body={'source':source,'cabinet':'token_2','period_from':a,'period_to':b,'run_id':RUN_ID,'payload':[p],'status':status,'detail':'Owner requested exact missing Nov3 daily report; no WB/TG'})
 rows=decode_rows(database('GET','analytics_snapshots',params={'source':'eq.'+source,'cabinet':'eq.token_2','run_id':'eq.'+RUN_ID,'select':'id,payload','order':'id.desc','limit':1}) or [])
 if not rows or digest(rows[0]['payload'])!=digest([p]):raise RuntimeError('Saved snapshot full readback mismatch')
 return rows[0]['id']
memo={}
def existing(tool,args):
 key='token_2:'+tool+':'+json.dumps(args,sort_keys=True)
 if key in memo:return memo[key]
 a,b=period(args)
 rows=database('GET','analytics_snapshots',params={'source':'eq.mpstats_'+tool,'cabinet':'eq.token_2','period_from':'eq.'+a,'period_to':'eq.'+b,'collected_at':'gte.'+(datetime.fromisoformat(DAY)+timedelta(days=1,hours=-3)).replace(tzinfo=timezone.utc).isoformat(),'select':'id,state:payload->0->>status,key:payload->0->>request_key','order':'id.desc','limit':100}) or []
 for r in rows:
  if r.get('key')==key and r.get('state')=='received':
   full=decode_rows(database('GET','analytics_snapshots',params={'id':'eq.'+str(r['id']),'select':'id,payload','limit':1}))[0]
   obs=full['payload'][0]
   if tool=='lk_wb_products' and obs.get('data',{}).get('data',{}).get('need_update')!=0:continue
   memo[key]=obs;state['reused'].append(r['id']);return obs
 return None
def request(tool,args):
 old=existing(tool,args)
 if old is not None:return None
 return {'key':'token_2:'+tool+':'+json.dumps(args,sort_keys=True),'cabinet':'token_2','tool':tool,'arguments':args}
catalogs=[];reports={};own=None
def saved(cabinet,obs):
 global own
 if cabinet!='token_2':raise PermissionError('Unexpected cabinet')
 a,b=period(obs['arguments']);ident=snapshot('mpstats_'+obs['tool'],obs,a,b,'complete' if obs.get('status')=='received' else 'partial')
 memo[obs['request_key']]=obs;state['saved'].append({'id':ident,'key':obs['request_key'],'status':obs.get('status')})
 if obs.get('retry_after'):
  until=datetime.now(timezone.utc)+timedelta(seconds=obs['retry_after'])
  put('mpstats:cooldown',{'pending':True,'retry_after':obs['retry_after']})
  database('PATCH','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown'},body={'expires_at':until.isoformat()})
 if obs.get('status')=='received':ingest(obs,ident)
 save()
def ingest(obs,ident=None):
 global own
 if obs['tool']=='lk_wb_products':own=obs
 try:
  source,p=normalize(obs,'token_2')
  if source:
   if ident:p['raw_snapshot_id']=ident;snapshot(source,p,p.get('period_from') or period(obs['arguments'])[0],p.get('period_to') or period(obs['arguments'])[1])
   if source=='mpstats_campaign_catalog':catalogs.append(p)
   elif source=='mpstats_campaign_report':reports[p['campaign_id']]=p
 except (ValueError,KeyError,TypeError) as e:state['normalization_errors'].append({'tool':obs['tool'],'error':str(e)})
def collect(call,checks,known):
 bidder=copy.deepcopy(BIDDER)
 def run(reqs):
  reqs=[r for r in reqs if r]
  if not reqs:return
  if state.get('planned_external_reads',0)+len(reqs)>24:raise RuntimeError('Bounded24 missing-read allowance exhausted')
  state['planned_external_reads']=state.get('planned_external_reads',0)+len(reqs);save()
  out=execute_reads(call,checks,known,reqs,bidder,saved,max_requests=20)
  if any(r['status']!='received' for r in out):state['provider_gaps']=out
 def obtain(tool,args):
  old=existing(tool,args)
  if old is not None:ingest(old)
  else:run([request(tool,args)])
 for kind in ('stats','state'):
  args={'tokens':[BIDDER['token_2']['id']],'report':kind,'d1':DAY,'d2':DAY,'limit':100,'start_row':0,'bidder_only':False,'sort':'wb_id','sort_dir':'asc'}
  obtain('wbbidder_campaigns',args)
  first=next((c for c in catalogs if c['report']==kind and c['start_row']==0),None)
  if not first:continue
  if first['total']>400:raise ValueError('Unexpected catalog scope over400; no unbounded paging')
  for offset in range(100,first['total'],100):obtain('wbbidder_campaigns',dict(args,start_row=offset))
 rows=[r for c in catalogs if c.get('report')=='stats' for r in c.get('rows',[])]
 mapping={r['wb_id']:r for r in rows}
 bidder['token_2']['campaign_ids']=sorted({r['id'] for r in rows})
 state['mapping']={str(k):r['id'] for k,r in mapping.items() if k in scope}
 for cid in sorted(scope):
  if cid not in mapping:continue
  r=mapping[cid]
  args={'campaign_id':r['id'],'report':'products','d1':DAY,'d2':DAY}
  if all(r.get(k)==0 for k in ('ac_spending_sum','ac_orders','ac_orders_sum')):
   p={'tool':'wbbidder_campaign_stats','report':'products','cabinet':'token_2','campaign_id':r['id'],'period_from':DAY,'period_to':DAY,'scope_nm_id':None,'sku_order_basis':'direct_only','spending_reconciled':True,'rows':[],'totals':{k:r[k] for k in r if k.startswith('ac_')},'observed_at':datetime.now(timezone.utc).isoformat(),'derivation':'Exact-day complete catalog explicitly reports zero spend/orders; not inferred from missing rows'}
   snapshot('mpstats_campaign_report',p,DAY,DAY);reports[r['id']]=p
  else:obtain('wbbidder_campaign_stats',args)
 obtain('lk_wb_products',{'date_from':DAY,'date_to':DAY,'start_row':0,'end_row':1500})
 state['unmapped_campaigns']=sorted(scope-set(mapping));return []
class Store:
 def db(self,method,table,params=None,**kwargs):
  if method=='GET' and table=='analytics_snapshots' and (params or {}).get('source')=='eq.advertising_active_configuration':return [{'id':0,'payload':{'campaign_ids':sorted(scope)},'collected_at':NOW.isoformat()}]
  return database(method,table,params=params,**kwargs)
 def cache_get(self,k):return get(k)
 def registration(self):return {'chat_id':overview['chat_id']}
scope=set();overview={}
def main():
 global scope,overview
 intent=get(KEY+':approval')
 if not intent or intent.get('status')!='owner_authorized_missing_only' or intent.get('data_day')!=DAY:raise PermissionError('Exact report recovery approval missing')
 if get(KEY):raise RuntimeError('Existing recovery must be inspected, not replayed')
 save()
 host=urlsplit(os.environ['SUPABASE_URL']).hostname
 import requests
 original=requests.sessions.Session.request
 def guarded(session,method,url,*a,**kw):
  domain=urlsplit(url).hostname
  if domain not in (host,'mcp.mpstats.io'):raise PermissionError('Recovery source outside MPStats/Supabase')
  if domain=='mcp.mpstats.io' and state['decoded_response_bytes']>=100_000_000:raise RuntimeError('100MB collection boundary')
  r=original(session,method,url,*a,**kw);state['decoded_response_bytes']+=len(r.content);return r
 requests.sessions.Session.request=guarded
 try:
  overview=get('advertising:ip:daily-overview-scope:v1') or {}
  scope=set(overview.get('campaign_ids',[]))
  manual=get('ip_agent:expanded98:manual_campaign_launches:2026-11-02:v1') or {}
  scope.update(c['campaign_id'] for c in manual.get('campaigns',[]))
  if len(scope)>20 or not scope:raise ValueError('Scope missing/too wide')
  rows=database('GET','analytics_snapshots',params={'source':'eq.mpstats_connection','cabinet':'eq.shared','select':'tools:payload->0->tools','order':'id.desc','limit':1}) or []
  catalog=rows[0].get('tools') if rows else None
  pause=database('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+NOW.isoformat(),'select':'expires_at','limit':1}) or []
  if pause:
   until=datetime.fromisoformat(pause[0]['expires_at'].replace('Z','+00:00'));wait=(until-datetime.now(timezone.utc)).total_seconds()
   state.update(status='waiting_provider_cooldown',next_allowed_at=until.isoformat());save()
   if wait>1200:raise RuntimeError('Existing provider cooldown exceeds this bounded run')
   if wait>0:time.sleep(wait+1)
  result=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=collect,catalog=catalog)
  state['provider_status']={k:v for k,v in result.items() if k not in ('tools','checks')}
  view=load_daily_table_view(Store(),datetime.now(timezone.utc))
  state['view']=view;state['scope_count']=len(scope);state['complete_campaigns']=sum(c['metrics_complete'] for c in view['campaigns'])
  if own and own.get('status')=='received':
   body=own.get('data',{}).get('data',{});products=body.get('data',[])
   if body.get('need_update')==0 and body.get('total')==len(products) and len({r['p_id'] for r in products})==len(products):
    state['own_summary']={'period':DAY,'record_count':len(products),'orders':sum(r['orders_count'] for r in products),'orders_sum':sum(r['orders_sum'] for r in products),'sales':sum(r['sales_count'] for r in products),'returns':sum(r['returns_count'] for r in products),'note':'Own order-date statistics; finances preliminary. Variant rows retained once by p_id.'}
  state['status']='complete' if state['complete_campaigns']==len(scope) else 'partial'
 except Exception as e:state.update(status='blocked',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__)
 state['finished_at']=datetime.now(timezone.utc).isoformat();save()
 print(json.dumps({k:state.get(k) for k in ('status','scope_count','complete_campaigns','decoded_response_bytes','wb_calls','wb_writes','telegram_calls')}))
if __name__=='__main__':main()

