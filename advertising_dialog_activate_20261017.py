"""Activate only saved-dialogue routing after privacy and webhook checks; no AI or seller sources."""
import os,sys,json,copy,hashlib
from datetime import datetime,timezone,timedelta
import requests
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store
from stock_deploy_support import seal
KEY='advertising:dialog_rollout:v1'
proof={'complete':False,'model_calls':0,'telegram_sends':0,'source_calls':0,'wb_writes':0,'registry_changed':False}
def hash_value(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
try:
 r=store.registration();token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
 def tg(method,params=None):
  response=requests.get('https://api.telegram.org/bot'+token+'/'+method,params=params,timeout=(5,20));data=response.json()
  if not response.ok or not data.get('ok'):raise RuntimeError('Telegram identity/config check failed')
  return data['result']
 me=tg('getMe');member=tg('getChatMember',dict(chat_id=r['chat_id'],user_id=me['id']));info=tg('getWebhookInfo')
 ready=bool(me.get('can_read_all_group_messages')) or member.get('status') in ('administrator','creator')
 proof.update(bot_username=me['username'],bot_membership=member.get('status'),can_read_all_group_messages=me.get('can_read_all_group_messages',False),group_text_delivery_ready=ready,openai_key_present=bool(os.environ.get('OPENAI_API_KEY','').strip()))
 base=os.environ['SUPABASE_URL'].rstrip('/')
 if info.get('url')!=base+'/functions/v1/advertising-agent-webhook':raise RuntimeError('Unexpected existing webhook URL')
 secret=hashlib.sha256(('veschi-advertising-agent-v1:'+token).encode()).hexdigest()
 response=requests.post(info['url'],headers={'X-Telegram-Bot-Api-Secret-Token':secret},json={'dialog_probe':True},timeout=(5,20))
 probe=response.json() if response.ok else {}
 if probe.get('dialog_contract')!='saved-dialog-v1':raise RuntimeError('Deploy reviewed webhook before activation')
 if not probe.get('dispatcher_token_present'):raise RuntimeError('Edge secret GITHUB_WORKFLOW_DISPATCH_TOKEN missing')
 if not ready:raise RuntimeError('Telegram privacy is enabled and bot is not administrator; Disable privacy then recheck')
 if not proof['openai_key_present']:raise RuntimeError('Existing OPENAI_API_KEY missing from public runner')
 before=store.cache_get('advertising:ip_pair_decisions:token_2:v1') or {}
 rows=store.db('GET','telegram_api_cache',params={'cache_key':'eq.'+KEY,'select':'payload,updated_at','limit':1}) or []
 previous=copy.deepcopy(rows[0]['payload'] if rows else {})
 stamp=datetime.now(timezone.utc).isoformat()
 desired=dict(previous,enabled=True,chat_id=r['chat_id'],owner_id=r['registered_by_user_id'],
  source_sha=os.environ['ADVERTISING_DIALOG_SOURCE_SHA'],
  enabled_at=previous.get('enabled_at') or stamp,route='saved-dialog-v1',model_calls_per_question=1,no_collectors=True,no_execution=True)
 body=dict(payload=desired,updated_at=stamp,expires_at=(datetime.now(timezone.utc)+timedelta(days=365)).isoformat())
 if rows:
  changed=store.db('PATCH','telegram_api_cache',params={'cache_key':'eq.'+KEY,'updated_at':'eq.'+rows[0]['updated_at'],'select':'payload'},body=body,prefer='return=representation') or []
 else:
  changed=store.db('POST','telegram_api_cache',params={'on_conflict':'cache_key','select':'payload'},body=dict(body,cache_key=KEY),prefer='resolution=ignore-duplicates,return=representation') or []
 if len(changed)!=1 or store.cache_get(KEY)!=desired:raise RuntimeError('Dialogue rollout CAS/readback mismatch')
 after=store.cache_get('advertising:ip_pair_decisions:token_2:v1') or {}
 if hash_value(before)!=hash_value(after):raise RuntimeError('Recommendation registry changed during activation')
 proof.update(complete=True,rollout_readback_verified=True,source_sha=desired['source_sha'],registry_unchanged=True,
  status='route_enabled_requires_actual_Telegram_question_and_followup')
except Exception as e:proof.update(error_type=type(e).__name__,error=str(e)[:180],status='not_enabled_or_not_verified')
seal('advertising-dialog-activation',proof)
print(json.dumps({k:proof.get(k) for k in ('complete','status','group_text_delivery_ready','model_calls','telegram_sends','source_calls','wb_writes','error_type')}))
if not proof['complete']:raise SystemExit(1)
