"""Deterministic current-member approval of one frozen report. No model or WB access."""
import re,json,hashlib
from datetime import datetime,timezone
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def is_command(text):return bool(re.fullmatch(r'(?i)\s*(?:агент[, :]+)?(?:сделай|делай)\s+(?:всё|все)[.!]?\s*',text or ''))
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

