"""Owner-requested completed-report keyboard update. No WB calls or new chat messages."""
from china_loss_execute import IO
from china_execution_notice import proven
def run():
 io=IO();K='china_agent:report_buttons:v1:existing11:delivery'
 prior=io.get(K)
 if prior:
  assert prior['status']=='edited_verified';return
 pid='daily-2026-11-11-owner-unified-final-drr-0'
 p=io.get('china_agent:loss_plan:v1:'+pid);e=io.get('china_agent:daily_ad_execution:v2:'+pid);items={i['id']:i for i in p['items']}
 assert p['report_message_ids']==[857,858]and len(e['items'])==21 and all(proven(items[s['id']],s)for s in e['items'])
 result=io.get('china_agent:daily_ad_result:v2:'+pid);assert result['status']=='sent'and result['message_id']==868
 assert io.tg('getMe',{})['id']==8780468043
 markup=dict(inline_keyboard=[[dict(text='Все действия выполнены · открыть итог',url='https://t.me/c/4342917488/868')]])
 rec=dict(status='editing',plan_id=pid,result_message_id=868,archive=io.get('china_agent:owner_budget_final:2026-11-11:v2:delivery'),receipts=[],wb_writes=0)
 assert io.create(K,rec)
 for mid in [857,858]:
  r=io.tg('editMessageReplyMarkup',dict(chat_id=-1004342917488,message_id=mid,reply_markup=markup))
  assert r['message_id']==mid and r['chat']['id']==-1004342917488 and r['from']['id']==8780468043 and r['reply_markup']==markup
  rec['receipts'].append(r);io.put(K,rec)
 rec['status']='edited_verified';io.put(K,rec)
 print('Report857858 keyboards edited and verified; no WB writes or new messages')
if __name__=='__main__':run()
