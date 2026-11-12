"""Owner12Nov: recover only the missed1030 compact price candidates, zero model/WB writes."""
from datetime import date
from china_agent.morning_pair import PairWorker

def main():
 w=PairWorker('candidates')
 if w.day!=date(2026,11,12):raise RuntimeError('Dated owner recovery expired')
 w.manual=True
 w.command='/china_morning_pair_candidates_1030_owner_recovery'
 w.update_id=-9300000000-(w.day-date(2020,1,1)).days
 w.delivery_mode='morning-1030-owner-recovery'
 try:
  w.run()
  w.save('china_agent:owner_price1030_recovery:2026-11-12:v1',dict(w.audit,model_calls=0,grants_action_permission=False))
  if w.audit.get('status') not in ('delivered','already_delivered'):raise RuntimeError('Compact report not delivered')
  print({k:w.audit.get(k) for k in ('status','job_id','sent_parts','telegram_message_ids','wb_writes')})
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
if __name__=='__main__':main()
