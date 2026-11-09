"""Deterministic current-member approval of one frozen report. No model or WB access."""
import re,json,hashlib
from datetime import datetime,timezone
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def is_command(text):
 if not isinstance(text,str):return False
 text=re.sub(r'@VESCHI_OOO_bot\b','',text,flags=re.I).strip()
 return bool(re.fullmatch(r'(?i)\s*(?:агент[, :]+)?(?:сделай|делай)\s+(?:всё|все)[.!]?\s*',text))

def bind_delivery(db,root,publication_key,chat,bot):
 """Bind frozen report actions only to independently stored sent photo receipts."""
 publication=db.get(publication_key)or{}
 plan=publication.get('manifest')or{}
 if publication.get('status')!='prepared'or publication.get('chat_id')!=chat or publication.get('manifest_sha256')!=digest(plan):raise PermissionError('Frozen publication manifest required')
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',publication.get('plan_id','')):raise PermissionError('Invalid plan identity')
 if plan.get('cabinet')!='token_1'or plan.get('currency')!='KGS':raise PermissionError('Publication scope mismatch')
 expires=publication['expires_at']
 if datetime.now(timezone.utc)>=datetime.fromisoformat(expires):raise PermissionError('Publication expired')
 receipts=publication.get('receipt_keys')or[]
 if not 1<=len(receipts)<=2:raise PermissionError('Exact photo receipt keys required')
 verified=[]
 for key in receipts:
  if not key.startswith('ooo_agent:')or key.startswith('ooo_agent:sol_dialog:'):raise PermissionError('Independent delivery receipt required')
  receipt=db.get(key)or{}
  if receipt.get('status')not in('sent','verified')or receipt.get('chat_id')!=chat or type(receipt.get('message_id'))is not int:raise PermissionError('Actual photo delivery unverified')
  if receipt.get('sha256')not in publication.get('artifact_sha256',[]):raise PermissionError('Receipt artifact differs from frozen report')
  verified.append((key,receipt))
 for key,receipt in verified:
  value={'status':'delivered_verified','chat_id':chat,'bot_id':bot,'plan_id':publication['plan_id'],'manifest':plan,'manifest_sha256':digest(plan),'expires_at':expires,'publication_key':publication_key,'receipt_key':key}
  binding_key=root+'report_binding:'+str(chat)+':'+str(receipt['message_id'])
  old=db.get(binding_key)
  if old and old!=value:raise PermissionError('Photo binding is immutable')
  if not old:db.once(binding_key,value)
 return len(receipts)
def approve(db,message,root,chat,bot,now=None,membership=None):
 now=now or datetime.now(timezone.utc)
 if not is_command(message.get('text')):return None
 policy=db.get(root+'report_execution_policy')or{}
 if policy.get('enabled')is not True:return {'status':'disabled','answer':'Исполнитель отчётов пока не включён.'}
 member=membership or {}
 if member.get('status')not in('member','administrator','creator')and not(member.get('status')=='restricted'and member.get('is_member')is True):return {'status':'rejected','answer':'Команду может согласовать текущий участник этой группы.'}
 if member.get('user',{}).get('id')!=message.get('from',{}).get('id'):raise PermissionError('Verified membership identity mismatch')
 if message.get('chat',{}).get('id')!=chat or message.get('from',{}).get('is_bot'):raise PermissionError('Command scope mismatch')
 reply=message.get('reply_to_message')or{}
 if reply.get('from',{}).get('id')!=bot:return {'status':'needs_report_reply','answer':'Ответьте «Сделай всё» непосредственно на PNG отчёта — так команда будет привязана к его действиям.'}
 report=db.get(root+'report_binding:'+str(chat)+':'+str(reply.get('message_id')))or{}
 plan=report.get('manifest')or{}
 if report.get('status')!='delivered_verified' or report.get('chat_id')!=chat or report.get('manifest_sha256')!=digest(plan):return {'status':'unbound','answer':'Для этого сообщения нет проверенного списка действий. Изменения не запущены.'}
 if now>=datetime.fromisoformat(report['expires_at']):return {'status':'expired','answer':'Отчёт устарел. Сначала нужна свежая проверка, изменения не запущены.'}
 if plan.get('cabinet')!='token_1'or plan.get('currency')!='KGS'or not(plan.get('actions')or plan.get('topups')):raise PermissionError('Invalid report scope')
 execution=db.get(report.get('execution_key',''))if report.get('execution_key')else None
 if execution:
  answer='Этот пакет уже выполнен и проверен в WB.'if execution.get('status')=='verified'else'У этого пакета уже есть журнал исполнения. Повторные изменения не запускаю; результат сообщит исполнитель.'
  return {'status':'existing_execution','answer':answer}
 key=root+'approved_report:'+report['plan_id']
 existing=db.get(key)
 if existing:return {'status':'existing','answer':'Эта команда уже зарегистрирована. Повторное исполнение не запускаю.','approval_key':key}
 value={'status':'approved_pending_execution','manifest':plan,'manifest_sha256':digest(plan),'plan_id':report['plan_id'],'chat_id':chat,'report_message_id':reply['message_id'],'approver_sender_id':message['from']['id'],'approval_message_id':message['message_id'],'approved_at':now.isoformat(),'expires_at':report['expires_at']}
 db.once(key,value)
 return {'status':'approved_pending_execution','answer':'Согласование отчёта сохранено. Завершение подтвержу только после исполнения и контрольной сверки WB.','approval_key':key}

