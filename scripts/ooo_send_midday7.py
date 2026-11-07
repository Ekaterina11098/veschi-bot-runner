"""Send one private approved dated PNG pair once. No WB, model, or schedules."""
import os,json,base64,hashlib,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:midday:2026-11-07:1500:telegram'
def run():
 db=DB();p=db.get(ROOT+':input')or{}
 if p.get('owner_approved')is not True or p.get('chat_id')!=-5459387392 or p.get('kinds')!=['midday']:raise PermissionError('Exact owner delivery approval required')
 if db.get(ROOT+':execution'):print('Existing delivery retained; no replay');return
 state={'status':'preparing','started_at':stamp(),'run_id':os.environ['GITHUB_RUN_ID'],'chat_id':p['chat_id'],'receipts':[],'wb_calls':0,'model_calls':0};db.once(ROOT+':execution',state)
 def save():db.update(ROOT+':execution',state)
 try:
  report=db.get('ooo_agent:midday:2026-11-07:1500:report')or{}
  if report.get('status')!='ready':raise RuntimeError('Prepared report missing')
  token=os.environ['OOO_TELEGRAM_BOT_TOKEN'];url='https://api.telegram.org/bot'+token
  me=requests.post(url+'/getMe',timeout=(10,30),allow_redirects=False)
  if me.status_code!=200 or me.json().get('result',{}).get('username','').casefold()!='veschi_ooo_bot':raise RuntimeError('Bot identity mismatch')
  for im in p['images']:
   raw=base64.b64decode(''.join(db.get(k)['data']for k in im['chunk_keys']),validate=True)
   if len(raw)!=im['bytes']or hashlib.sha256(raw).hexdigest()!=im['sha256']or not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise RuntimeError('Artifact integrity mismatch')
   key=ROOT+':delivery:'+im['kind']
   if db.get(key):raise RuntimeError('Existing photo attempt; do not repeat unknown result')
   receipt={'status':'submitting','chat_id':p['chat_id'],'sha256':im['sha256'],'submitted_at':stamp()};db.once(key,receipt)
   try:
    r=requests.post(url+'/sendPhoto',data={'chat_id':p['chat_id']},files={'photo':(im['kind']+'.png',raw,'image/png')},timeout=(10,60),allow_redirects=False)
    result=r.json().get('result',{})if r.status_code==200 else{}
    if not isinstance(result.get('message_id'),int)or result.get('chat',{}).get('id')!=p['chat_id']:raise RuntimeError('Photo delivery unconfirmed')
   except Exception:
    receipt.update(status='uncertain',observed_at=stamp());db.update(key,receipt);raise RuntimeError('Photo outcome uncertain; never blind resend')from None
   receipt.update(status='sent',message_id=result['message_id'],sent_at=stamp());db.update(key,receipt);state['receipts'].append({'kind':im['kind'],'message_id':result['message_id']});save()
  state.update(status='verified',verified_at=stamp());save();print('One intraday PNG message confirmed; no WB or model calls')
 except Exception as e:
  state.update(status='attention',safe_error=str(e)if isinstance(e,RuntimeError)else type(e).__name__);save();print('Delivery stopped; private receipt retained')
if __name__=='__main__':run()

