"""Dedicated recovery driver preparation. No activation, insertion or scheduling.
Default exits before credentials/imports. Existing approved rows only.
"""
import os

PREPARED_SCOPES = {(39410834,1007948808): '57-NoelBag-burgundy',
 (40223314,1123677454): '685-CelineaBag-black', (39410834,320248210): '141-PamelaBag-brown'}

def exact_scope(action):
 spec=action['specification'];pair=(spec.get('campaign_id'),spec.get('nm_id'))
 if any(type(v) is not int for v in pair) or pair not in PREPARED_SCOPES or spec.get('cabinet')!='token_2':
  raise PermissionError('Exact prepared pair and cabinet required')
 return pair


def notify_recovery_incident(port,action,send,now):
 """One durable incident notice to the owner-registered advertising chat.
 Lost Telegram response is uncertain, never replayed. No DB intent => no send.
 """
 import copy
 cid,nm=exact_scope(action)
 state=port.load(action['id'])
 if not state:raise RuntimeError('Durable incident state missing')
 if state.get('incident_notice'):return state['incident_notice']
 value=copy.deepcopy(state);value['revision']+=1
 value['incident_notice']=dict(status='intent',at=now.isoformat(),recipient_chat_id=action['chat_id'])
 if not port.cas(action['id'],state['revision'],value) or port.load(action['id'])!=value:raise RuntimeError('Notice intent not durable')
 if not port.fenced(action['id']):raise PermissionError('Notice lease lost')
 try:
  message=send(action['chat_id'],f'Нужно ручное восстановление: {PREPARED_SCOPES[(cid,nm)]} / nm{nm} / CPM{cid}. '
   'Автоматический возврат не подтверждён; причина: '+str(value.get('incident') or value.get('last_read_error') or value.get('phase'))+
   '. Ответственный — владелец. Проверьте фактический состав и ставку перед действием. Повторную запись вслепую не выполняйте.')
  if type(message) is not int or message<=0:raise RuntimeError('Telegram confirmation missing')
  result=dict(status='confirmed',message_id=message,at=now.isoformat(),recipient_chat_id=action['chat_id'])
 except Exception as exc:result=dict(status='uncertain',error_type=type(exc).__name__,at=now.isoformat(),recipient_chat_id=action['chat_id'])
 final=copy.deepcopy(value);final['revision']+=1;final['incident_notice']=result
 if not port.cas(action['id'],value['revision'],final) or port.load(action['id'])!=final:raise RuntimeError('Notice outcome uncertain; no resend')
 return result

def resume_existing(store,actions,now,*,enabled=False,port_factory=None,notify=None):
 if not enabled:return dict(enabled=False,wb_calls=0,rows_created=0)
 from datetime import datetime,timedelta
 from uuid import uuid4
 if os.environ.get('ADVERTISING_EXECUTION_ENABLED')!='true':raise PermissionError('WB execution disabled')
 registration=store.registration()
 rows=store.db('GET','advertising_agent_watches',params={'status':'in.(active,completed)',
  'policy->>mode':'eq.sku_membership_recovery','or':'(and(campaign_id.eq.39410834,nm_id.eq.1007948808),and(campaign_id.eq.40223314,nm_id.eq.1123677454),and(campaign_id.eq.39410834,nm_id.eq.320248210))',
  'next_check_at':'lte.'+now.isoformat(),'order':'next_check_at.asc','limit':10}) or []
 results=[]
 selected=actions.due_sku_membership_recoveries(rows,now)
 selected += [w for w in rows if w.get('status')=='completed' and (w.get('state') or {}).get('notification_pending')
  and (w.get('campaign_id'),w.get('nm_id')) in PREPARED_SCOPES
  and (w.get('policy') or {}).get('mode')=='sku_membership_recovery']
 for watch in selected:
  policy=watch['policy'];aid=policy.get('action_id');jid=policy.get('executor_job_id')
  if not aid or not jid:raise PermissionError('Separately reserved existing action/job/watch required')
  if watch['chat_id']!=registration['chat_id'] or watch['sender_id']!=registration['registered_by_user_id']:
   raise PermissionError('Owner registration changed')
  approved=store.db('GET','advertising_agent_actions',params={'id':'eq.'+aid,'status':'eq.running','limit':1}) or []
  if len(approved)!=1:raise PermissionError('Exact running action missing')
  action=approved[0];spec=action['specification']
  cid,nm=exact_scope(action)
  if (watch.get('campaign_id'),watch.get('nm_id'))!=(cid,nm):raise PermissionError('Watch/action pair mismatch')
  conflicts=store.db('GET','advertising_agent_watches',params={'status':'eq.active',
   'policy->>mode':'eq.sku_membership_recovery','campaign_id':'eq.'+str(cid),'select':'id','limit':2}) or []
  if len(conflicts)!=1 or conflicts[0]['id']!=watch['id']:raise PermissionError('Campaign reservation missing or conflicting')
  if (action['job_id']!=jid or action['chat_id']!=watch['chat_id'] or action['sender_id']!=watch['sender_id']
   or action.get('approved_by')!=registration['registered_by_user_id']
   or action['digest']!=actions.fingerprint(spec) or policy.get('approved_digest')!=action['digest']
   or spec.get('execution_authorized') is not True or spec.get('restore_authorized') is not True
   or policy.get('backup_operator_id')!=registration['registered_by_user_id']):
   raise PermissionError('Exact scope and both authorities required')
  jobs=store.db('GET','advertising_agent_jobs',params={'id':'eq.'+str(jid),'limit':1}) or []
  if len(jobs)!=1:raise RuntimeError('Reserved executor job unavailable')
  old=jobs[0]
  if old.get('request_text')!='/_sku57_reserved_recovery '+aid:raise PermissionError('Not a reserved recovery job')
  if old.get('status')=='running':
   if not old.get('lease_until') or datetime.fromisoformat(old['lease_until'])>now:continue
   params={'id':'eq.'+str(jid),'status':'eq.running','lease_token':'eq.'+str(old['lease_token']),'lease_until':'lte.'+now.isoformat()}
  elif old.get('status')=='done':params={'id':'eq.'+str(jid),'status':'eq.done'}
  else:raise PermissionError('Reserved job state is not reusable')
  lease=str(uuid4())
  changed=store.db('PATCH','advertising_agent_jobs',params=params,body={'status':'running',
   'lease_token':lease,'lease_until':(now+timedelta(minutes=5)).isoformat()},prefer='return=representation') or []
  if len(changed)!=1:continue
  job=changed[0]
  try:
   port=(port_factory or actions.SkuMembershipActionPort)(action,job,watch,live_enabled=True)
   updated=actions.sku_membership_watch_step(action,watch,port,now,enabled=True)
   results.append(dict(watch_id=watch['id'],state=updated['state']))
   if updated['state'].get('notification_pending') and notify:
    # Notification service must journal pending before send, preserve unknown and deduplicate.
    outcome=notify_recovery_incident(port,action,notify,now)
    updated['state'].update(notification_pending=False,incident_notice=outcome)
    port.save_watch(updated)
  finally:
   store.db('PATCH','advertising_agent_jobs',params={'id':'eq.'+str(jid),'status':'eq.running','lease_token':'eq.'+lease},
    body={'status':'done','lease_until':None})
 return dict(enabled=True,results=results,rows_created=0)

if __name__=='__main__':
 # Runtime cannot be activated by toggling only a workflow input or passing a date.
 # No credential-bearing invocation is shipped by this preparation.
 print('{"enabled":false,"wb_calls":0,"rows_created":0,"reason":"stage_one_preparation"}')
