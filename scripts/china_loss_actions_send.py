import os,json,base64,hashlib,datetime,requests
u=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache'
h={'apikey':os.environ['SUPABASE_SECRET_KEY'],'Authorization':'Bearer '+os.environ['SUPABASE_SECRET_KEY'],'Content-Type':'application/json'}
key='china_agent:delete_wrong_loss_answer:2026-10-22:104'
def read(k):
 r=requests.get(u,headers=h,params={'cache_key':'eq.'+k,'select':'payload'},timeout=30);r.raise_for_status();return r.json()
old=read(key)
if old and old[0]['payload'].get('status')=='deleted':raise SystemExit('already_deleted')
r=requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN']+'/deleteMessage',json={'chat_id':-1004342917488,'message_id':104},timeout=30);j=r.json()
if not j.get('ok'):raise RuntimeError('Deletion not confirmed')
out={'status':'deleted','message_id':104,'chat_id':-1004342917488,'result':j['result'],'wb_writes':0,'at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
r=requests.post(u,headers={**h,'Prefer':'resolution=merge-duplicates'},json={'cache_key':key,'payload':out,'expires_at':'2036-10-22T00:00:00Z'},timeout=30);r.raise_for_status()
print(json.dumps(out))
