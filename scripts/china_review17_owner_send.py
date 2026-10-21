"""Send only the owner-requested private recommendation text; no WB operations."""
from china_price_apply import IO
from datetime import datetime,timezone
import json
KEY='china_agent:review17_owner_send:2026-10-21:v1'
io=IO();p=io.get(KEY)
if p['status']=='delivered':print('already_delivered');raise SystemExit()
if p['status'] not in ['prepared','partial']:raise RuntimeError('Uncertain send needs reconciliation')
if p['chat_id']!=-1004342917488 or p['bot_id']!=8780468043:raise RuntimeError('Scope mismatch')
if io.tg('getMe',{})['id']!=p['bot_id']:raise RuntimeError('Bot mismatch')
for i,text in enumerate(p['texts']):
 old=next((x for x in p['parts'] if x['index']==i),None)
 if old:
  if old['status']=='sent':continue
  raise RuntimeError('Part outcome uncertain')
 part=dict(index=i,status='sending');p['parts'].append(part);p['status']='sending';io.put(KEY,p)
 try:
  r=io.tg('sendMessage',dict(chat_id=p['chat_id'],text=text,parse_mode='HTML',link_preview_options=dict(is_disabled=True)))
  if r['chat']['id']!=p['chat_id'] or not r.get('message_id'):raise RuntimeError('Receipt mismatch')
  part.update(status='sent',receipt=r);p['status']='partial';io.put(KEY,p)
 except Exception:
  part['status']='uncertain';p['status']='uncertain';io.put(KEY,p);raise
p.update(status='delivered',completed_at=datetime.now(timezone.utc).isoformat());io.put(KEY,p)
print(json.dumps(dict(status='delivered',message_ids=[x['receipt']['message_id'] for x in p['parts']],wb_writes=0)))
