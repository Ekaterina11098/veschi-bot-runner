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
def main():
 p=DB().get(ROOT+':approval')or{}
 if p.get('owner_user_id')!=5122667182:raise ValueError('Owner migration scope missing')
 stage=p.get('stage')
 if stage=='prepare_live':prepare()
 elif stage=='publish_live':publish()
 elif stage=='price_preview':price_preview()
 else:raise ValueError('Unknown live validation stage')
if __name__=='__main__':main()
