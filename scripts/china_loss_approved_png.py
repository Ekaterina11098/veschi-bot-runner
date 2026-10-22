import sys,base64,hashlib,json,requests
sys.path.insert(0,'scripts')
from china_price_apply import IO,now,day
io=IO();key='china_agent:loss_report:2026-10-22:approved_png:v2'
if day()!='2026-10-22':raise RuntimeError('Expired approved delivery')
old=io.get(key)
if old:
 if old.get('status')=='delivered':print('already_delivered');raise SystemExit()
 raise RuntimeError('Sending/uncertain needs receipt investigation')
p=io.get('china_agent:loss_approved_png:2026-10-22:v2')
if not p or p.get('status')!='approved':raise RuntimeError('Approval missing')
b=b''.join(base64.b64decode(x,validate=True) for x in p['chunks_b64'])
if len(b)!=p['byte_length'] or not b.startswith(b'\x89PNG\r\n\x1a\n'):raise RuntimeError('Invalid approved PNG')
if io.tg('getMe',{}).get('id')!=8780468043:raise RuntimeError('Wrong bot')
if io.tg('getChat',{'chat_id':-1004342917488}).get('id')!=-1004342917488:raise RuntimeError('Wrong group')
a=dict(status='sending',chat_id=-1004342917488,bot_id=8780468043,day=day(),sha256=hashlib.sha256(b).hexdigest(),cursor=0,receipts=[],created_at=now().isoformat(),wb_writes=0,owner_approved=True,supersedes_deleted_message=100)
if not io.create(key,a):raise RuntimeError('Concurrent send')
try:
 r=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data={'chat_id':'-1004342917488','caption':'Китай · убыточные позиции · 22.10.2026\nСогласованный предварительный расчёт за 22.09–21.10. Цены и реклама не менялись.'},files={'photo':('loss-report.png',b,'image/png')},timeout=60)
 j=r.json();receipt=j.get('result',{})
 if not r.ok or not j.get('ok') or receipt.get('chat',{}).get('id')!=-1004342917488 or not receipt.get('message_id'):raise RuntimeError('Photo receipt not confirmed')
 a.update(status='delivered',cursor=1,message_id=receipt['message_id'],receipts=[receipt],completed_at=now().isoformat());io.put(key,a)
 print(json.dumps(dict(status='delivered',message_id=receipt['message_id'],wb_writes=0)))
except Exception:
 a['status']='uncertain';io.put(key,a);raise
