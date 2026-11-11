"""Resume only five proven preflight failures; preserve all submitted/verified actions."""
import copy,json
from datetime import datetime,timezone
from china_loss_execute import IO
from china_loss_control import PLAN,APPROVAL,digest
from china_daily_ad_actions import process_and_deliver
from china_execution_notice import proven
PID='daily-2026-11-11-owner-unified-final-drr-0'
IDS={'40811856:add:1556488181','41325622:add:1535337771','41325622:add:1535337772','41325622:add:1535337773','41325622:add:1535337779'}
def run():
 io=IO();p=io.get(PLAN+PID);a=io.get(APPROVAL+'294');key='china_agent:daily_ad_execution:v2:'+PID;e=io.get(key)
 assert p['plan_sha256']==digest(p['items'])=='271c5b6c1b5229287505bb9feeb2366d2924bf80e4522eadc69b95c593ee7ad4'
 io.validate_owner(a)
 audit='china_agent:owner_additions_recovery:2026-11-11:v1'
 if io.get(audit)is None:
  blocked=[x for x in e['items']if x['id']in IDS]
  assert len(blocked)==5 and all(x['status']=='blocked'and x.get('reason')=='TypeError'and not any(k in x for k in ['request','response','submitted_at','bid_phase'])for x in blocked)
  assert io.create(audit,dict(status='preflight_only_resume',original_states=blocked,recorded_at=datetime.now(timezone.utc).isoformat(),execution_key=key,plan_sha256=p['plan_sha256']))
  e['items']=[x for x in e['items']if x['id']not in IDS];e['status']='running';io.put(key,e)
 e=process_and_deliver(io,a,p)
 states={x['id']:x for x in e['items']};items={x['id']:x for x in p['items']}
 verified=[items[k]for k,v in states.items()if proven(items[k],v)]
 added=[items[k]['article']for k in IDS if proven(items[k],states[k])]
 blocked=[(items[k],v)for k,v in states.items()if not proven(items[k],v)]
 funded=sum(i['amount_cny']for i in verified if i['kind']=='topup_campaign')
 text='Итог восстановления по PNG857/858: '+str(len(verified))+' из21действия подтверждены чтением WB. Добавлены: '+', '.join(added)+'. Всего пополнено '+str(funded)+' CNY, повторных пополнений нет.'
 if blocked:
  text+=' Не выполнено: '+'; '.join('РК'+str(i['campaign_id'])+' — '+v.get('reason','результат не подтверждён')for i,v in blocked)+'.'
 text+=' РК41296363 оставлена без пополнения по вашему поручению. Вечерний ответ — сообщение866.'
 K=audit+':delivery';prior=io.get(K)
 if prior is None:
  assert io.create(K,dict(status='sending',text=text,execution_key=key))
  try:
   r=io.tg('sendMessage',dict(chat_id=-1004342917488,text=text,reply_parameters=dict(message_id=859,allow_sending_without_reply=True)))
   assert r['chat']['id']==-1004342917488 and r['from']['id']==8780468043 and r.get('message_id')
   io.put(K,dict(status='sent',message_id=r['message_id'],chat_id=-1004342917488,text=text,execution_key=key,verified_count=len(verified),funded_cny=funded))
  except Exception:
   io.put(K,dict(status='uncertain',text=text,execution_key=key));raise
 print(json.dumps(dict(verified=len(verified),added=added,funded=funded,blocked=[dict(id=i['id'],status=s['status'],reason=s.get('reason'))for i,s in blocked]),ensure_ascii=False))
if __name__=='__main__':run()
