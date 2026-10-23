"""Deliver one approved immutable China PNG set; no WB access or execution."""
import os,sys,json,base64,hashlib
from urllib.parse import urlparse
import requests
sys.path.insert(0,'scripts')
from china_price_apply import IO
from china_loss_control import digest,PLAN,CHAT,BOT
from datetime import datetime,timezone
KEY='china_agent:approved_campaign_png_delivery:20261023:v1'
PID='ad-approved-20261023-three-png'
if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise ValueError('Public runner only')
original=requests.sessions.Session.request
def scoped(self,method,url,**kw):
 u=urlparse(url);db=urlparse(os.environ['SUPABASE_URL'])
 if u.scheme!='https' or not (u.hostname==db.hostname and u.path.startswith('/rest/v1/') or u.hostname=='api.telegram.org' and u.path.rsplit('/',1)[-1] in ('getMe','sendPhoto')):raise ValueError('Delivery-only network scope')
 return original(self,method,url,**kw)
requests.sessions.Session.request=scoped
io=IO();state=io.get(KEY);p=io.get(PLAN+PID)
assert state and p and state['plan_id']==PID and state['plan_sha256']==p['plan_sha256']==digest(p['items']) and len(p['items'])==39
if datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('Expired plan')
info=requests.get('https://api.telegram.org/bot'+io.bot+'/getMe',timeout=30).json()
assert info.get('ok') and info['result']['id']==BOT and state['chat_id']==CHAT
def bind(mid):
 binding=dict(plan_id=PID,plan_sha256=p['plan_sha256'],chat_id=CHAT)
 io.create('china_agent:ad_rule_message:'+str(mid),binding)
 assert io.get('china_agent:ad_rule_message:'+str(mid))==binding
 p['report_message_ids']=sorted(set(p.get('report_message_ids',[])+[mid]));io.put(PLAN+PID,p)
for idx,part in enumerate(state['parts']):
 if part['status']=='sent':bind(part['message_id']);continue
 if part['status'] in ('sending','uncertain'):raise RuntimeError('Uncertain send; investigate without retry')
 data=io.get(part['cache_key']);b=base64.b64decode(data['data'],validate=True)
 assert hashlib.sha256(b).hexdigest()==part['sha256']
 part['status']='sending';io.put(KEY,state)
 try:
  caption=f'Китай · рекомендации · {idx+1}/3. Один ответ «Сделай всё» на любой из этих трёх PNG подтвердит все 39 рекомендаций. До подтверждения рекламу и цены не меняем.'
  j=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data=dict(chat_id=CHAT,caption=caption),files={'photo':(f'China-actions-{idx+1}.png',b,'image/png')},timeout=45).json()
  if not j.get('ok') or j['result']['chat']['id']!=CHAT or j['result']['from']['id']!=BOT:raise ValueError('Delivery receipt missing')
  part.update(status='sent',message_id=j['result']['message_id'],receipt=j['result'],sent_at=datetime.now(timezone.utc).isoformat());io.put(KEY,state)
  bind(part['message_id'])
 except Exception:
  if part['status']!='sent':part['status']='uncertain';io.put(KEY,state)
  raise
state['status']='delivered';state['delivered_at']=datetime.now(timezone.utc).isoformat();io.put(KEY,state)
print(json.dumps(dict(status='delivered',parts=3,message_ids=[x['message_id'] for x in state['parts']],bound_plan=PID,items=len(p['items']),wb_writes=0),ensure_ascii=False))
