import sys,json
sys.path.insert(0,'scripts')
from china_price_apply import IO,now
io=IO();key='china_agent:loss_report:2026-10-22:delete100:v1'
old=io.get(key)
if old:
 if old.get('status')=='deleted':print('already_deleted');raise SystemExit()
 raise RuntimeError('Pending deletion requires review')
audit=dict(status='deleting',chat_id=-1004342917488,message_id=100,created_at=now().isoformat(),owner_requested=True)
if io.tg('getMe',{}).get('id')!=8780468043:raise RuntimeError('Wrong bot')
source=io.get('china_agent:loss_report:2026-10-22:v1')
if source.get('message_id')!=100 or source.get('chat_id')!=-1004342917488:raise RuntimeError('Wrong receipt')
if not io.create(key,audit):raise RuntimeError('Concurrent delete')
r=io.tg('deleteMessage',dict(chat_id=-1004342917488,message_id=100))
if r is not True:raise RuntimeError('Deletion unconfirmed')
audit.update(status='deleted',result=True,completed_at=now().isoformat());io.put(key,audit)
source.update(deleted_at=audit['completed_at'],deletion_audit=key);io.put('china_agent:loss_report:2026-10-22:v1',source)
print(json.dumps(dict(status='deleted',message_id=100)))
