"""Publish owner-approved two-button menu once; no marketplace calls."""
import json
from china_loss_execute import IO
ROOT='china_agent:main_menu:v1:'
CHAT=-1004342917488
BOT=8780468043
K=ROOT+'initial:2026-11-11'
def run():
 io=IO()
 assert io.tg('getMe',{})['id']==BOT
 assert (io.get(ROOT+'policy')or{}).get('enabled')is True
 # Use actual latest edited receipts; no obsolete original morning receipt.
 delivery=io.get('china_agent:report_buttons:v1:existing11:delivery')
 assert delivery['status']=='edited_verified'
 from china_main_menu_index import bind
 p=io.get('china_agent:loss_plan:v1:'+delivery['plan_id'])
 for family,mid in [('drr',857),('budgets',858)]:
  receipt=next(r for r in delivery['receipts'] if r['message_id']==mid)
  bind(io,dict(family=family),p,receipt)
 old=io.get(K)
 if old:
  assert old['status']=='sent' and old['receipt']['message_id']
  print(json.dumps(dict(status='already_sent',message_id=old['receipt']['message_id'])));return
 markup=dict(keyboard=[[dict(text='📊 Продажи')],[dict(text='📣 Реклама')]],resize_keyboard=True,is_persistent=True,one_time_keyboard=False,input_field_placeholder='Выберите раздел или напишите вопрос')
 assert io.create(K,dict(status='sending',wb_writes=0))
 receipt=io.tg('sendMessage',dict(chat_id=CHAT,text='Главное меню\nВыберите раздел:',reply_markup=markup))
 assert receipt['chat']['id']==CHAT and receipt['from']['id']==BOT and type(receipt['message_id'])is int
 io.put(K,dict(status='sent',receipt=receipt,message_id=receipt['message_id'],requested_reply_markup=markup,wb_writes=0))
 print(json.dumps(dict(status='sent',message_id=receipt['message_id'],wb_writes=0)))
if __name__=='__main__':run()
