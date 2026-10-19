"""Owner-authorized MPStats gap reads only. Fixed provider/tools; never WB writes or Telegram.
Run only under the runner's shared bot-mpstats-data concurrency group.
Uses a separately pinned, unchanged private normalizer and restores provider cabinet selection.
"""
import contextlib,io,json,os,sys,signal
from pathlib import Path
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'private-source'))
from analytics.mpstats_probe import discover,unpack_tool,complete_products,CABINETS,ProbeError
from analytics.mpstats_recovery import normalize

def db(method,table,params=None,body=None):
 if table not in ('analytics_snapshots','telegram_api_cache'):raise ValueError('Forbidden table')
 if method=='POST' and table=='analytics_snapshots' and body.get('source')!='owner_mpstats_products':raise ValueError('Forbidden source')
 if method=='POST' and table=='telegram_api_cache' and body.get('cache_key')!='mpstats:cooldown':raise ValueError('Forbidden cache')
 key=os.environ['SUPABASE_SECRET_KEY'];url=os.environ['SUPABASE_URL'].rstrip('/')
 if not url.startswith('https://') or not url.endswith('.supabase.co'):raise ValueError('Invalid DB URL')
 headers={'apikey':key,'Content-Type':'application/json','Prefer':'resolution=merge-duplicates,return=representation'}
 if not key.startswith('sb_secret_'):headers['Authorization']='Bearer '+key
 r=requests.request(method,url+'/rest/v1/'+table,params=params,json=body,headers=headers,timeout=(10,40),allow_redirects=False)
 if not r.ok:raise RuntimeError('Database HTTP '+str(r.status_code))
 return r.json() if r.content else None

def collect(scope):
 a=date.fromisoformat(scope['from']);b=date.fromisoformat(scope['to'])
 yesterday=datetime.now(ZoneInfo('Europe/Moscow')).date()-timedelta(days=1)
 if not 0<=(b-a).days<=30 or b>yesterday:raise ValueError('Completed exact period required')
 cabinets=scope.get('cabinets',list(CABINETS))
 if not isinstance(cabinets,list) or not cabinets or any(c not in CABINETS for c in cabinets) or len(cabinets)>3:raise ValueError('Invalid cabinets')
 now=datetime.now(timezone.utc);result={'reports':[],'wb_calls':0,'telegram_sends':0}
 pause=db('GET','telegram_api_cache',{'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+now.isoformat(),'select':'expires_at','limit':1})
 if pause:return {**result,'status':'provider_cooldown','retry_after_at':pause[0]['expires_at']}
 pending=[]
 for cabinet in cabinets:
  cached=db('GET','analytics_snapshots',{'source':'in.(mpstats_products_validated,owner_mpstats_products)','cabinet':'eq.'+cabinet,'period_from':'eq.'+str(a),'period_to':'eq.'+str(b),'status':'eq.complete','payload->0->>complete':'eq.true','select':'id','order':'id.desc','limit':1})
  if cached:result['reports'].append({'cabinet':cabinet,'status':'cached','id':cached[0]['id']})
  else:pending.append(cabinet)
 if not pending:return {**result,'status':'cached'}
 def reader(call,checks,known):
  if not {'lk_wb_cabinets','lk_wb_products'}.issubset(known):raise ProbeError('required_tool_unavailable')
  listed=checks['lk_wb_cabinets'];selected=[r['id'] for r in listed if r.get('selected')]
  if len(selected)>1:raise ProbeError('ambiguous_original_selection')
  def tool(name,args):
   if name not in ('lk_wb_cabinets','lk_wb_products'):raise ValueError('Forbidden provider tool')
   return unpack_tool(call('tools/call',{'name':name,'arguments':args}))
  def verify(identity):
   current=tool('lk_wb_cabinets',{'action':'list'})
   if [r.get('id') for r in current if r.get('selected')]!=[identity]:raise ProbeError('cabinet_selection_changed')
  try:
   for cabinet in pending:
    identity,name=CABINETS[cabinet]
    if len([r for r in listed if r.get('id')==identity and r.get('name')==name and r.get('valid') is True])!=1:raise ProbeError('cabinet_identity_unverified')
    tool('lk_wb_cabinets',{'action':'select','id':identity});verify(identity)
    args={'date_from':str(a),'date_to':str(b),'start_row':0,'end_row':300}
    def scoped_tool(name,params):
     verify(identity);value=tool(name,params);verify(identity);return value
    raw=scoped_tool('lk_wb_products',args)
    raw=complete_products(scoped_tool,args,raw)
    obs={'tool':'lk_wb_products','arguments':args,'data':raw,'scope_verified':True,'status':'received','observed_at':now.isoformat(),'request_key':'owner:'+cabinet+':'+str(a)+':'+str(b)}
    _,normalized=normalize(obs,cabinet)
    text=json.dumps(normalized,ensure_ascii=False)
    if len(text.encode())>5_000_000:raise ProbeError('report_storage_limit')
    record={'source':'owner_mpstats_products','cabinet':cabinet,'period_from':str(a),'period_to':str(b),'status':'complete','run_id':'owner:'+os.environ.get('GITHUB_RUN_ID','manual'),'payload':[normalized],'detail':'Owner-authorized exact-period MPStats recovery. Provider cabinet verified before/after pages. Own profit not verified.'}
    receipt=db('POST','analytics_snapshots',body=record)
    if not receipt or receipt[0].get('cabinet')!=cabinet:raise ProbeError('storage_receipt_missing')
    result['reports'].append({'cabinet':cabinet,'status':'saved','id':receipt[0]['id'],'product_records':len(normalized['products'])})
  finally:
   tool('lk_wb_cabinets',{'action':'select','id':selected[0]} if selected else {'action':'reset'})
  return {'saved':len(result['reports'])}
 # Private dependency/provider output is never forwarded to public logs.
 with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
  connection=discover(os.environ.get('MPSTATS_API_TOKEN',''),read_checks=True,extra_reader=reader)
 result['status']=connection.get('status','unknown')
 if connection.get('retry_after'):
  until=(datetime.now(timezone.utc)+timedelta(seconds=connection['retry_after'])).isoformat()
  db('POST','telegram_api_cache',{'on_conflict':'cache_key'},{'cache_key':'mpstats:cooldown','payload':{'pending':True,'source':'owner_agent'},'expires_at':until})
  result['retry_after_at']=until
 return result

if __name__=='__main__':
 def interrupted(signum,frame):raise ProbeError('collection_interrupted')
 signal.signal(signal.SIGTERM,interrupted)
 signal.signal(signal.SIGINT,interrupted)
 try:print(json.dumps(collect(json.loads(sys.argv[1]))))
 except Exception as e:print(json.dumps({'status':'collection_failed','reason':getattr(e,'status',str(e) if isinstance(e,ValueError) else type(e).__name__),'error_type':type(e).__name__,'reports':[],'wb_calls':0,'telegram_sends':0}));sys.exit(0)
