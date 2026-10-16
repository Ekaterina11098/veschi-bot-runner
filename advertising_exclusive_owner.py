"""Only current IP campaign membership and remaining budgets, using existing cooldowns."""
import os,sys,json,io,contextlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report={'wb_writes':0,'telegram_calls':0,'calls':[]}
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  from advertising_agent import collect_ip as c
  from urllib.parse import urlsplit
  import requests
  original=requests.sessions.Session.request
  host=urlsplit(os.environ['SUPABASE_URL']).hostname
  allowed={'/adv/v1/promotion/count','/api/advert/v2/adverts','/adv/v1/budget'}
  def guarded(session,method,url,*args,**kwargs):
   p=urlsplit(url)
   if p.hostname!=host:
    read_post={'/api/advert/v1/bids/min','/adv/v2/supplier/nms','/adv/v0/normquery/get-minus'}
    permitted=(method.upper()=='GET' and p.path in allowed) or (os.getenv('FOCUS57_CAPABILITY')=='true' and method.upper()=='POST' and p.path in read_post)
    if p.hostname!='advert-api.wildberries.ru' or not permitted:raise RuntimeError('Exclusive WB read allowlist rejected request')
    report['calls'].append({'method':method,'path':p.path})
   return original(session,method,url,*args,**kwargs)
  requests.sessions.Session.request=guarded
  if os.getenv('FOCUS57_CAPABILITY')=='true':
   report.update(scope='57_read_capability',nm_id=1007948808,campaign_id=39410834,execution_authorized=False)
   blocked,remaining=c.cooldown_active('focus57_capability')
   if blocked:report.update(blocked=True,retry_after=remaining);raise SystemExit(0)
   checks=[('configuration','GET','/api/advert/v2/adverts',None,{'ids':'39410834'}),
    ('minimum','POST','/api/advert/v1/bids/min',{'advert_id':39410834,'nm_ids':[1007948808],'payment_type':'cpm','placement_types':['recommendation']},None),
    ('eligible','POST','/adv/v2/supplier/nms',[50],None),
    ('minus','POST','/adv/v0/normquery/get-minus',{'items':[{'advert_id':39410834,'nm_id':1007948808}]},None)]
   report['checks']=[]
   for label,method,path,body,params in checks:
    response=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':os.environ['WB_TOKEN_2']},json=body,params=params,timeout=45)
    try:data=response.json()
    except ValueError:data={'response_text':response.text[:1000]}
    if label=='eligible' and isinstance(data,list):data={'returned':len(data),'target':[x for x in data if x.get('nm')==1007948808 or x.get('nm_id')==1007948808]}
    report['checks'].append(dict(check=label,http=response.status_code,retry_after=response.headers.get('Retry-After'),data=data))
    if response.status_code==429:break
   raise SystemExit(0)
  key='advertising:recovery:exclusive-health:'+os.environ['GITHUB_RUN_ID']
  from datetime import datetime,timedelta,timezone
  now=datetime.now(timezone.utc);value={'scope':'ip-exclusive-read','run':os.environ['GITHUB_RUN_ID']}
  c.db('POST','telegram_api_cache',dict(cache_key=key,payload=value,expires_at=(now+timedelta(days=90)).isoformat()),params={'on_conflict':'cache_key'})
  assert c.db('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload','limit':1})[0]['payload']==value
  from advertising_daily_runtime_guard import membership_cache_valid
  daily_snapshot=c.daily_snapshot
  def fresh_daily(source,*args,**kwargs):
   value=daily_snapshot(source,*args,**kwargs)
   return value if membership_cache_valid(value,now) else None
  c.daily_snapshot=fresh_daily
  allids,active,raw,reused=c.campaign_index(os.environ['WB_TOKEN_2'])
  report.update(active_campaign_ids=active,total_campaigns=len(allids),index_reused=reused)
  old=c.daily_snapshot('advertising_active_configuration')
  if not old and active:
   data=c.wb('GET','https://advert-api.wildberries.ru/api/advert/v2/adverts',os.environ['WB_TOKEN_2'],'active_configuration',{'ids':','.join(map(str,active))})
   adverts=(data or {}).get('adverts')
   if not isinstance(adverts,list) or {x.get('id') for x in adverts}!=set(active):raise RuntimeError('Incomplete current campaign membership')
   c.save('advertising_active_configuration',{'campaign_ids':active,'adverts':adverts})
  # Budgets remain exclusively owned by the already running sequential collector.
  report['configuration']=c.latest('advertising_active_configuration',status=None)
  report['budgets']=c.latest('advertising_campaign_budgets',status=None)
  report['storage_readback']=bool(report['configuration'] and report['budgets'])
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-exclusive',report)
 print(json.dumps({'active_campaign_count':len(report.get('active_campaign_ids',[])),'wb_reads':len(report['calls']),'wb_writes':0,'telegram_calls':0,'error_type':report.get('error',{}).get('type')}))
