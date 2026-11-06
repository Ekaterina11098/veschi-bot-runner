"""Dated migration live preview/publication. WB is read-only in preview; publish has no WB capability."""
import os,json,base64,hashlib,copy
from datetime import datetime,timezone
from china_codex_cloud import DB
ROOT='china_agent:cloud_migration:2026-11-03:v1'
DAY='2026-11-03'
def stamp():return datetime.now(timezone.utc).isoformat()
def put(io,key,value):
 if io.get(key) is None:
  if not io.create(key,value):raise ValueError('Concurrent migration state')
 else:io.put(key,value)
def prepare():
 from china_price_apply import IO
 from china_advertising_v2 import collect,MSK,sums
 from china_advertising_midday import prepare_midday,only_completed_day_actions,render_midday
 from china_midday_completed_review import include_closed,attach,merge_completed
 from china_codex_reports import review_advertising
 from china_daily_ad_actions import plan
 class ReadIO(IO):
  def __init__(self):
   os.environ.setdefault('CHINA_TELEGRAM_BOT_TOKEN','disabled');super().__init__()
  def wb(self,path,method='GET',body=None):
   if method!='GET':raise ValueError('No marketplace writes in migration preview')
   return super().wb(path,method,body)
  def tg(self,*a,**kw):raise ValueError('No Telegram in preview')
 io=ReadIO()
 if io.get(ROOT+':live_artifacts'):print('Live preview already frozen');return
 state=dict(status='preparing',started_at=stamp(),wb_writes=0,telegram_calls=0);put(io,ROOT+':live_state',state)
 try:
  if datetime.now(MSK).date().isoformat()!=DAY:raise ValueError('Dated migration preview scope')
  current=include_closed(io,collect(io,DAY,current=True),DAY);observed=prepare_midday(io,DAY,current)
  attach(io,observed,DAY)
  closed=io.get('china_agent:advertising_midday_completed:'+DAY+':v1')
  if not closed or closed.get('status')!='complete':raise ValueError('Completed-day source missing')
  source=closed['source'];review=review_advertising(io,closed['review'],source,'migration-live-ad3',observed,True)
  if not io.create(ROOT+':live_completed',dict(source=source,review=review,status='complete',observed_at=stamp(),wb_writes=0)):raise ValueError('Source already frozen')
  b=only_completed_day_actions(merge_completed(observed,review,ROOT+':live_completed'))
  if any(c['today'] is None for c in b['campaigns']):raise ValueError('Current campaign coverage incomplete')
  b['fresh_current_totals']=sums([c['today']for c in b['campaigns']]);b['correction_of_message_ids']=[665]
  pages=render_midday(b);files=[]
  for index,f in enumerate(pages):
   p=plan(io,DAY,f,index,slot='cloud-cutover3')
   files.append(dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],action_count=len(p['items']),sha256=hashlib.sha256(f['bytes']).hexdigest(),b64=base64.b64encode(f['bytes']).decode()))
  artifact=dict(status='frozen',day=DAY,bundle=b,files=files,observed_at=b['observed_at'],producer='codex_cloud',created_at=stamp(),wb_writes=0)
  if not io.create(ROOT+':live_artifacts',artifact):raise ValueError('Concurrent artifact')
  manifest=dict(status='review_ready',artifact_sha256=hashlib.sha256(json.dumps(artifact,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),source_observed_at=b['observed_at'],totals=b['fresh_current_totals'],page_count=len(files),action_count=sum(f['action_count']for f in files),directions={k:dict(status=v['status'],count=v.get('count'),note=v.get('note'))for k,v in b['recommendation_directions'].items()},research=b['codex_analysis'].get('research'),analysis_receipt=b['codex_analysis'],wb_writes=0,telegram_calls=0)
  put(io,ROOT+':live_manifest',manifest);put(io,ROOT+':live_state',dict(state,status='prepared',completed_at=stamp()));print('Managed Codex live report preview prepared; no writes/sends')
 except Exception as ex:
  put(io,ROOT+':live_state',dict(state,status='blocked',error_type=type(ex).__name__,detail=str(ex)[:500],finished_at=stamp()));raise
def publish():
 from china_price_apply import IO
 from china_advertising_v2 import event_time
 from china_advertising_delivery import deliver,telegram_sender
 from china_daily_ad_actions import bind
 class SendIO(IO):
  def __init__(self):os.environ.setdefault('WB_TOKEN_3','disabled');super().__init__()
  def wb(self,*a,**kw):raise ValueError('No marketplace access in publication')
 io=SendIO();a=io.get(ROOT+':approval')or{};art=io.get(ROOT+':live_artifacts')
 if a.get('owner_user_id')!=5122667182 or a.get('stage')!='publish_live' or a.get('visual_review_completed')is not True:raise ValueError('Reviewed owner publication authorization missing')
 if not art or art.get('producer')!='codex_cloud':raise ValueError('Actual cloud-produced report absent')
 if hashlib.sha256(json.dumps(art,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()!=a.get('artifact_sha256'):raise ValueError('Reviewed source changed')
 if not 0<=(datetime.now(timezone.utc)-event_time(art['observed_at'])).total_seconds()<=4800:raise ValueError('Preview too old; do not label current')
 files=[]
 for f in art['files']:
  content=base64.b64decode(f['b64'],validate=True)
  if hashlib.sha256(content).hexdigest()!=f['sha256']:raise ValueError('PNG hash mismatch')
  caption='Китай · отчёт облачного Codex · 03.11 · '+str(f['page'])+'/'+str(f['total'])+'. Заменяет №665. Рекомендации — по завершённым дням до 02.11; текущий срез указан в PNG. '
  caption+=('Ответьте «Сделай всё» для '+str(f['action_count'])+' новых действий только этого PNG.'if f['action_count']else'Готовых действий для исполнения нет.')
  files.append(dict(f,bytes=content,caption=caption))
 receipt=deliver(io,DAY,files,telegram_sender(io),binder=lambda f,r:bind(io,f,r),delivery_key=ROOT+':live_delivery',expected_families={'drr'})
 if receipt.get('status')!='delivered' or any(x.get('status')!='sent'or not x.get('message_id')for x in receipt['parts']):raise ValueError('Cloud report delivery incomplete')
 for key in ['china_agent:advertising_midday_artifacts:'+DAY+':v1','china_agent:advertising_midday_delivery:'+DAY+':v1']:
  if io.get(ROOT+':before:'+key)is None:io.create(ROOT+':before:'+key,io.get(key))
 io.put('china_agent:advertising_midday_artifacts:'+DAY+':v1',art)
 io.put('china_agent:advertising_midday_delivery:'+DAY+':v1',dict(receipt,producer='codex_cloud',migration_root=ROOT,replaces_message_ids=[665]))
 value=dict(status='verified',producer='codex_cloud',message_ids=[x['message_id']for x in receipt['parts']],completed_at=stamp(),wb_writes=0,source_observed_at=art['observed_at'],analysis_receipt=art['bundle']['codex_analysis'])
 put(io,ROOT+':delivery_proof',value);print(json.dumps(dict(status=value['status'],message_ids=value['message_ids'],wb_writes=0)))
def price_preview():
 import china_codex_reports as reports
 original=reports.review_price
 def force(worker,draft,trace,*args,**kw):return original(worker,draft,trace,force=True)
 reports.review_price=force
 from china_agent.morning_pair import PairWorker
 from china_agent.coverage_worker import CoverageWorker
 from china_agent.daily_report_worker import MSK
 from china_price_apply import IO
 io=IO();results=[]
 for kind in ('morning','intraday'):
  key=ROOT+':price_preview:'+kind
  if io.get(key):results.append(io.get(key));continue
  worker=PairWorker('candidates') if kind=='morning'else CoverageWorker('intraday')
  try:
   worker.run(preview=True)
   value=dict(kind=kind,status=worker.audit.get('status'),audit=worker.audit,wb_writes=worker.audit.get('wb_writes',0),telegram_calls=0)
   if not worker.audit.get('codex_analysis'):raise ValueError('Actual price preview did not use cloud Codex')
   io.create(key,value);results.append(value)
  finally:
   import requests
   requests.sessions.Session.request=worker.original_http
 put(io,ROOT+':price_preview_result',dict(status='verified',modes=[v['kind']for v in results],completed_at=stamp(),wb_writes=0,telegram_calls=0))
 print('Actual pricing acquisition and cloud review verified; no sends/writes')

def growth_check():
 from china_price_apply import IO
 from china_morning_readiness import enrich_economics
 from china_advertising_v2 import http,history
 class ReadIO(IO):
  def __init__(self):os.environ.setdefault('CHINA_TELEGRAM_BOT_TOKEN','disabled');super().__init__()
  def wb(self,path,method='GET',body=None):
   if method!='GET':raise ValueError('No marketplace writes')
   return super().wb(path,method,body)
  def tg(self,*a,**kw):raise ValueError('No Telegram in growth check')
 io=ReadIO();saved=io.get(ROOT+':live_completed')
 if not saved or saved.get('status')!='complete':raise ValueError('Exact completed source missing')
 targets=[(40933588,1473243894),(41296359,1473242584),(41187173,1560230895),(41298169,1473243896),(40933588,1473244357)]
 rough=dict(campaigns=[dict(focus=[dict(nm=nm)for _,nm in targets])])
 source=enrich_economics(io,copy.deepcopy(saved['source']),rough,DAY);quotes={};errors={}
 for cid,nm in targets:
  try:
   raw=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=[nm],payment_type='cpc',placement_types=['search'if cid in [41296359,41298169]else'recommendation']))
   quotes[str(cid)+':'+str(nm)]=raw
  except Exception as ex:errors[str(nm)]=type(ex).__name__
 value=dict(status='complete',observed_at=stamp(),source=source,minima=quotes,quote_errors=errors,targets=targets,history=history(source.get('executions',[])),wb_writes=0,telegram_calls=0)
 put(io,ROOT+':growth_economics',value)
 from china_advertising_midday import render_midday
 art=io.get(ROOT+':live_artifacts');pages=render_midday(art['bundle'])
 if len(pages)!=1 or pages[0]['actions']!=io.get('china_agent:loss_plan:v1:'+art['files'][0]['plan_id'])['items']:raise ValueError('Unchanged action-plan identity required')
 f=pages[0];clean=dict(status='review_ready',b64=base64.b64encode(f['bytes']).decode(),sha256=hashlib.sha256(f['bytes']).hexdigest(),message_id=667,plan_id=art['files'][0]['plan_id'],wb_writes=0,telegram_calls=0)
 put(io,ROOT+':clean_png',clean);print('Five exact growth candidates reviewed with fresh economics/stock and bid quotes, no writes/sends')


def correct_png():
 import requests
 from china_price_apply import IO
 from china_advertising_midday import render_midday
 os.environ.setdefault('WB_TOKEN_3','disabled')
 io=IO();approval=io.get(ROOT+':approval')or{}
 if approval.get('owner_user_id')!=5122667182 or approval.get('stage')!='correct_png':raise ValueError('Owner correction scope missing')
 key=ROOT+':png667_cleanup'
 if io.get(key):raise ValueError('Existing correction receipt: do not repeat uncertain edits')
 art=io.get(ROOT+':live_artifacts');bundle=copy.deepcopy(art['bundle'])
 for row in bundle['campaigns']:row['codex_research_recommendations']=[]
 pages=render_midday(bundle)
 plan=io.get('china_agent:loss_plan:v1:'+art['files'][0]['plan_id'])
 if len(pages)!=1 or pages[0]['actions']!=plan['items']or plan['report_message_ids']!=[667]:raise ValueError('Action plan must remain identical')
 content=pages[0]['bytes'];sha=hashlib.sha256(content).hexdigest()
 if io.tg('getMe',{}).get('id')!=8780468043:raise ValueError('Wrong bot')
 if not io.create(key,dict(status='submitting',message_id=667,sha256=sha,started_at=stamp(),wb_writes=0)):raise ValueError('Correction already claimed')
 try:
  r=requests.post('https://api.telegram.org/bot'+io.bot+'/editMessageMedia',data={'chat_id':'-1004342917488','message_id':'667','media':json.dumps(dict(type='photo',media='attach://photo',caption='Китай · 03.11 · срез 17:30 МСК. Расход 1 127,98 CNY; ДРР 3,89%. Только три готовых действия. Ответьте «Сделай всё» для действий этого PNG.'),ensure_ascii=False)},files={'photo':('report.png',content,'image/png')},timeout=60)
  j=r.json()
  if not r.ok or not j.get('ok')or j['result'].get('message_id')!=667:raise RuntimeError('PNG correction not verified')
  proof=dict(status='verified',message_id=667,sha256=sha,receipt=j['result'],completed_at=stamp(),wb_writes=0,actions_unchanged=True)
  io.put(key,proof)
 except Exception as ex:
  io.put(key,dict(status='uncertain',message_id=667,error_type=type(ex).__name__,wb_writes=0));raise
 io.create(ROOT+':before_png667_cleanup',art)
 art['bundle']=bundle;art['files'][0].update(b64=base64.b64encode(content).decode(),sha256=sha);art['correction_receipt']=key
 io.put(ROOT+':live_artifacts',art);io.put('china_agent:advertising_midday_artifacts:'+DAY+':v1',art)
 io.put(ROOT+':clean_png',dict(status='verified',b64=base64.b64encode(content).decode(),sha256=sha,message_id=667,wb_writes=0))
 print('Existing PNG667 corrected; three bound actions unchanged; no marketplace actions')


def api_recheck():
 from china_codex_cloud import Worker
 db=DB();worker=Worker(db)
 value=dict(status='checking',observed_at=stamp(),model='gpt-6.1-sol',wb_writes=0,telegram_calls=0)
 put_db=lambda val:db.update(ROOT+':api_recheck_latest',val) if db.get(ROOT+':api_recheck_latest') else db.once(ROOT+':api_recheck_latest',val)
 put_db(value)
 try:
  with worker.sdk().beta.agents.sessions.create(agent={'model':'gpt-6.1-sol','instructions':'Ответь только ОК.'},environment={'type':'none'},input='Проверка доступности API: ответь ОК.',stream=True).with_result_collection() as events:
   for event in events:
    if event.type.endswith(('.failed','.cancelled')):raise RuntimeError('Availability probe failed')
   sid=events.get_final_result().session_id
  value.update(status='available',session_id=sid,completed_at=stamp());put_db(value)
  print('Actual managed API request available')
  price_preview()
 except Exception as ex:
  body=getattr(ex,'body',None)
  value.update(status='unavailable',error_type=type(ex).__name__,error_body=body,completed_at=stamp());put_db(value)
  print('Cloud API or remaining live validation unavailable: '+type(ex).__name__)


def verify_cutover():
 from china_codex_analysis import active
 from china_codex_routing import bound_execution
 db=DB();p=db.get('china_agent:analysis_backend:v1')or{};bridge=db.get('china_agent:codex_bridge:v1:policy')or{};cloud=db.get('china_agent:codex_cloud:v1:policy')or{}
 if not active(db) or p.get('legacy_analysis_enabled')is not False or bridge.get('legacy_analysis_enabled')is not False:raise ValueError('Legacy analysis not disabled')
 if cloud.get('session_key')!='china_agent:codex_cloud:v2:session' or not db.get(cloud['session_key']):raise ValueError('Tested cloud session not selected')
 if (db.get(ROOT+':price_preview_result')or{}).get('status')!='verified':raise ValueError('Pricing verification absent')
 if (db.get(ROOT+':delivery_proof')or{}).get('status')!='verified' or (db.get(ROOT+':png667_cleanup')or{}).get('status')!='verified':raise ValueError('Real delivery proof absent')
 configs=db.api('GET','business_agent_config',{'agent_id':'eq.china','select':'agent_id,active,chat_id'})
 if len(configs)!=1 or configs[0].get('active')is not True or configs[0]['chat_id']!=-1004342917488:raise ValueError('Bot transport configuration changed')
 class Bound:
  def get(self,key):return db.get(key)
 j=dict(request_text='Сделай всё',tool_trace=[dict(name='china_saved_question',bot_id=8780468043,reply_message_id=667,forwarded=False)])
 if not bound_execution(Bound(),j):raise ValueError('Exact PNG confirmation routing missing')
 if bound_execution(Bound(),dict(j,request_text='Сделай таблицу расходов')):raise ValueError('Question incorrectly becomes execution')
 value=dict(status='verified',verified_at=stamp(),legacy_analysis_disabled=True,bot_transport_active=True,collectors_and_schedules_preserved=True,png667_confirmation_binding_verified=True,pricing_live_reviews_verified=True,wb_writes=0,telegram_calls=0,model_calls=0)
 key=ROOT+':cutover_readback'
 if db.get(key):db.update(key,value)
 else:db.once(key,value)
 print('Cloud cutover verified by exact policy/session/receipt/PNG readback; zero model/WB/TG calls')

def main():
 p=DB().get(ROOT+':approval')or{}
 if p.get('owner_user_id')!=5122667182:raise ValueError('Owner migration scope missing')
 stage=p.get('stage')
 if stage=='prepare_live':prepare()
 elif stage=='publish_live':publish()
 elif stage=='price_preview':price_preview()
 elif stage=='growth_check':growth_check()
 elif stage=='correct_png':correct_png()
 elif stage=='api_recheck':api_recheck()
 elif stage=='verify_cutover':verify_cutover()
 else:raise ValueError('Unknown live validation stage')
if __name__=='__main__':main()
