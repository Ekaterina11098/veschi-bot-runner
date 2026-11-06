"""Replace only two acknowledged pilot photos with approved layout. No model or WB."""
import os,json,base64,hashlib,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:cloud_pilot:2026-11-06:v1'
def run():
 db=DB();key=ROOT+':reference_cell:execution'
 if db.get(key):print('Existing format correction retained; no blind repeat');return
 state={'status':'starting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':stamp(),'model_calls':0,'wb_calls':0,'new_messages':0}
 db.once(key,state)
 try:
  auth=db.get(ROOT+':authorization')or{};old=db.get(ROOT+':execution:binding_continuation')or{};payload=db.get(ROOT+':reference_cell:input')or{}
  if auth.get('approved')is not True or old.get('status')!='verified'or payload.get('revision')!=8:raise ValueError('Pilot revision not bound')
  source=db.get(payload.get('report_source',''))or{}
  review=db.get(ROOT+':risk_review:analysis')or{}
  if payload.get('report_only')is not True or source.get('status')!='finished' or review.get('status')!='analysis_complete_proposals_only' or review.get('telegram_ready')is not True:raise ValueError('Complete report evidence required before delivery')
  if any(source.get('sources',{}).get(k,{}).get('status')!='complete'for k in ['advertising_today','budgets']):raise ValueError('Missing required source; no delivery')
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
   data=base64.b64decode(''.join(db.get(k)['data']for k in image['chunk_keys']),validate=True)
   if len(data)!=image['bytes']or hashlib.sha256(data).hexdigest()!=image['sha256']or not data.startswith(bytes([137,80,78,71,13,10,26,10])):raise ValueError('Artifact integrity mismatch')
   ek=ROOT+':reference_cell:edit:'+kind
   if db.get(ek):raise RuntimeError('Existing edit receipt; no replay')
   db.once(ek,{'status':'submitting','chat_id':chat,'message_id':receipt['message_id'],'submitted_at':stamp()})
   media={'type':'photo','media':'attach://photo','caption':''}
   try:
    response=requests.post('https://api.telegram.org/bot'+token+'/editMessageMedia',data={'chat_id':chat,'message_id':receipt['message_id'],'media':json.dumps(media,ensure_ascii=False)},files={'photo':(kind+'.png',data,'image/png')},timeout=(10,60),allow_redirects=False)
    result=response.json().get('result',{})if response.status_code==200 else{}
    if result.get('message_id')!=receipt['message_id']or result.get('chat',{}).get('id')!=chat:raise RuntimeError('Edit not confirmed')
   except Exception:
    db.update(ek,{'status':'uncertain','chat_id':chat,'message_id':receipt['message_id'],'observed_at':stamp()});raise RuntimeError('Edit outcome uncertain; no blind repeat')from None
   v={'status':'edited_verified','chat_id':chat,'message_id':receipt['message_id'],'sha256':image['sha256'],'bytes':len(data),'edited_at':stamp()};db.update(ek,v);edited.append(v)
  deleted=[]
  allowed=[]
  for suffix in [':delivery:answer',':full_report:delivery:answer']:
   prior=db.get(ROOT+suffix)or{}
   if prior.get('status')=='sent'and prior.get('chat_id')==chat:allowed.append(prior['message_id'])
  for mid in payload.get('delete_message_ids',[]):
   if mid not in allowed:raise ValueError('Unconfirmed own text message')
   dk=ROOT+':reference_cell:delete:'+str(mid)
   if db.get(dk):raise RuntimeError('Deletion already attempted; no blind repeat')
   db.once(dk,{'status':'submitting','chat_id':chat,'message_id':mid})
   response=requests.post('https://api.telegram.org/bot'+token+'/deleteMessage',data={'chat_id':chat,'message_id':mid},timeout=(10,30),allow_redirects=False)
   if response.status_code!=200 or response.json().get('result')is not True:
    db.update(dk,{'status':'uncertain','chat_id':chat,'message_id':mid});raise RuntimeError('Text deletion not confirmed')
   db.update(dk,{'status':'deleted_verified','chat_id':chat,'message_id':mid,'deleted_at':stamp()});deleted.append(mid)
  state.update(status='verified',edits=edited,deleted_text_ids=deleted,finished_at=stamp());db.update(key,state)
 except Exception as e:
  state.update(status='attention',error_type=type(e).__name__,safe_error=str(e)if isinstance(e,(ValueError,RuntimeError))else None,failed_at=stamp());db.update(key,state)
  print('Format edit stopped; private receipts retained');return
 print('Both original pilot images replaced; no model or new message')
if __name__=='__main__':run()


