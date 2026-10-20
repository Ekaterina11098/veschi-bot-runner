"""Edit only the approved existing China message74; preserve full original audit."""
import sys,json,re
sys.path.insert(0,'scripts')
from china_price_apply import IO,CHAT,BOT,day,now
from china_break_even import compact_report,compact_payload
KEY='china_agent:break_even_compact_edit:2026-10-20:74:v1'
def main():
 if day()!='2026-10-20':raise RuntimeError('Expired one-time edit')
 io=IO();old=io.get(KEY)
 if old:
  print(json.dumps(dict(status=old['status'],message_id=old.get('message_id'),wb_writes=0)))
  if old['status']!='edited':raise RuntimeError('Existing edit requires reconciliation')
  return
 cfg=io.db('business_agent_config?agent_id=eq.china&select=chat_id,bot_id,active')
 if cfg!=[dict(chat_id=CHAT,bot_id=BOT,active=True)] or io.tg('getMe',{}).get('id')!=BOT:raise RuntimeError('Wrong bot/chat')
 source=io.get('china_agent:break_even_preview:2026-10-20:39420564894')
 sent=io.get('china_agent:break_even_owner_delivery:2026-10-20:119:v1')
 if not source or source['status']!='verified' or not sent or sent['status']!='sent' or sent['message_id']!=74:raise RuntimeError('Original verified delivery missing')
 calc=next(t for t in source['trace'] if t['name']=='china_break_even')
 if calc['nm_id']!='1473243898' or calc['buyout']['sample_size']!=3 or abs(calc['buyout']['percent']-100/3)>.001:raise RuntimeError('Wrong calculation')
 if [s['seller_after_cny'] for s in calc['scenarios']]!=[166.4,207.6]:raise RuntimeError('Wrong approved prices')
 match=re.search(r'Текущая цена продавца: ([0-9,]+) ¥',source['answer'])
 if not match or match[1]!='146,40':raise RuntimeError('Current-price source differs')
 text=compact_report(calc['article'],calc['nm_id'],calc['buyout'],1,'146.4',calc['scenarios'])
 audit=dict(status='editing',chat_id=CHAT,message_id=74,old_answer=sent['answer'],old_receipt=sent['receipt'],answer=text,started_at=now().isoformat(),wb_writes=0,new_messages=0)
 if not io.create(KEY,audit):raise RuntimeError('Concurrent edit')
 try:
  receipt=io.tg('editMessageText',dict(chat_id=CHAT,message_id=74,text=text,**compact_payload(text,[(calc['nm_id'],calc['article'])])))
 except Exception:
  audit['status']='uncertain';io.put(KEY,audit);raise RuntimeError('Edit uncertain; no automatic retry')
 if receipt.get('message_id')!=74 or receipt.get('chat',{}).get('id')!=CHAT or receipt.get('text')!=text:raise RuntimeError('Edit receipt mismatch')
 audit.update(status='edited',receipt=receipt,edited_at=now().isoformat());io.put(KEY,audit)
 sent.update(current_answer=text,last_edit_receipt=receipt,last_edit_audit=KEY);io.put('china_agent:break_even_owner_delivery:2026-10-20:119:v1',sent)
 print(json.dumps(dict(status='edited',message_id=74,new_messages=0,wb_writes=0,answer=text),ensure_ascii=False))
if __name__=='__main__':main()
