"""Automatic, receipt-journalled post-WB notices for every daily executor entry point."""
import copy
from datetime import datetime,timezone
from china_loss_control import CHAT,BOT
PREFIX='china_agent:daily_ad_result:v2:'
def proven(item,state):
 if state.get('status')!='verified':return False
 before=state.get('before');after=state.get('after')
 if not isinstance(before,dict) or not isinstance(after,dict) or before.get('id')!=item['campaign_id'] or after.get('id')!=item['campaign_id']:return False
 kind=item['kind']
 if before.get('settings')!=after.get('settings'):return False
 if kind=='archive_campaign':return after.get('status')==7 and before.get('nm_settings')==after.get('nm_settings')
 if kind=='pause_campaign':return after.get('status')==11 and before.get('nm_settings')==after.get('nm_settings')
 if before.get('status')!=after.get('status'):return False
 if kind=='topup_campaign':
  if sorted(before.get('nm_settings',[]),key=lambda n:n['nm_id'])!=sorted(after.get('nm_settings',[]),key=lambda n:n['nm_id']) or not isinstance(state.get('after_budget'),(int,float)):return False
  if state.get('already_done'):return state['after_budget']>=item['target_balance']
  return isinstance(state.get('before_budget'),(int,float)) and state['after_budget']>=state['before_budget']+item['amount_cny']-2
 expected=copy.deepcopy(before.get('nm_settings',[]))
 if kind=='ad_exclude_sku':expected=[x for x in expected if x['nm_id']!=item['nm_id']]
 elif kind=='ad_add_sku':
  old_ids={n['nm_id']for n in expected};new=after.get('nm_settings',[])
  added=[n for n in new if n['nm_id']==item['nm_id']]
  if item['nm_id']in old_ids:return bool(state.get('already_done'))and len(added)==1 and added[0]['bids_kopecks'].get(item['placement'])==item['target_minor']and sorted(expected,key=lambda x:x['nm_id'])==sorted(new,key=lambda x:x['nm_id'])
  return len(added)==1 and added[0].get('subject',{}).get('id')==item['subject_id']and added[0]['bids_kopecks'].get(item['placement'])==item['target_minor']and sorted(expected,key=lambda x:x['nm_id'])==sorted([n for n in new if n['nm_id']!=item['nm_id']],key=lambda x:x['nm_id'])
 elif kind=='ad_set_bid':
  found=False
  for n in expected:
   if n['nm_id']==item['nm_id']:n['bids_kopecks'][item['placement']]=item['target_minor'];found=True
  if not found:return False
 else:return False
 return sorted(expected,key=lambda x:x['nm_id'])==sorted(after.get('nm_settings',[]),key=lambda x:x['nm_id'])

def deliver_result(io,a,p,e):
 # A notice must be tied to an actual command, even for legacy callers/test adapters.
 if type(a.get('job_id')) is not int or type(a.get('input_message_id')) is not int:return None
 states=e.get('items',[]);items=p['items']
 if not states or len(states)!=len(items):return None
 byid={x['id']:x for x in items}
 if any(s.get('id') not in byid for s in states):return None
 ready=all(proven(byid[s['id']],s) for s in states)
 pending=any(s.get('status') in ['accepted','submitting','uncertain','running','preflight'] or s.get('status')=='verified' and not proven(byid[s['id']],s) for s in states)
 phase='verified' if ready else 'uncertain' if pending else 'partial' if any(proven(byid[s['id']],s) for s in states) else 'approved_pending_conditions' if any(s.get('status')=='approved_pending_conditions' for s in states) else 'blocked'
 key=PREFIX+p['plan_id']+(':uncertain' if phase=='uncertain' else '')
 old=io.get(key)
 # A partial/blocked notice must not suppress a later verified completion.
 if old and phase=='verified' and old.get('status')=='sent' and old.get('phase') in ('partial','blocked','approved_pending_conditions'):
  key+=':verified'
 if io.get(key):return None
 lines=['Результат команды:']
 for state in states:
  item=byid[state['id']];label=(item['article']+' · ' if item.get('article') else '')+'РК '+str(item['campaign_id'])
  if proven(item,state):
   if item['kind']=='ad_exclude_sku':out='исключён; проверено WB. Остальные товары и ставки сохранены.'
   elif item['kind']=='ad_set_bid':out='ставка '+format(item['old_minor']/100,'.2f')+' → '+format(item['target_minor']/100,'.2f')+' ¥; проверено WB.'
   elif item['kind']=='topup_campaign':out='пополнена на '+str(item['amount_cny'])+' CNY; проверено WB.'
   elif item['kind']=='ad_add_sku':out='добавлен в '+('поиск' if item['placement']=='search' else 'рекомендации')+' по '+format(item['target_minor']/100,'.2f')+' CNY; проверено WB.'
   else:out='действие подтверждено WB.'
   if state.get('already_done'):out='уже было выполнено; состояние проверено WB, повторной записи нет.'
  elif state.get('status')=='approved_pending_conditions':out='сумма '+str(item['amount_cny'])+' CNY согласована; пополнение не выполнено. '+state.get('reason','Сначала проверка условий.')
  elif state.get('status')=='blocked':out='не выполнено: '+state.get('reason','проверка условий не пройдена')
  else:out='результат пока не подтверждён WB; повторно действие не запускаю.'
  lines.append(label+': '+out)
 text='\n'.join(lines);now=datetime.now(timezone.utc).isoformat()
 record=dict(status='sending',phase=phase,text=text,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],execution_key=p.get('execution_key','china_agent:daily_ad_execution:v2:'+p['plan_id']),job_id=a['job_id'],chat_id=CHAT,bot_id=BOT,created_at=now)
 if not io.create(key,record):return None
 try:
  if a.get('result_message_id'):
   r=io.tg('editMessageText',dict(chat_id=CHAT,message_id=a['result_message_id'],text=text,reply_markup=dict(inline_keyboard=[])))
  else:
   r=io.tg('sendMessage',dict(chat_id=CHAT,text=text,reply_parameters=dict(message_id=a['input_message_id'],allow_sending_without_reply=True)))
  if r.get('chat',{}).get('id')!=CHAT or r.get('from',{}).get('id')!=BOT or not r.get('message_id'):raise ValueError('Telegram receipt identity')
  record.update(status='sent',message_id=r['message_id'],receipt=r,sent_at=datetime.now(timezone.utc).isoformat());io.put(key,record)
 except Exception:
  record.update(status='uncertain');io.put(key,record)
 return record

def deliver_registered(io,key,e):
 """A registered confirmed recovery completes by receipt save, without a monitor."""
 contract=e.get('completion_notice') if isinstance(e,dict) else None
 if not contract or e.get('status') not in ('verified','done','partial','attention'):return None
 auth=io.get(contract.get('authorization_key','')) or {}
 p=contract.get('plan') or {};a=contract.get('approval') or {}
 from china_loss_control import digest
 if (auth.get('status')!='approved' or auth.get('owner_id')!=5122667182 or auth.get('telegram_allowed')is not True
     or auth.get('chat_id')!=CHAT or auth.get('bot_id')!=BOT or auth.get('execution_key')!=key
     or auth.get('plan_sha256')!=digest(p.get('items',[])) or p.get('plan_sha256')!=auth.get('plan_sha256')
     or a.get('job_id')!=auth.get('job_id') or a.get('input_message_id')!=auth.get('input_message_id')):
  raise ValueError('Completion notice authorization mismatch')
 p=dict(p,execution_key=key)
 return deliver_result(io,a,p,e)
