"""Owner-approved exact retained first overview; no business collection or WB calls."""
import os,sys,json,copy,hashlib,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()))
sys.path.insert(0,str(Path.cwd().parent))
from stock_deploy_support import seal
HASHES=["9e197667142eefb4adf0395cda4ab8207e6684de909f39b9fff81818b21d201f","c865c88589f4a98041708e98b7365357a846e38a6e049d1aaeb80ec6c3651a7d","89f5e4e1a73ba2f968d09ab4ebb3582e488feca51a0574c93eb1206f8c2bdbc3","be4f4c44c3e9c2d4804d6d48c1631267ac9c2d65eb1eff3647e1288115207a0f","eb79f221dc206ae3a86f3b59a2ae7600924f94257ed15c33796d13c38e8a793d","1a706f565b1f7e420cc75b0bbb077bcddb1bbcbaab463c386c1a4a4712ceac3a","442ba4f710416bbff32d7d85ddeb75cbca95dfce60ea73aaa6fb944d9273e295","2c0fc9f92dc9e4b8a58a1df13acbd808102acea5cd2c424a5fdc7c06360099c7","af4384efe201d15ec0320e51af8872b14300a670e49baaa5abdf3922cbe602c7","94d0ae86b4a9089781b9fc78521aca637303e7cef4c357e2c59cc197fb5cccd8","37de78fa24ad9d64e9ac66b7727d53b9c36cfba418d6715abb978255a3be9cde","81ee5718ddccacf8d323f3b1003a8c28b0a8869e607c117e4ed6b6a7fa52366f"]
proof=dict(complete=False,source_calls=0,wb_writes=0,telegram_calls=0,decoded_bytes=0,receipts=[])
native=requests.sessions.Session.request
allowed=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(session,method,url,*args,**kwargs):
 p=urlparse(str(url))
 if p.hostname==allowed and p.path.startswith('/rest/v1/') and method.upper() in ('GET','POST','PATCH'):pass
 elif p.hostname=='api.telegram.org' and p.path.endswith('/sendMessage') and method.upper()=='POST':
  if proof['telegram_calls']>=12:raise RuntimeError('Twelve calls maximum')
  proof['telegram_calls']+=1
 else:raise RuntimeError('Business source or WB transport forbidden')
 r=native(session,method,url,*args,**kwargs)
 proof['decoded_bytes']+=len(r.content)
 if proof['decoded_bytes']>100_000_000:raise RuntimeError('100MB limit')
 return r
