"""Deliver one exact approved daily loss PNG; no WB credentials or writes."""
import os,sys,json,base64,hashlib,requests
from urllib.parse import urlparse
from datetime import datetime,timezone
sys.path.insert(0,'scripts')
from china_price_apply import IO
CHAT=-1004342917488;BOT=8780468043;KEY='china_agent:loss_report:2026-10-23:v2'
if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise ValueError('Public runner only')
original=requests.sessions.Session.request
def scoped(self,method,url,**kwargs):
 u=urlparse(url);db=urlparse(os.environ['SUPABASE_URL'])
 if u.scheme!='https' or not (u.hostname==db.hostname and u.path.startswith('/rest/v1/') or u.hostname=='api.telegram.org' and u.path.rsplit('/',1)[-1] in ['getMe','sendPhoto']):raise ValueError('Delivery-only scope')
 return original(self,method,url,**kwargs)
requests.sessions.Session.request=scoped
io=IO();state=io.get(KEY)
assert state and state['owner_approved'] and state['chat_id']==CHAT and state['bot_id']==BOT
if state['status']=='delivered':print('already_delivered');sys.exit()
pair=io.get('china_agent:advertising_delivery:2026-10-23:v1')
assert pair and pair['status']=='delivered' and len(pair['parts'])==2 and all(p['status']=='sent' and p['message_id'] for p in pair['parts'])
me=requests.get('https://api.telegram.org/bot'+io.bot+'/getMe',timeout=30).json()
assert me.get('ok') and me['result']['id']==BOT
for idx,part in enumerate(state['parts']):
 if part['status']=='sent':continue
 if part['status'] in ['sending','uncertain']:raise ValueError('Investigate uncertain send, no blind replay')
 b=base64.b64decode(state['files'][idx]['data'],validate=True);assert hashlib.sha256(b).hexdigest()==part['sha256']
 part['status']='sending';state['status']='sending';io.put(KEY,state)
 try:
  r=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data=dict(chat_id=CHAT,caption='Китай · требует внимания · 23.10. Две позиции: подтверждённые сигналы и конкретные рекомендации. Новые изменения не применены.'),files={'photo':('China-attention-2026-10-23.png',b,'image/png')},timeout=45).json()
  assert r.get('ok') and r['result']['chat']['id']==CHAT and r['result']['from']['id']==BOT
  part.update(status='sent',message_id=r['result']['message_id'],receipt=r['result'],sent_at=datetime.now(timezone.utc).isoformat());io.put(KEY,state)
 except Exception:
  part['status']='uncertain';state['status']='uncertain';io.put(KEY,state);raise
state['status']='delivered';state['delivered_at']=datetime.now(timezone.utc).isoformat();io.put(KEY,state)
print(json.dumps(dict(status='delivered',message_ids=[p['message_id'] for p in state['parts']],wb_writes=0)))
