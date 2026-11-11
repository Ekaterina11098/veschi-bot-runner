"""Exact owner-confirmed unified plan execution and truthful prior-evening audit. No broad queue drain."""
import copy,json,requests
from datetime import datetime,timezone
from china_loss_execute import IO
from china_loss_control import PLAN,APPROVAL,digest
from china_daily_ad_actions import process_and_deliver
from china_codex_routing import bound_execution,cloud_only
from conversion_watches import runtime,saved_network_guard
PID='daily-2026-11-11-owner-unified-final-drr-0'
def run():
 io=IO();p=io.get(PLAN+PID)
 assert p['report_message_ids']==[857,858]and len(p['items'])==21 and p['budget_total_cny']==4300
 assert p['plan_sha256']==digest(p['items'])=='271c5b6c1b5229287505bb9feeb2366d2924bf80e4522eadc69b95c593ee7ad4'
 assert not any(i.get('campaign_id')==41296363 and i['kind']=='topup_campaign'for i in p['items'])
 assert io.get('china_agent:budget_owner_policy:v1')['do_not_fund']['41296363']
 # Preserve evidence that the old evening plan had no execution before today's work.
 oldpid='daily-2026-11-10-midday-owner-approved-drr-0'
 audit='china_agent:owner_evening293_audit:2026-11-11:v1'
 if io.get(audit)is None:
  old=io.get(PLAN+oldpid);assert len(old['items'])==3
  value=dict(status='audited',old_plan_id=oldpid,old_execution=io.get('china_agent:daily_ad_execution:v2:'+oldpid),old_result=io.get('china_agent:daily_ad_result:v2:'+oldpid),items=old['items'],audited_at=datetime.now(timezone.utc).isoformat(),message_id=852,wb_writes=0)
  assert value['old_execution']is None and value['old_result']is None
  assert io.create(audit,value)
 w=runtime();assert cloud_only(w)
 for jobid,reply,inputmid in[(294,857,859),(295,858,861)]:
  job=io.db('business_agent_jobs?id=eq.'+str(jobid)+'&agent_id=eq.china&select=id,status,request_text,sender_id,chat_id,created_at,tool_trace,update_id')[0]
  assert job['sender_id']==5122667182 and job['chat_id']==-1004342917488 and job['request_text'].strip().casefold()=='сделай все'
  marker=next(t for t in job['tool_trace']if t['name']=='china_saved_question')
  assert marker['reply_message_id']==reply and marker['message_id']==inputmid and bound_execution(w,job)
  with saved_network_guard():outcome=w.question(jobid)
  print('Exact approval acknowledgement',jobid,outcome)
  a=io.get(APPROVAL+str(jobid))
  assert a and a['plan_id']==PID and a['plan_sha256']==p['plan_sha256']
 a=io.get(APPROVAL+'294')
 e=process_and_deliver(io,a,p)
 notice=io.get('china_agent:daily_ad_result:v2:'+PID)
 assert notice and notice['status']=='sent'and notice.get('message_id')
 # The second reply confirms the same immutable plan, never a second execution.
 duplicate=io.get(APPROVAL+'295')
 duplicate.update(status='completed',duplicate_of_job_id=294,result_status=e['status'],execution_key='china_agent:daily_ad_execution:v2:'+PID,result_message_id=notice['message_id'])
 io.put(APPROVAL+'295',duplicate)
 # Give the requested truthful evening result, without executing the replaced plan.
 K=audit+':delivery';prior=io.get(K)
 if prior is None:
  text='По вашему вечернему «сделай все» от10ноября к PNG851: те3действия не были выполнены — задание293 осталось без попытки обработки, квитанции WB отсутствуют. Подтверждение приёма не было результатом. Старый план заменён; автоматически его не запускаю. Сегодняшний общий план857/858 обрабатывается отдельно, его фактический результат — в сообщении'+str(notice['message_id'])+'.'
  assert io.create(K,dict(status='sending',text=text,chat_id=-1004342917488))
  try:
   receipt=io.tg('sendMessage',dict(chat_id=-1004342917488,text=text,reply_parameters=dict(message_id=852,allow_sending_without_reply=True)))
   assert receipt['message_id']and receipt['chat']['id']==-1004342917488
   io.put(K,dict(status='sent',text=text,chat_id=-1004342917488,message_id=receipt['message_id']))
   resolution=dict(status='answered_by_owner',job_id=293,chat_id=-1004342917488,message_id=receipt['message_id'],receipt_key=K,answer=text)
   key='china_agent:owner_dialog_resolution:v1:job:293'
   if io.get(key)is None:assert io.create(key,resolution)
   assert io.get(key)==resolution
  except Exception:
   io.put(K,dict(status='uncertain',text=text,chat_id=-1004342917488));raise
 print('Result delivery verified',notice['message_id'],'item states',json.dumps([{k:x.get(k)for k in['id','status','reason']}for x in e['items']],ensure_ascii=False))
if __name__=='__main__':run()
