"""Deliver one explicitly approved private PNG, then delete the superseded answer."""
import os,json,base64,hashlib,io
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
from PIL import Image
from conversion_watches import runtime
KEY='china_agent:approved_answer_replace:v1:88:profit_forecast'
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
 w=runtime();p=w.get(KEY)
 if not p or p.get('chat_id')!=-1004342917488 or p.get('bot_id')!=8780468043 or p.get('old_message_id')!=171:raise SystemExit('Approval scope mismatch')
 token=os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()
 def tg(method,**kwargs):
  response=requests.post('https://api.telegram.org/bot'+token+'/'+method,timeout=45,**kwargs)
  return response.json()
 me=tg('getMe')
 if not me.get('ok') or me['result'].get('id')!=p['bot_id']:raise SystemExit('Bot identity mismatch')
 chat=tg('getChat',json={'chat_id':p['chat_id']})
 if not chat.get('ok') or chat['result'].get('id')!=p['chat_id']:raise SystemExit('Chat identity mismatch')
 member=tg('getChatMember',json={'chat_id':p['chat_id'],'user_id':p['bot_id']})
 if not member.get('ok') or member['result'].get('status') not in ('administrator','creator'):raise SystemExit('Bot delete permission not verified')
 if p.get('delivery_status') in ('sending','uncertain'):raise SystemExit('Uncertain send: investigate before retry')
 if p.get('delivery_status')!='sent':
  chunks=[w.get(KEY+':chunk:'+str(i)) for i in range(p['chunks'])]
  if any(c is None or c.get('index')!=i or c.get('sha256')!=p['sha256'] for i,c in enumerate(chunks)):raise SystemExit('Frozen chunks invalid')
  blob=base64.b64decode(''.join(c['data'] for c in chunks),validate=True)
  if len(blob)!=p['bytes'] or hashlib.sha256(blob).hexdigest()!=p['sha256']:raise SystemExit('Frozen PNG hash mismatch')
  picture=Image.open(io.BytesIO(blob));picture.verify()
  if picture.format!='PNG':raise SystemExit('Not PNG')
  original=w.get('china_agent:conversion_watch_delivery:v1:question:88:0')
  if not original or original.get('message_id')!=171 or original.get('chat_id')!=p['chat_id']:raise SystemExit('Old report identity not verified')
  p.update(delivery_status='sending',sending_at=stamp(),original_answer=original['text'],reply_message_id=170)
  claimed=w.db('PATCH','telegram_api_cache',params={'cache_key':'eq.'+KEY,'payload->>delivery_status':'eq.ready'},body={'payload':p,'updated_at':stamp()},prefer='return=representation')
  if not claimed:raise SystemExit('Delivery claim lost')
  try:result=tg('sendPhoto',data={'chat_id':p['chat_id'],'caption':p['caption'],'reply_parameters':json.dumps({'message_id':170})},files={'photo':('china-profit-forecast.png',blob,'image/png')})
  except Exception:
   p.update(delivery_status='uncertain',error='Telegram transport result unknown');w.save(KEY,p);raise SystemExit('Transport uncertain, no blind retry')
  message=result.get('result') or {}
  if not result.get('ok'):
   p.update(delivery_status='rejected',error_code=result.get('error_code'));w.save(KEY,p);raise SystemExit('Photo rejected')
  if message.get('chat',{}).get('id')!=p['chat_id'] or type(message.get('message_id')) is not int:
   p.update(delivery_status='uncertain');w.save(KEY,p);raise SystemExit('Unexpected photo receipt')
  p.update(delivery_status='sent',message_id=message['message_id'],sent_at=stamp(),photo_file_id=(message.get('photo') or [{}])[-1].get('file_id'))
  w.save(KEY,p)
 if p.get('old_message_status')!='deleted':
  p.update(old_message_status='deleting',deleting_at=stamp());w.save(KEY,p)
  try:result=tg('deleteMessage',json={'chat_id':p['chat_id'],'message_id':171})
  except Exception:
   p.update(old_message_status='uncertain');w.save(KEY,p);raise SystemExit('Delete uncertain; new report already delivered')
  if result.get('ok'):
   p.update(old_message_status='deleted',deleted_at=stamp())
  else:
   p.update(old_message_status='rejected',delete_error_code=result.get('error_code'))
  w.save(KEY,p)
 print(json.dumps({k:p.get(k) for k in ['delivery_status','message_id','old_message_id','old_message_status','sha256']},ensure_ascii=False))
 if p.get('old_message_status')!='deleted':raise SystemExit(1)
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise SystemExit('Public runner only')
 main()