requests.sessions.Session.request=guard
try:
 from analytics import ip_daily_recommendations as d
 from advertising_agent import agent_store as store
 from advertising_agent.notify import db,S
 now=datetime.now(timezone.utc)
 if now.astimezone(d.ZoneInfo('Europe/Moscow')).date().isoformat()!='2026-10-17':raise RuntimeError('Expired one-off authorization')
 registration=store.registration()
 prior=store.cache_get('advertising:ip:limited_rollout:v1') or {}
 if not(prior.get('owner_id')==registration['registered_by_user_id'] and prior.get('chat_id')==registration['chat_id'] and prior.get('policy_version')==d.POLICY_VERSION):raise RuntimeError('Registered owner mismatch')
 # Render only retained verified inputs. No collector or financial analysis runs.
 f=json.loads(Path('tests/fixtures/ip_growth_retained_20261017.json').read_text(encoding='utf-8'))
 report=f['daily']
 d.build_campaign_review(report,f['report'],f['investigations'],f['events'],datetime.fromisoformat(report['observed_at']))
 messages=d.campaign_review_messages(report,first_overview=True)
 hashes=[hashlib.sha256(m['text'].encode()).hexdigest() for m in messages]
 if hashes!=HASHES or len(messages)!=12 or len({m['campaign_id'] for m in messages if m['campaign_id']})!=11:raise RuntimeError('Approved exact preview mismatch')
 def state_row():
  rows=db('GET','telegram_api_cache',params={'cache_key':'eq.'+d.KEY,'select':'payload,updated_at','limit':1}) or []
  if len(rows)!=1:raise RuntimeError('Canonical state missing')
  return rows[0]
 baseline=state_row()
 initial_records=copy.deepcopy(baseline['payload'].get('records',{}))
 report['decision_state']['campaign_overview_outbox']=copy.deepcopy(baseline['payload'].get('campaign_overview_outbox',{}))
 holder={'expected':copy.deepcopy(report['decision_state']['campaign_overview_outbox'])}
 def save_state(scoped):
  current=state_row()
  if current['payload'].get('campaign_overview_outbox',{})!=holder['expected']:raise RuntimeError('Concurrent overview state change')
  merged=copy.deepcopy(current['payload'])
  merged['campaign_overview_outbox']=copy.deepcopy(scoped['campaign_overview_outbox'])
  stamp=datetime.now(timezone.utc).isoformat()
  params={'cache_key':'eq.'+d.KEY,'updated_at':('eq.'+current['updated_at']) if current.get('updated_at') else 'is.null','select':'payload,updated_at'}
  saved=db('PATCH','telegram_api_cache',params=params,body={'payload':merged,'updated_at':stamp},prefer='return=representation') or []
  if len(saved)!=1:raise RuntimeError('CAS conflict; stop')
  if state_row()['payload']!=merged:raise RuntimeError('Durable state readback mismatch')
  holder['expected']=copy.deepcopy(merged['campaign_overview_outbox'])
 def send_one(chat,text):
  if chat!=registration['chat_id'] or text not in [m['text'] for m in messages]:raise RuntimeError('Message scope mismatch')
  time.sleep(3) # Same-chat pacing; no automatic retry.
  r=S.post('https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/sendMessage',json={'chat_id':chat,'text':text},timeout=(10,30))
  if r.status_code==429:
   wait=(r.json().get('parameters') or {}).get('retry_after')
   if type(wait) in (int,float) and wait>0:raise d.DeliveryRateLimited(datetime.now(timezone.utc)+timedelta(seconds=wait))
  if r.status_code!=200:raise RuntimeError('Telegram outcome not confirmed')
  b=r.json();m=b.get('result') or {}
  receipt=dict(ok=b.get('ok') is True,message_id=m.get('message_id'),chat_id=(m.get('chat') or {}).get('id'),text_sha256=hashlib.sha256(text.encode()).hexdigest(),at=datetime.now(timezone.utc).isoformat())
  proof['receipts'].append(receipt)
  seal('first-review-progress',proof)
  return receipt
 consent=dict(owner_id=registration['registered_by_user_id'],chat_id=registration['chat_id'],first_campaign_review_approved=True,period_from=report['period_from'],period_to=report['period_to'],message_sha256=HASHES)
 proof['delivery']=d.approved_first_campaign_review(report,registration,consent,True,send_one,save_state,now)
 final=state_row()['payload']
 batch=proof['delivery']['batch'];parts=final.get('campaign_overview_outbox',{}).get(batch,{})
 proof['parts']=parts
 proof['recommendation_records_unchanged']=initial_records==final.get('records',{})
 proof['confirmed_count']=sum(p.get('status')=='confirmed' for p in parts.values())
 proof['complete']=proof['confirmed_count']==12 and proof['recommendation_records_unchanged'] and not proof['delivery'].get('failures')
 proof['status']='confirmed' if proof['complete'] else 'incomplete_no_automatic_retry'
 proof['hashes']=hashes
except Exception as exc:
 proof.update(status='incomplete_no_automatic_retry',error_type=type(exc).__name__,error=str(exc)[:180])
finally:
 requests.sessions.Session.request=native
 seal('approved-first-campaign-review',proof)
 print(json.dumps({k:proof.get(k) for k in ('complete','status','telegram_calls','confirmed_count','decoded_bytes','error_type','source_calls','wb_writes')}))
if not proof['complete']:raise SystemExit(1)
