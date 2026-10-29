"""One exact owner-authorized reply; no marketplace reads or writes."""
import os,sys,hashlib
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,stamp
ROOT="china_agent:owner_conversion_reply177:2026-10-29:v1"
def main():
 c=Cache();p=c.get(ROOT+":approval")
 assert p and p['status']=='approved' and p['chat_id']==-1004342917488 and p['reply_to_message_id']==496 and p['bot_id']==8780468043
 assert datetime.now(timezone.utc)<datetime.fromisoformat(p['expires_at'])
 token=os.environ['CHINA_TELEGRAM_BOT_TOKEN']
 assert token.split(':')[0]=='8780468043'
 receipt=ROOT+":delivery"
 old=c.get(receipt)
 if old: return
 if not c.create(receipt,dict(status='sending',started_at=stamp(),text_sha256=hashlib.sha256(p['text'].encode()).hexdigest())):return
 try:
  r=requests.post('https://api.telegram.org/bot'+token+'/sendMessage',json=dict(chat_id=p['chat_id'],text=p['text'],reply_parameters=dict(message_id=p['reply_to_message_id'],allow_sending_without_reply=False)),timeout=45)
  if r.status_code!=200:raise RuntimeError('Telegram delivery failed')
  j=r.json()
  assert j.get('ok') and j['result']['chat']['id']==p['chat_id'] and type(j['result']['message_id']) is int
  c.put(receipt,dict(status='sent',message_id=j['result']['message_id'],chat_id=p['chat_id'],reply_to_message_id=p['reply_to_message_id'],text=p['text'],sent_at=stamp()))
 except Exception:
  c.put(receipt,dict(status='uncertain',at=stamp()))
  raise RuntimeError('Uncertain delivery; do not retry') from None
if __name__=='__main__':
 try:main();print('Owner-authorized reply workflow finished; receipt is private.')
 except Exception:print('Reply workflow failed; inspect private receipt.');sys.exit(1)
