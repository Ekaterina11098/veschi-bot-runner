"""Owner-authorized deployment metadata only. No analysis, collection, Telegram or WB."""
import os,sys,json,copy,hashlib,inspect
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()))
sys.path.insert(0,str(Path.cwd().parent))
from stock_deploy_support import seal
TARGET='d71a576d55f4e9c89aaa5fb5cc2177722c6176f9'
KEY='advertising:ip:daily_rollout:v1'
DECISIONS='advertising:ip_pair_decisions:token_2:v1'
proof=dict(complete=False,source_calls=0,telegram_calls=0,wb_writes=0,analysis_runs=0,decoded_bytes=0,approval_patches=0)
native=requests.sessions.Session.request
host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(session,method,url,*args,**kwargs):
 p=urlparse(str(url));method=method.upper();params=kwargs.get('params') or {}
 allowed=(p.hostname==host and (
  p.path=='/rest/v1/advertising_telegram_chat' and method=='GET' or
  p.path=='/rest/v1/telegram_api_cache' and method=='GET' and params.get('cache_key') in ('eq.'+KEY,'eq.'+DECISIONS) or
  p.path=='/rest/v1/telegram_api_cache' and method=='PATCH' and params.get('cache_key')=='eq.'+KEY))
 if not allowed:raise RuntimeError('Deployment-only transport scope rejected')
 if method=='PATCH':
  proof['approval_patches']+=1
  if proof['approval_patches']>1:raise RuntimeError('One CAS patch only')
 r=native(session,method,url,*args,**kwargs)
 proof['decoded_bytes']+=len(r.content)
 if proof['decoded_bytes']>100_000_000:raise RuntimeError('100MB limit')
 return r
requests.sessions.Session.request=guard
try:
 from advertising_agent import agent_store as store
 from analytics import ip_daily_recommendations as d
 def row(key):
  rows=store.db('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload,updated_at','limit':1}) or []
  if len(rows)!=1:raise RuntimeError('Required deployment state missing')
  return rows[0]
 def digest(payload):return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
 registration=store.registration()
 current=row(KEY);original=copy.deepcopy(current['payload'])
 if not(original.get('enabled') is True and original.get('owner_id')==registration['registered_by_user_id'] and original.get('chat_id')==registration['chat_id']):
  raise RuntimeError('Existing daily owner authorization mismatch')
 before=row(DECISIONS)['payload'];before_hash=digest(before)
 desired=copy.deepcopy(original);desired['source_sha']=TARGET
 proof['previous_source_sha']=original.get('source_sha')
 if original!=desired:
  params={'cache_key':'eq.'+KEY,'updated_at':('eq.'+current['updated_at']) if current.get('updated_at') else 'is.null','select':'payload,updated_at'}
  saved=store.db('PATCH','telegram_api_cache',params=params,body={'payload':desired,'updated_at':datetime.now(timezone.utc).isoformat()},prefer='return=representation') or []
  if len(saved)!=1:raise RuntimeError('Approval CAS conflict; stop without repeat')
 readback=row(KEY)['payload']
 if readback!=desired:raise RuntimeError('Approval readback mismatch')
 unchanged_other={k:v for k,v in original.items() if k!='source_sha'}=={k:v for k,v in readback.items() if k!='source_sha'}
 if not unchanged_other:raise RuntimeError('Unexpected approval field change')
 after=row(DECISIONS)['payload']
 if digest(after)!=before_hash:raise RuntimeError('Recommendation state changed during deployment')
 # Existing entrypoint chain inspection only, no analysis/notification invocation.
 source=inspect.getsource(d.campaign_review_messages)
 wrapper=inspect.getsource(d.render_campaign_messages)
 bridge=Path('analytics/ip_decision_bridge.py').read_text()
 if not('return campaign_review_messages(report,first_overview=False)' in wrapper and 'return build_campaign_review(' in bridge):
  raise RuntimeError('Existing daily formatter hook missing')
 exact='Предлагается на 24 часа исключить только 57-NoelBag-burgundy из РК 39410834, сохранив его CPC-рекламу. Остальные товары этой РК не менять'
 if exact not in source or 'CPC — оплата за клики' not in source or 'CPM — оплата за показы' not in source:raise RuntimeError('Approved presentation missing')
 continuation=json.loads((Path.cwd().parent/'advertising_daily_continue.json').read_text())
 if continuation.get('enabled') is not False:raise RuntimeError('One-off continuation must stay disabled')
 proof.update(complete=True,status='deployed_metadata_verified',source_sha=TARGET,approval_readback_verified=True,
  approval_other_fields_unchanged=True,recommendation_state_unchanged=True,recommendation_state_sha256=before_hash,
  records_count=len(after.get('records',{})),daily_entrypoint_verified=True,continuation_enabled=False,
  record_receipts_unchanged=True,outbox_unchanged=True)
except Exception as exc:
 proof.update(status='deployment_verification_failed',error_type=type(exc).__name__,error=str(exc)[:160])
finally:
 requests.sessions.Session.request=native
 seal('advertising-format-activation',proof)
 print(json.dumps({k:proof.get(k) for k in ('complete','status','source_calls','telegram_calls','wb_writes','analysis_runs','approval_patches','decoded_bytes','error_type')}))
if not proof['complete']:raise SystemExit(1)
