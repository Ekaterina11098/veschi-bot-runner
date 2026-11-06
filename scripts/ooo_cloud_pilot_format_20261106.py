"""Replace only two acknowledged pilot photos with approved layout. No model or WB."""
import os,json,base64,hashlib,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:cloud_pilot:2026-11-06:v1'
def run():
 db=DB();key=ROOT+':format_edit_execution'
 if db.get(key):print('Existing format correction retained; no blind repeat');return
 state={'status':'starting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':stamp(),'model_calls':0,'wb_calls':0,'new_messages':0}
 db.once(key,state)
 try:
  auth=db.get(ROOT+':authorization')or{};old=db.get(ROOT+':execution:binding_continuation')or{};payload=db.get(ROOT+':format_revision2')or{}
  if auth.get('approved')is not True or old.get('status')!='verified'or payload.get('revision')!=2:raise ValueError('Pilot revision not bound')
  chat=old['chat_id'];token=os.environ['OOO_TELEGRAM_BOT_TOKEN']
  r=requests.post('https://api.telegram.org/bot'+token+'/getMe',timeout=(10,30))
  if r.status_code!=200 or r.json().get('result',{}).get('username','').casefold()!=auth['expected_username'].casefold():raise ValueError('Bot identity mismatch')
  state.update(status='editing',chat_id=chat);db.update(key,state)
  edited=[]
  for image in payload['images']:
   kind=image['kind']
   if kind not in('advertising','budgets'):raise ValueError('Unknown artifact')
   receipt=db.get(ROOT+':delivery:'+kind)or{}
   if receipt.get('status')!='sent'or receipt.get('chat_id')!=chat or receipt.get('message_id')not in old['message_ids']:raise ValueError('Original photo delivery not confirmed')
   data=base64.b64decode(image['png_base64'],validate=True)
   if len(data)!=image['bytes']or hashlib.sha256(data).hexdigest()!=image['sha256']or not data.startswith(bytes([137,80,78,71,13,10,26,10])):raise ValueError('Artifact integrity mismatch')
   ek=ROOT+':format_edit:'+kind
   if db.get(ek):raise RuntimeError('Existing edit receipt; no replay')
   db.once(ek,{'status':'submitting','chat_id':chat,'message_id':receipt['message_id'],'submitted_at':stamp()})
   media={'type':'photo','media':'attach://photo','caption':'Пилот · исправленный согласованный формат · '+('реклама'if kind=='advertising'else'бюджеты')+' · датированный кэш'}
   try:
    response=requests.post('https://api.telegram.org/bot'+token+'/editMessageMedia',data={'chat_id':chat,'message_id':receipt['message_id'],'media':json.dumps(media,ensure_ascii=False)},files={'photo':(kind+'.png',data,'image/png')},timeout=(10,60),allow_redirects=False)
    result=response.json().get('result',{})if response.status_code==200 else{}
    if result.get('message_id')!=receipt['message_id']or result.get('chat',{}).get('id')!=chat:raise RuntimeError('Edit not confirmed')
   except Exception:
    db.update(ek,{'status':'uncertain','chat_id':chat,'message_id':receipt['message_id'],'observed_at':stamp()});raise RuntimeError('Edit outcome uncertain; no blind repeat')from None
   v={'status':'edited_verified','chat_id':chat,'message_id':receipt['message_id'],'sha256':image['sha256'],'bytes':len(data),'edited_at':stamp()};db.update(ek,v);edited.append(v)
  state.update(status='verified',edits=edited,finished_at=stamp());db.update(key,state)
 except Exception as e:
  state.update(status='attention',error_type=type(e).__name__,safe_error=str(e)if isinstance(e,(ValueError,RuntimeError))else None,failed_at=stamp());db.update(key,state)
  print('Format edit stopped; private receipts retained');return
 print('Both original pilot images replaced; no model or new message')
if __name__=='__main__':run()
