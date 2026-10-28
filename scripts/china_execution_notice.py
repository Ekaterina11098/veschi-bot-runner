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
 if kind=='pause_campaign':return after.get('status')==11 and before.get('nm_settings')==after.get('nm_settings')
 if before.get('status')!=after.get('status'):return False
 if kind=='topup_campaign':
  if before.get('nm_settings')!=after.get('nm_settings') or not isinstance(state.get('after_budget'),(int,float)):return False
  if state.get('already_done'):return state['after_budget']>=item['target_balance']
  return isinstance(state.get('before_budget'),(int,float)) and state['after_budget']>=state['before_budget']+item['amount_cny']-2
 expected=copy.deepcopy(before.get('nm_settings',[]))
 if kind=='ad_exclude_sku':expected=[x for x in expected if x['nm_id']!=item['nm_id']]
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
 phase='verified' if ready else 'uncertain' if pending else 'partial' if any(proven(byid[s['id']],s) for s in states) else 'blocked'
 key=PREFIX+p['plan_id']+(':uncertain' if phase=='uncertain' else '')
 if io.get(key):return None
 lines=['Результат команды:']
 for state in states:
  item=byid[state['id']];label=item.get('article','')+' · РК '+str(item['campaign_id'])
  if proven(item,state):
   if item['kind']=='ad_exclude_sku':out='исключён; проверено WB. Остальные товары и ставки сохранены.'
   elif item['kind']=='ad_set_bid':out='ставка '+format(item['old_minor']/100,'.2f')+' → '+format(item['target_minor']/100,'.2f')+' ¥; проверено WB.'
   elif item['kind']=='topup_campaign':out='пополнение подтверждено чтением бюджета WB.'
   else:out='действие подтверждено WB.'
   if state.get('already_done'):out='уже было выполнено; состояние проверено WB, повторной записи нет.'
  elif state.get('status')=='blocked':out='не выполнено: '+state.get('reason','проверка условий не пройдена')
  else:out='результат пока не подтверждён WB; повторно действие не запускаю.'
  lines.append(label+': '+out)
 text='\n'.join(lines);now=datetime.now(timezone.utc).isoformat()
 record=dict(status='sending',phase=phase,text=text,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],execution_key='china_agent:daily_ad_execution:v2:'+p['plan_id'],job_id=a['job_id'],chat_id=CHAT,bot_id=BOT,created_at=now)
 if not io.create(key,record):return None
 try:
  r=io.tg('sendMessage',dict(chat_id=CHAT,text=text,reply_parameters=dict(message_id=a['input_message_id'],allow_sending_without_reply=True)))
  if r.get('chat',{}).get('id')!=CHAT or r.get('from',{}).get('id')!=BOT or not r.get('message_id'):raise ValueError('Telegram receipt identity')
  record.update(status='sent',message_id=r['message_id'],receipt=r,sent_at=datetime.now(timezone.utc).isoformat());io.put(key,record)
 except Exception:
  record.update(status='uncertain');io.put(key,record)
 return record

