"""Deliver only the exact owner's finished economics and ready proposal, once."""
from datetime import datetime,timezone
import json
ROOT='china_agent:owner_moscow_fur:2026-11-11:v1'
CHAT=-1004342917488
def main():
 from conversion_watches import runtime,saved_network_guard
 from china_codex_ad_review import bind
 from china_loss_control import PLAN,digest
 w=runtime();cfg=w.config()
 if cfg.get('chat_id')!=CHAT or cfg.get('bot_id')!=8780468043:raise PermissionError('Wrong owner work destination')
 r=w.get(ROOT+':selection')or{};jid='owner-moscow-economics-20261111-final'
 if r.get('status')!='reviewed'or r.get('job_id')!=jid:raise ValueError('Final current-input review not ready')
 fresh=w.get('china_agent:menu_current_inputs:v1:'+jid)or{}
 if not fresh.get('observed_at')or(datetime.now(timezone.utc)-datetime.fromisoformat(fresh['observed_at'])).total_seconds()>1800:raise ValueError('Final exact price/stock checks stale')
 link=w.get('china_agent:codex_ad_review:v1:'+jid)or{};plan=w.get(PLAN+link['plan_id'])if link.get('plan_id')else None
 if plan and (digest(plan['items'])!=plan['plan_sha256']or datetime.fromisoformat(plan['expires_at'])<=datetime.now(timezone.utc)):raise ValueError('Prepared proposal hash/expiry invalid')
 delivery=[]
 def once(label,text,qid):
  w.active_question_id=qid;identity='owner_moscow_final_20261111:'+label
  with saved_network_guard():status=w.send_once(identity,CHAT,text)
  key='china_agent:conversion_watch_delivery:v1:'+identity;receipt=w.get(key)or{}
  if status!='sent'or receipt.get('status')!='sent'or type(receipt.get('message_id'))is not int:raise ValueError('Final delivery not confirmed; no blind retry')
  delivery.append(dict(receipt_key=key,message_id=receipt['message_id']));return receipt['message_id']
 calc=w.get(ROOT+':calculation_resolved');rows=calc['rows'];profits=[r['profit_per_buyout_cny']for r in rows]
 text='Шубы с отправкой из Москвы пересчитаны по новой модели: собственный завершённый выкуп, при отсутствии — плановый. По этим шести шубам своей завершённой выборки пока нет; использован согласованный план '+str(round(rows[0]['buyout_scenario']*100))+'%. Доставка '+str(rows[0]['logistics_cny_per_dispatch'])+' ¥/отправку, реклама '+str(rows[0]['planned_ads_pct'])+'%. Расчётная прибыль '+f'{min(profits):.2f}–{max(profits):.2f}'+' ¥/выкуп, не фактическая прибыль. Подробности — в таблице.'
 calc_id='owner-moscow-fur-calculation-20261111-v2'
 once('economics_text',text,calc_id)
 once('economics_png','CHINA_TABLE_PNG:china_agent:table_png:v1:'+calc_id+':0',calc_id)
 mids=[once('proposal_text',r['answer'],jid)]
 artifact=w.get('china_agent:table_png:v1:'+jid)or{}
 for i in range(len(artifact.get('files',[]))):mids.append(once('proposal_png:'+str(i),'CHINA_TABLE_PNG:china_agent:table_png:v1:'+jid+':'+str(i),jid))
 if plan:bind(w,jid,mids,r['answer'])
 oldkey=PLAN+'dialog-menu-owner-moscow-economics-20261111';old=w.get(oldkey)
 if old and not old.get('report_message_ids'):w.save(oldkey,dict(old,status='revoked',reason='Superseded by final current-input review',replacement_plan_id=link.get('plan_id')))
 result=dict(status='sent',parts=delivery,plan_id=link.get('plan_id'),observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,monitor_created=False)
 w.save(ROOT+':delivery',result);print(json.dumps(result))
if __name__=='__main__':main()

