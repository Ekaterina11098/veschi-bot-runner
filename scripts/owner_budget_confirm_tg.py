import os,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,stamp
K='china_agent:owner_budget_confirm_tg:2026-11-02:v1'
C=Cache()
TEXT='Бюджеты уже пополнили сегодня в 16:12–16:13 МСК на 2 700 CNY по четырём рекламным кампаниям. Зачисление подтверждено WB. В том числе РК 40933588 пополнена на 1 650 CNY. Повторное пополнение не выполнялось.'
def main():
 if datetime.now(timezone.utc).date().isoformat()!='2026-11-02':raise ValueError('Expired')
 r=C.get('china_agent:owner_budget_partial:2026-11-02:v1:execution')or{}
 assert r.get('status')=='verified' and r.get('total_verified_cny')==2700
 assert {x['campaign_id']:x['amount_cny']for x in r['items']if x['status']=='verified'}=={40933588:1650,41055480:350,41298169:550,41332083:150}
 old=C.get(K)
 if old:
  print({'status':old.get('status'),'message_id':old.get('message_id')});return
 b=os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()
 def tg(method,data):
  v=requests.post('https://api.telegram.org/bot'+b+'/'+method,json=data,timeout=35).json()
  if not v.get('ok'):raise RuntimeError('Telegram rejected '+method)
  return v['result']
 assert tg('getMe',{})['id']==8780468043
 p=dict(status='submitting',chat_id=-1004342917488,reply_to_message_id=631,text=TEXT,created_at=stamp(),owner_authorization='Codex: да, отправь в тг',wb_writes=0)
 if not C.create(K,p):return
 try:r=tg('sendMessage',dict(chat_id=-1004342917488,text=TEXT,reply_parameters=dict(message_id=631,allow_sending_without_reply=False)))
 except Exception:
  C.put(K,p|dict(status='uncertain',error='Telegram transport or rejection; no automatic retry'));raise
 assert r['chat']['id']==-1004342917488
 C.put(K,p|dict(status='sent',message_id=r['message_id'],sent_at=stamp()))
 print({'status':'sent','message_id':r['message_id']})
if __name__=='__main__':main()
