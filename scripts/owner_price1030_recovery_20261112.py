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
  # Complete the omitted non-action direction status in the SAME report, never resend.
  from china_cloud_cost_control import Cache,stamp
  import json,requests
  cache=Cache();key='china_agent:owner_price1030_caption:2026-11-12:v1'
  old=cache.get(key)
  if old and old.get('status')!='edited':raise RuntimeError('Caption outcome requires review; no replay')
  if not old:
   root=cache.get('china_agent:price_delivery:v2:2026-11-12:morning-1030-owner-recovery')
   prepared=cache.get('china_agent:price_delivery:v2:2026-11-12:morning-1030-owner-recovery:prepared')
   assert root['status']=='sent' and root['message_ids']==[1001] and prepared['answer'].endswith('Снижение: нет данных')
   caption='Китай · цены · 12.11.2026. Повышение: 13 предложений. Снижение: нет данных. Новая цена покупателя — прогноз. Изменения только после подтверждения.'
   assert cache.create(key,dict(status='editing',message_id=1001,started_at=stamp()))
   import os
   response=w.original_http(requests.Session(),'POST','https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN']+'/editMessageCaption',json=dict(chat_id=-1004342917488,message_id=1001,caption=caption,reply_markup=prepared['reply_markup']),timeout=60)
   value=response.json()
   if not response.ok or value.get('ok')is not True:raise RuntimeError('Caption edit unverified')
   assert value['result']['message_id']==1001
   cache.put(key,dict(status='edited',message_id=1001,caption=caption,keyboard_preserved=True,edited_at=stamp()))
  print({k:w.audit.get(k) for k in ('status','job_id','sent_parts','telegram_message_ids','wb_writes')})
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
if __name__=='__main__':main()

# Caption-only completion after offline status rendering checks passed.
