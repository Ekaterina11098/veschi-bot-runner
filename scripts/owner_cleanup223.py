import os,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,stamp
K='china_agent:owner_cleanup223:2026-11-02:v1'
C=Cache()
IDS=(638,639,640)
def main():
 if datetime.now(timezone.utc).date().isoformat()!='2026-11-02':raise ValueError('Expired')
 b=os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()
 def tg(method,data):
  v=requests.post('https://api.telegram.org/bot'+b+'/'+method,json=data,timeout=35).json()
  if not v.get('ok'):raise RuntimeError('Telegram rejected '+method)
  return v['result']
 assert tg('getMe',{})['id']==8780468043
 for i,mid in enumerate(IDS):
  proof=C.get('china_agent:conversion_watch_delivery:v1:question:223:'+str(i)) or {}
  assert proof.get('status')=='sent' and proof.get('message_id')==mid and proof.get('chat_id')==-1004342917488
  key='china_agent:owner_cleanup223:2026-11-02:v1:'+str(mid)
  old=C.get(key)
  if old:continue
  if not C.create(key,dict(status='deleting',message_id=mid,chat_id=-1004342917488,owner_authorization='убери это все',created_at=stamp())):continue
  assert tg('deleteMessage',dict(chat_id=-1004342917488,message_id=mid)) is True
  C.put(key,dict(status='deleted',message_id=mid,chat_id=-1004342917488,deleted_at=stamp(),wb_writes=0))
 print({'status':'completed','deleted':IDS})
if __name__=='__main__':main()
