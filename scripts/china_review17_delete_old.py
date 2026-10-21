"""Owner requested deletion of exact obsolete recommendation messages."""
from china_price_apply import IO
import json
KEY='china_agent:review17_delete_old:2026-10-21:v1'
io=IO();old=io.get('china_agent:review17_owner_send:2026-10-21:v1')
if old['status']!='delivered' or [x['receipt']['message_id'] for x in old['parts']]!=[92,93]:raise RuntimeError('Old receipt scope mismatch')
p=io.get(KEY)
if p and p['status']=='deleted':print('already_deleted');raise SystemExit()
if p:raise RuntimeError('Deletion outcome requires review')
if io.tg('getMe',{})['id']!=8780468043:raise RuntimeError('Bot mismatch')
p=dict(status='deleting',chat_id=-1004342917488,original=old,results=[],wb_writes=0)
if not io.create(KEY,p):raise RuntimeError('Concurrent delete')
for mid in [92,93]:
 r=io.tg('deleteMessage',dict(chat_id=-1004342917488,message_id=mid))
 p['results'].append(dict(message_id=mid,deleted=r is True));io.put(KEY,p)
p['status']='deleted';io.put(KEY,p)
print(json.dumps(dict(status=p['status'],deleted=[92,93],wb_writes=0)))
