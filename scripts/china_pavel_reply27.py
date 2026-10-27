"""One owner-authorized reply to Pavel321. No marketplace transport."""
import os,hashlib,json
from datetime import datetime,timezone
from china_price_apply import IO
KEY='china_agent:codex_pavel_reply:2026-10-27:321:v1'
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 io=IO();p=io.get(KEY)
 if not p or p.get('status')!='prepared' or p.get('chat_id')!=-1004342917488 or p.get('bot_id')!=8780468043 or p.get('reply_message_id')!=321 or not 1<=len(p.get('text',''))<=4000:raise ValueError('Reviewed reply missing')
 digest=hashlib.sha256(p['text'].encode()).hexdigest();k=KEY+':execution'
 if io.get(k):print('Existing attempt; never resend blindly');return
 identity=io.tg('getMe',{})
 if identity.get('id')!=8780468043:raise ValueError('Wrong bot')
 e=dict(status='sending',prepared_key=KEY,text_sha256=digest,chat_id=p['chat_id'],reply_message_id=321,started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
 if not io.create(k,e):raise ValueError('Concurrent attempt')
 try:
  receipt=io.tg('sendMessage',dict(chat_id=p['chat_id'],text=p['text'],reply_parameters=dict(message_id=321,allow_sending_without_reply=False),link_preview_options=dict(is_disabled=True)))
  if receipt.get('chat',{}).get('id')!=p['chat_id'] or receipt.get('from',{}).get('id')!=8780468043 or receipt.get('reply_to_message',{}).get('message_id')!=321:raise ValueError('Receipt identity mismatch')
  e.update(status='sent',message_id=receipt['message_id'],telegram_date=receipt['date'],receipt=receipt,completed_at=datetime.now(timezone.utc).isoformat())
  io.put(k,e);print(json.dumps(dict(status='sent',message_id=receipt['message_id'],wb_writes=0)))
 except Exception as error:
  e.update(status='uncertain',error=type(error).__name__);io.put(k,e);raise RuntimeError('Reply outcome uncertain; no retry') from None
if __name__=='__main__':run()
