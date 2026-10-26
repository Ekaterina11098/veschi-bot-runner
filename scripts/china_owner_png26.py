"""One exact owner-approved cached PNG; no marketplace access or regeneration."""
import os,json,base64,hashlib,io
from datetime import datetime,timezone
import requests
KEY='china_agent:approved_report_png:20261026:v4:delivery'
URL=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache'
H={'apikey':os.environ['SUPABASE_SECRET_KEY'],'Content-Type':'application/json'}
def get(k):
 r=requests.get(URL,params={'cache_key':'eq.'+k,'select':'payload'},headers=H,timeout=30);r.raise_for_status();return r.json()[0]['payload']
def save(p,claim=False):
 params={'cache_key':'eq.'+KEY}
 if claim:params['payload->>status']='eq.approved'
 r=requests.patch(URL,params=params,headers=H|{'Prefer':'return=representation'},json={'payload':p,'updated_at':datetime.now(timezone.utc).isoformat()},timeout=30);r.raise_for_status();return len(r.json())==1
def main():
 p=get(KEY)
 if p['status']!='approved':print('Existing delivery state; no resend');return
 assert datetime.fromisoformat(p['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)
 assert (p['owner_user_id'],p['chat_id'],p['bot_id'])==(5122667182,-1004342917488,8780468043)
 b=base64.b64decode(''.join(get(k)['b64'] for k in p['chunks']),validate=True)
 assert hashlib.sha256(b).hexdigest()==p['sha256']
 token=os.environ['CHINA_TELEGRAM_BOT_TOKEN'];tg='https://api.telegram.org/bot'+token+'/'
 me=requests.get(tg+'getMe',timeout=30).json()
 assert me.get('ok') and me['result']['id']==p['bot_id']
 p.update(status='sending',sending_at=datetime.now(timezone.utc).isoformat(),runner=os.environ.get('GITHUB_RUN_ID'))
 if not save(p,True):print('Delivery already claimed');return
 try:
  r=requests.post(tg+'sendPhoto',data={'chat_id':p['chat_id'],'caption':p['caption']},files={'photo':(p['file'],b,'image/png')},timeout=60)
  j=r.json()
  assert j.get('ok') and j['result']['chat']['id']==p['chat_id']
  p.update(status='sent',message_id=j['result']['message_id'],telegram_date=j['result']['date'],sent_at=datetime.now(timezone.utc).isoformat())
  assert save(p)
  print(json.dumps({'status':'sent','message_id':p['message_id'],'wb_writes':0}))
 except Exception:
  p['status']='uncertain';save(p)
  raise RuntimeError('Delivery result uncertain; do not resend') from None
if __name__=='__main__':main()
