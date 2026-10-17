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
  if not response.ok or not data.get('ok'):
   proof.update(telegram_method=method,telegram_error=data.get('description'),telegram_parameters=data.get('parameters'))
   raise RuntimeError('Telegram identity/config check failed')
  return data['result']
 me=tg('getMe')
 old_chat=r['chat_id']
 try:
  tg('getChatAdministrators',dict(chat_id=old_chat))
 except RuntimeError:
  migrated=(proof.get('telegram_parameters') or {}).get('migrate_to_chat_id')
  if not isinstance(migrated,int):raise
  target=tg('getChat',dict(chat_id=migrated))
  membership=tg('getChatMember',dict(chat_id=migrated,user_id=me['id']))
  owner=tg('getChatMember',dict(chat_id=migrated,user_id=r['registered_by_user_id']))
  proof.update(migration_from=old_chat,migration_to=migrated,target_chat_title=target.get('title'),target_chat_type=target.get('type'),target_bot_status=membership.get('status'),target_owner_status=owner.get('status'))
  if target.get('id')!=migrated or target.get('type')!='supergroup' or membership.get('status') not in ('administrator','creator') or owner.get('status') not in ('administrator','creator'):raise RuntimeError('Migration identity verification failed')
  rows=store.db('PATCH','advertising_telegram_chat',params={'chat_id':'eq.'+str(old_chat),'is_active':'eq.true','registered_by_user_id':'eq.'+str(r['registered_by_user_id']),'select':'chat_id,registered_by_user_id'},body={'chat_id':migrated},prefer='return=representation') or []
  if len(rows)!=1 or store.registration()!=dict(r,chat_id=migrated):raise RuntimeError('Migration CAS/readback mismatch')
  r=store.registration();proof.update(registration_migration_verified=True)
  proof.pop('telegram_error',None);proof.pop('telegram_parameters',None);proof.pop('telegram_method',None)
 proof.update(bot_id=me['id'],bot_username=me.get('username'),bot_name=me.get('first_name'),registered_chat_id=r['chat_id']);chat=tg('getChat',dict(chat_id=r['chat_id']));proof.update(resolved_chat_id=chat.get('id'),chat_title=chat.get('title'),chat_type=chat.get('type'),linked_chat_id=chat.get('linked_chat_id'));member=tg('getChatMember',dict(chat_id=r['chat_id'],user_id=me['id']));info=tg('getWebhookInfo');proof.update(webhook_pending=info.get('pending_update_count'),webhook_last_error=info.get('last_error_message'))
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
 aligned=[]
 for key in ('advertising:ip:daily_rollout:v1','advertising:ip:limited_rollout:v1','advertising:ip:employee_access:v1','advertising:agent_webhook'):
  rows0=store.db('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload,updated_at','limit':1}) or []
  if not rows0:continue
  p=rows0[0]['payload']
  if p.get('chat_id')==-5533733230:
   if r['chat_id']!=-1004378639510 or member.get('status')!='administrator':raise RuntimeError('Address alignment requires verified migrated administrator')
   if key=='advertising:agent_webhook':
    if p.get('bot_id')!=me['id']:raise RuntimeError('Webhook bot identity mismatch')
   elif p.get('owner_id')!=r['registered_by_user_id']:raise RuntimeError('Address approval owner mismatch')
   desired_p=dict(p,chat_id=r['chat_id'])
   patched=store.db('PATCH','telegram_api_cache',params={'cache_key':'eq.'+key,'updated_at':'eq.'+rows0[0]['updated_at'],'select':'payload'},body={'payload':desired_p,'updated_at':datetime.now(timezone.utc).isoformat()},prefer='return=representation') or []
   if len(patched)!=1 or store.cache_get(key)!=desired_p:raise RuntimeError('Address approval CAS/readback failed')
   aligned.append(key)
 proof.update(address_only_aligned_keys=aligned)

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
