"""Send the approved 119 calculation once; no WB credentials or calls."""
import sys,json
sys.path.insert(0,'scripts')
from china_price_apply import IO,CHAT,BOT,now,day
KEY='china_agent:break_even_owner_delivery:2026-10-20:119:v1'
SOURCE='china_agent:break_even_preview:2026-10-20:39420564894'
def main():
 if day()!='2026-10-20':raise RuntimeError('Expired one-time delivery')
 io=IO()
 existing=io.get(KEY)
 if existing:
  print(json.dumps(dict(status=existing['status'],message_id=existing.get('message_id'),wb_writes=0)))
  if existing['status']!='sent':raise RuntimeError('Existing send requires reconciliation, not replay')
  return
 cfg=io.db('business_agent_config?agent_id=eq.china&select=chat_id,bot_id,active')
 if cfg!=[dict(chat_id=CHAT,bot_id=BOT,active=True)] or io.tg('getMe',{}).get('id')!=BOT:raise RuntimeError('China routing unverified')
 source=io.get(SOURCE)
 if not source or source.get('status')!='verified' or source.get('wb_writes')!=0:raise RuntimeError('Verified calculation missing')
 calc=next(t for t in source['trace'] if t['name']=='china_break_even')
 if calc['nm_id']!='1473243898' or calc['buyout']['sample_size']!=3 or abs(calc['buyout']['percent']-100/3)>.001:raise RuntimeError('Wrong article/rate')
 prices=[x['seller_after_cny'] for x in calc['scenarios']]
 if prices!=[166.4,207.6]:raise RuntimeError('Calculation changed')
 text=source['answer']
 article='119-NoelBag-darkblack'
 if not text.startswith(article) or len(text)>3300:raise RuntimeError('Invalid approved answer')
 entity=dict(type='text_link',offset=0,length=len(article),url='https://www.wildberries.ru/catalog/1473243898/detail.aspx')
 audit=dict(status='sending',source_key=SOURCE,chat_id=CHAT,answer=text,started_at=now().isoformat(),wb_writes=0)
 if not io.create(KEY,audit):raise RuntimeError('Concurrent delivery')
 try:receipt=io.tg('sendMessage',dict(chat_id=CHAT,text=text,entities=[entity],link_preview_options=dict(is_disabled=True),reply_parameters=dict(message_id=72,allow_sending_without_reply=True)))
 except Exception:
  audit.update(status='uncertain');io.put(KEY,audit);raise RuntimeError('Delivery uncertain: no blind retry')
 if receipt.get('chat',{}).get('id')!=CHAT or receipt.get('text')!=text:
  audit.update(status='uncertain',receipt=receipt);io.put(KEY,audit);raise RuntimeError('Unexpected receipt')
 audit.update(status='sent',message_id=receipt['message_id'],receipt=receipt,sent_at=now().isoformat());io.put(KEY,audit)
 print(json.dumps(dict(status='sent',message_id=receipt['message_id'],sent_at=audit['sent_at'],wb_writes=0)))
if __name__=='__main__':main()
