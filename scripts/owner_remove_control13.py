"""Delete only owner-rejected control pages; preserve recommendations1010. No WB."""
import json
from datetime import datetime,timezone
from china_advertising_state import AdvertisingIO
KEY='china_agent:owner_remove_control:2026-11-13:v1'
IDS=list(range(1011,1030))
def main():
 io=AdvertisingIO();root=io.get('china_agent:price_delivery:v2:2026-11-13:control')
 assert root['status']=='sent'and root['job_id']==322 and root['message_ids']==IDS
 assert (io.get('china_agent:price_delivery:v2:2026-11-13:morning')or{})['message_ids']==[1010]
 prior=io.get(KEY)
 if prior:
  assert prior['status']=='deleted';print('Already deleted; no Telegram repeat');return
 state=dict(status='deleting',chat_id=-1004342917488,message_ids=IDS,preserve_message_ids=[1010],owner_source='Codex13Nov:Удаляй.В10-30только краткий отчёт с рекомендациями',started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
 assert io.create(KEY,state)
 try:
  me=io.tg('getMe',{});assert me['id']==8780468043
  result=io.tg('deleteMessages',dict(chat_id=-1004342917488,message_ids=IDS));assert result is True
  state.update(status='deleted',telegram_result=result,completed_at=datetime.now(timezone.utc).isoformat());io.put(KEY,state)
  tomb=dict(status='deleted_by_owner',message_ids=IDS,preserve_message_ids=[1010],receipt_key=KEY)
  assert io.create('china_agent:price_delivery_removed:v1:2026-11-13:control',tomb)
  print(json.dumps(dict(status='deleted',message_ids=IDS,preserved=[1010],wb_writes=0)))
 except Exception:
  state['status']='uncertain';io.put(KEY,state);raise
if __name__=='__main__':main()
