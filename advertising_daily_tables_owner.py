"""Daily two-PNG delivery: retained data only, independent of saved analysis status."""
import os,sys,json,time
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
import requests
from advertising_agent import agent_store as store
from advertising_budget_evidence import load_daily_table_view,deliver_daily_tables
from advertising_daily_png import render_daily_png
from ip_budget_table_png import render_budget_png
from ip_daily_png_contract import build_contract,render_recommendations,freeze_plan,bind_receipt
from stock_deploy_support import seal,error
def publication_coverage(view):
 rows=view.get('campaigns') or []
 known=sum(1 for row in rows if row.get('metrics_complete') is True)
 return dict(ready=known>0,known=known,total=len(rows))
def main():
 report=dict(source_calls=0,wb_writes=0,telegram_calls=0,business_status='incomplete')
 native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
 def guard(session,method,url,*a,**kw):
  u=urlparse(url)
  if u.hostname==host and u.path.startswith('/rest/v1/'):pass
  elif u.hostname=='api.telegram.org' and method.upper()=='POST' and u.path.endswith('/sendPhoto'):report['telegram_calls']+=1
  else:raise PermissionError('Daily tables cannot collect sources or change WB')
  return native(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  reg=store.registration();approval=store.cache_get('advertising:ip:daily_rollout:v1') or {}
  if not approval.get('enabled') or approval.get('chat_id')!=reg['chat_id'] or approval.get('owner_id')!=reg['registered_by_user_id']:raise PermissionError('Existing daily owner approval mismatch')
  hold=store.cache_get('advertising:ip:notification_hold:v1') or {}
  if hold.get('paused') and hold.get('chat_id')==reg['chat_id']:
   report.update(business_status='complete',notification_status='held_by_owner',reason='Owner requested no sending; no Telegram calls')
   return report
  view=load_daily_table_view(store,datetime.now(timezone.utc))
  report['view']=view
  coverage=publication_coverage(view)
  report['campaign_coverage']=coverage
  if not coverage['ready']:
   report.update(business_status='incomplete',notification_status='not_sent',data_coverage='missing_daily_campaign_metrics',reason='No campaign/day metrics; both PNGs withheld before rendering or delivery claims')
   return report
  outdir=Path(os.environ['RUNNER_TEMP'])/'daily-advertising-png'
  from datetime import timedelta
  view['_recent_views']=[]
  for offset in (2,1):
   try:view['_recent_views'].append(load_daily_table_view(store,datetime.now(timezone.utc)-timedelta(days=offset)))
   except (ValueError,RuntimeError):pass # An independent historical gap must not block today's ready rows.
  contract=build_contract(store,view)
  # Reuse the same dated calculations for cloud answers; no model or source calls.
  try:
   from ip_cloud_dialog import publish_context
   publish_context(store,view,contract)
   report["cloud_context_status"]="prepared"
  except Exception as exc:
   report["cloud_context_status"]="unavailable:"+type(exc).__name__ # Independent cache issue never blocks ready PNGs.
  for c in view['campaigns']:
   c['campaign_name']=c.get('campaign_name') or (contract.get('campaign_labels',{}).get(str(c['campaign_id'])) or {}).get('name') or ''
  # Approved shortage-only budget format; same delivery slots, no payment actions.
  budget_image,budget_coverage=render_budget_png(view,outdir)
  report['budget_coverage']=budget_coverage
  if not budget_image:report['budget_notification_status']='withheld_no_current_budget_evidence'
  images=[render_recommendations(view,contract,outdir)]+([budget_image] if budget_image else [])
  import hashlib
  messages=[]
  for image in images:
   caption=('ИП · рекомендации за '+view['period']+'. Ответьте «Сделай всё» на этот PNG, чтобы применить только новые перечисленные действия. Ранее согласованные изменения не повторяются.' if contract['actions'] else 'ИП · отчёт за '+view['period']+'. Новых готовых команд нет.') if image['kind']=='drr' else ('Бюджеты · отчёт '+view['observed_day']+' · время МСК. Срок условный, по расходу '+view['period']+'.')
   messages.append(dict(kind=image['kind'],text=json.dumps(dict(path=image['path'],caption=caption,sha256=hashlib.sha256(Path(image['path']).read_bytes()).hexdigest()),ensure_ascii=False)))
  report['messages']=messages
  report['new_action_count']=len(contract['actions'])
  report['review_coverage']=contract.get('review_coverage')
  if os.environ.get('IP_DAILY_FORMAT_PREVIEW_ONLY')=='true':
   report.update(business_status='complete',notification_status='saved_preview_only_no_claims_no_telegram')
   return report
  plan_key,plan=freeze_plan(store,contract,json.loads(messages[0]['text'])['sha256'])
  last=[None]
  def send(chat,text):
   if last[0] is not None:
    wait=3.2-(time.monotonic()-last[0])
    if wait>0:time.sleep(wait)
   last[0]=time.monotonic()
   item=json.loads(text);path=Path(item['path'])
   if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('PNG changed after durable claim')
   with path.open('rb') as photo:
    response=requests.post('https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/sendPhoto',data={'chat_id':chat,'caption':item['caption']},files={'photo':(path.name,photo,'image/png')},timeout=(10,60))
   body=response.json();msg=body.get('result') or {};photos=msg.get('photo') or []
   receipt=dict(ok=response.status_code==200 and body.get('ok') is True and bool(photos),message_id=msg.get('message_id'),chat_id=(msg.get('chat') or {}).get('id'),media_sha256=item['sha256'],photo_file_unique_id=photos[-1].get('file_unique_id') if photos else None)
   if receipt['ok'] and receipt['chat_id']==reg['chat_id'] and item['path']==images[0]['path']:
    # Bind the confirmed first photo even if independent budget delivery later fails.
    bind_receipt(store,plan_key,plan,dict(receipt,status='confirmed'))
   return receipt
  from zoneinfo import ZoneInfo
  day=str(datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/Moscow')).date())
  report['receipts']=deliver_daily_tables(store,messages,reg['chat_id'],day,send)
  bind_receipt(store,plan_key,plan,report['receipts'][0])
  report['reply_plan_key']=plan_key
  report['new_action_count']=len(contract['actions'])
  report['business_status']='complete'
  report['data_coverage']='complete' if budget_image and all(x['metrics_complete'] for x in view['campaigns']) else 'partial_explicitly_labelled'
 except Exception as exc:report['error']=error(exc)
 finally:
  requests.sessions.Session.request=native
  seal('advertising-daily-tables',report)
  print(json.dumps({k:report.get(k) for k in ('business_status','data_coverage','source_calls','wb_writes','telegram_calls')}))
 return report
if __name__=='__main__':
 if main()['business_status']!='complete':raise SystemExit(1)
