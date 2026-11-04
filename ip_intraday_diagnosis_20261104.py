"""One owner-authorized intraday IP diagnostic using existing MPStats readers only."""
import os,sys,json,time,copy
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from analytics.collect import database,RUN_ID
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from analytics.mpstats_recovery import BIDDER,normalize
DAY='2026-11-04';KEY='ip_agent:intraday_diagnosis:2026-11-04:v1'
SCOPE={35654841,36514081,37155100,37363108,37757330,39410834,39483230,39634287,40192945,40428505,40428689,41519685,41519741}
def put(s):database('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':KEY,'payload':s,'updated_at':datetime.now(timezone.utc).isoformat(),'expires_at':'2027-11-04T00:00:00Z'})
state=dict(status='running',day=DAY,run_id=RUN_ID,observations=[],wb_writes=0,wb_calls=0,telegram_calls=0,response_bytes=0)
def saved(cab,obs):
 if cab!='token_2':raise PermissionError('IP only')
 state['observations'].append(obs);put(state)
def collect(call,checks,known):
 reqs=[]
 for tool,args in [('wbbidder_campaigns',dict(tokens=[BIDDER['token_2']['id']],report='stats',d1=DAY,d2=DAY,limit=200,start_row=0,bidder_only=False,sort='wb_id',sort_dir='desc')),('lk_wb_products',dict(date_from=DAY,date_to=DAY,start_row=0,end_row=1500))]:
  reqs.append(dict(key='token_2:'+tool+':'+json.dumps(args,sort_keys=True),cabinet='token_2',tool=tool,arguments=args))
 return execute_reads(call,checks,known,reqs,copy.deepcopy(BIDDER),saved,max_requests=2)
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise PermissionError('Public runner only')
 if datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()!=DAY:raise PermissionError('Dated diagnostic only')
 if database('GET','telegram_api_cache',params={'cache_key':'eq.'+KEY,'select':'cache_key','limit':1}):raise RuntimeError('Prior diagnostic retained; do not replay')
 pause=database('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+datetime.now(timezone.utc).isoformat(),'select':'expires_at','limit':1}) or []
 if pause:
  state.update(status='provider_cooldown',next_allowed_at=pause[0]['expires_at']);put(state);return
 put(state)
 tools=database('GET','analytics_snapshots',params={'source':'eq.mpstats_connection','cabinet':'eq.shared','select':'tools:payload->0->tools','order':'id.desc','limit':1})[0]['tools']
 import requests
 original=requests.sessions.Session.request;host=urlsplit(os.environ['SUPABASE_URL']).hostname
 def guard(session,method,url,*a,**kw):
  domain=urlsplit(url).hostname
  if domain not in (host,'mcp.mpstats.io'):raise PermissionError('No WB, Telegram or other sources')
  r=original(session,method,url,*a,**kw)
  if domain=='mcp.mpstats.io':
   state['response_bytes']+=len(r.content)
   if state['response_bytes']>100_000_000:raise RuntimeError('100MB boundary')
  return r
 requests.sessions.Session.request=guard
 try:
  result=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=collect,catalog=tools)
  state['provider_result']={k:v for k,v in result.items() if k not in ('tools','checks')}
  for obs in state['observations']:
   if obs.get('status')!='received':continue
   if obs['tool']=='wbbidder_campaigns':
    source,p=normalize(obs,'token_2');rows=[r for r in p.get('rows',[]) if r.get('wb_id') in SCOPE];state['campaigns']=rows;state['missing_campaigns']=sorted(SCOPE-{r['wb_id'] for r in rows})
   elif obs['tool']=='lk_wb_products':
    body=obs.get('data',{}).get('data',{});rows=body.get('data',[])
    state['own_source_state']={k:body.get(k) for k in ('need_update','total','last_update','updated_at')}
    if rows and len({r.get('p_id') for r in rows})==len(rows) and body.get('total')==len(rows):
     state['own_summary']=dict(orders=sum(r['orders_count'] for r in rows),orders_sum=sum(r['orders_sum'] for r in rows),sales=sum(r['sales_count'] for r in rows),returns=sum(r['returns_count'] for r in rows),rows=len(rows),provisional=True)
  state['status']='received_provisional' if state.get('own_summary') and state.get('campaigns') else 'partial'
 except Exception as e:state.update(status='blocked',error=type(e).__name__)
 finally:
  requests.sessions.Session.request=original;state['finished_at']=datetime.now(timezone.utc).isoformat();put(state)
 print(json.dumps({k:state.get(k) for k in ('status','own_summary','missing_campaigns','error','wb_writes','telegram_calls')}))
if __name__=='__main__':main()
