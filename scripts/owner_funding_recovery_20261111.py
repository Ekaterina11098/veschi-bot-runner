"""Recover only a known preflight-only funding failure, with all fresh funding checks."""
import json
from datetime import datetime,timezone
from china_loss_execute import IO
from china_loss_control import PLAN,APPROVAL,digest
from china_daily_ad_actions import process_and_deliver
from china_execution_notice import proven
PID='daily-2026-11-11-owner-unified-final-drr-0'
def run():
 io=IO();p=io.get(PLAN+PID);a=io.get(APPROVAL+'294');key='china_agent:daily_ad_execution:v2:'+PID;e=io.get(key)
 assert p['plan_sha256']==digest(p['items'])=='271c5b6c1b5229287505bb9feeb2366d2924bf80e4522eadc69b95c593ee7ad4'
 io.validate_owner(a)
 audit='china_agent:owner_funding_recovery:2026-11-11:v1'
 if io.get(audit)is None:
  assert e['status']=='done'
  blocked=[x for x in e['items']if x['id']=='topup:40933588'];assert len(blocked)==1
  x=blocked[0];assert x['status']=='blocked'and x.get('reason')=='Funding current stock/COGS unavailable: 600-JessicaBag-blue (nm 1473244350, MSK free 0.0, WB 0)'and not any(k in x for k in ['request','response','submitted_at'])
  item=next(i for i in p['items']if i['id']==x['id']);ev=item['budget_evidence']
  assert ev['member_inputs']['1473244350']['stock_free']==0 and ev['member_inputs']['1473244350']['published_stock']==0
  assert 1473244350 in ev['unknown_nm_ids']and ev['coverage']>=.9 and ev['stress_after_ads_cny']>0
  assert io.create(audit,dict(status='preflight_only_resume',original_states=blocked,recorded_at=datetime.now(timezone.utc).isoformat(),execution_key=key,plan_sha256=p['plan_sha256']))
  e['items']=[s for s in e['items']if s['id']!=x['id']];e['status']='running';io.put(key,e)
 e=process_and_deliver(io,a,p);states={s['id']:s for s in e['items']};items={i['id']:i for i in p['items']}
 verified=[i for k,i in items.items()if proven(i,states[k])]
 missing=[dict(id=k,status=states[k]['status'],reason=states[k].get('reason'))for k in items if not proven(items[k],states[k])]
 funded=sum(i['amount_cny']for i in verified if i['kind']=='topup_campaign')
 if missing:text='Итог плана857/858: подтверждено WB '+str(len(verified))+' из21. Пополнено '+str(funded)+' CNY. Не выполнено: '+json.dumps(missing,ensure_ascii=False)
 else:
  text='Всё по подтверждённому плану857/858 выполнено и проверено чтением WB:21 из21действия. Пять добавлений, три изменения ставок, четыре исключения и завершение трёхРК. Шесть пополнений, всего4300CNY:40933588 +2500;40964981 +100;41055480 +300;41155909 +100;41270309 +250;41298169 +1050. Товар55 исключён. Повторных пополнений нет. РК41296363 оставлена без пополнения по вашему решению. Вечерний сбой10ноября разобран отдельно в сообщении866: старые3действия не выдаются за выполненные.'
 K=audit+':delivery'
 if io.get(K)is None:
  assert io.create(K,dict(status='sending',text=text,execution_key=key))
  try:
   r=io.tg('sendMessage',dict(chat_id=-1004342917488,text=text,reply_parameters=dict(message_id=859,allow_sending_without_reply=True)))
   assert r['chat']['id']==-1004342917488 and r['from']['id']==8780468043 and r.get('message_id')
   io.put(K,dict(status='sent',message_id=r['message_id'],chat_id=-1004342917488,text=text,execution_key=key,verified_count=len(verified),funded_cny=funded))
  except Exception:
   io.put(K,dict(status='uncertain',text=text,execution_key=key));raise
 print(json.dumps(dict(verified=len(verified),funded=funded,missing=missing),ensure_ascii=False))
if __name__=='__main__':run()
