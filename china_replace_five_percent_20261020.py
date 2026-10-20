"""One-time owner-requested replacement of today's delivered report; no WB writes."""
import sys,json,copy
from datetime import datetime,timedelta,timezone
from urllib.parse import quote
sys.path.insert(0,'scripts')
from china_price_apply import IO,CHAT,BOT,now,day
import china_price_brief as brief
import china_buyer_price_forecast as buyer_module
import types
sys.modules['china_agent']=types.ModuleType('china_agent')
sys.modules['china_agent.buyer_price_forecast']=buyer_module
KEY='china_agent:report_replacement:2026-10-20:five_percent:59:v1'
class ReadOnlyIO(IO):
 def wb(self,path,method='GET',body=None):
  if method!='GET' or not path.startswith('/api/v2/list/goods/filter?'):raise RuntimeError('WB write forbidden')
  return super().wb(path,method,body)
 def tg(self,method,body):
  if method not in ('getMe','sendMessage','deleteMessage'):raise RuntimeError('Unexpected Telegram operation')
  if method!='getMe' and body.get('chat_id')!=CHAT:raise RuntimeError('Wrong chat')
  if method=='deleteMessage' and body.get('message_id')!=67:raise RuntimeError('Wrong previous message')
  return super().tg(method,body)
def main():
 if day()!='2026-10-20':raise RuntimeError('Expired one-time scope')
 io=ReadOnlyIO()
 old=io.get(KEY)
 if old:
  print(json.dumps(dict(status=old.get('status'),message_id=old.get('message_id'),wb_writes=0)))
  if old.get('status')!='done':raise RuntimeError('Existing attempt requires reconciliation; no blind repeats')
  return
 if io.tg('getMe',{}).get('id')!=BOT:raise RuntimeError('Wrong bot')
 cfg=io.db('business_agent_config?agent_id=eq.china&select=chat_id,bot_id,active')
 if len(cfg)!=1 or cfg[0]!=dict(chat_id=CHAT,bot_id=BOT,active=True):raise RuntimeError('Wrong China config')
 jobs=io.db('business_agent_jobs?id=eq.59&agent_id=eq.china&chat_id=eq.'+str(CHAT)+'&status=eq.done&select=*')
 if len(jobs)!=1:raise RuntimeError('Missing delivered report')
 job=jobs[0]
 expected='Снижение · Zont01-fio Продавец: 97,5 → 75 ¥\nПокупатель: 1 061 → 816 ₽'
 if job['answer']!=expected or job['request_text']!='/china_morning_pair_candidates':raise RuntimeError('Report changed')
 trace=job['tool_trace']
 buyer=next(t for t in trace if t.get('name')=='china_buyer_price_forecast')
 delivery=next(t for t in trace if t.get('name')=='china_report_delivery')
 if delivery.get('sent_parts')!=1:raise RuntimeError('Delivery scope changed')
 review=io.get('china_agent:daily_expected_candidates:2026-10-20')
 proposals=review.get('products',[])
 selected=[p for p in proposals if p.get('result',{}).get('status')=='rollback_review']
 if len(selected)!=1 or selected[0]['article']!='Zont01-fio':raise RuntimeError('Selection changed')
 live=io.prices(['1556488181'])['1556488181']
 if live.get('vendorCode')!='Zont01-fio':raise RuntimeError('Wrong live card')
 catalogue=dict(cabinet='token_3',rows=[live])
 text=brief.render_plain('ПЕРВОЕ ПОВЫШЕНИЕ +5%: 0','morning',review,datetime(2026,10,20).date(),catalogue,buyer)
 if text!='Снижение · Zont01-fio Продавец: 97,5 → 92,95 ¥\nПокупатель: 1 061 → 1 011 ₽':raise RuntimeError('Unexpected recalculation')
 payload=brief.plain_payload(text,catalogue)
 audit=dict(status='sending',report_date=day(),chat_id=CHAT,job_id=59,old_message_id=67,old_answer=job['answer'],old_trace=trace,answer=text,started_at=now().isoformat(),seller_readback=live,wb_writes=0,policy_step=0.05,buyer_assumption='unchanged_WB_discounts_and_conversion')
 if not io.create(KEY,audit):raise RuntimeError('Concurrent attempt')
 try:
  receipt=io.tg('sendMessage',dict(chat_id=CHAT,text=text,**payload))
 except Exception:
  audit['status']='uncertain';io.put(KEY,audit);raise RuntimeError('Send uncertain; do not retry')
 if receipt.get('chat',{}).get('id')!=CHAT or receipt.get('text')!=text:raise RuntimeError('Unexpected Telegram receipt')
 audit.update(status='sent',message_id=receipt['message_id'],receipt=receipt,sent_at=now().isoformat());io.put(KEY,audit)
 newtrace=copy.deepcopy(trace)
 for t in newtrace:
  if t.get('name')=='china_report_delivery':
   t.update(message_id=receipt['message_id'],telegram_message_ids=[receipt['message_id']],replacement_audit=KEY)
 newtrace.append(dict(name='china_price_step_replacement',step=0.05,old_message_id=67,message_id=receipt['message_id'],audit_key=KEY,wb_writes=0))
 result=io.db('business_agent_jobs?id=eq.59&answer=eq.'+quote(expected,safe=''),'PATCH',dict(answer=text,tool_trace=newtrace),'return=representation')
 if len(result)!=1 or result[0]['answer']!=text:raise RuntimeError('Job replacement readback failed')
 audit.update(status='linked');io.put(KEY,audit)
 deleted=io.tg('deleteMessage',dict(chat_id=CHAT,message_id=67))
 if deleted is not True:raise RuntimeError('Previous message deletion unconfirmed')
 audit.update(status='done',deleted_message_id=67,deletion_confirmed=True,completed_at=now().isoformat());io.put(KEY,audit)
 print(json.dumps(dict(status='done',message_id=receipt['message_id'],deleted_message_id=67,answer=text,entities=receipt.get('entities'),wb_writes=0),ensure_ascii=False))
if __name__=='__main__':main()
