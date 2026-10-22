import os,json,base64,hashlib,datetime,requests
u=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache'
h={'apikey':os.environ['SUPABASE_SECRET_KEY'],'Authorization':'Bearer '+os.environ['SUPABASE_SECRET_KEY'],'Content-Type':'application/json'}
key='china_agent:loss_new_recommendations_send:2026-10-22:v1'
def read(k):
 r=requests.get(u,headers=h,params={'cache_key':'eq.'+k,'select':'payload'},timeout=30);r.raise_for_status();return r.json()
prior=read(key)
if prior:
 print(json.dumps({'existing':prior[0]['payload'].get('status'),'no_resend':True}));raise SystemExit()
p=read('china_agent:loss_new_recommendations_png:2026-10-22:v1')[0]['payload'];b=base64.b64decode(p['b64']);assert hashlib.sha256(b).hexdigest()==p['sha256']
row={'cache_key':key,'payload':{'status':'sending','sha256':p['sha256'],'chat_id':-1004342917488},'expires_at':'2027-01-22T00:00:00Z'}
r=requests.post(u,headers={**h,'Prefer':'resolution=ignore-duplicates,return=representation'},json=row,timeout=30);r.raise_for_status()
if not r.json():raise SystemExit('Concurrent claim, not sending')
try:
 r=requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN']+'/sendDocument',data={'chat_id':-1004342917488,'caption':p['caption']},files={'document':(p['filename'],b,'image/png')},timeout=60)
 j=r.json();ok=j.get('ok') is True
 out={'status':'delivered' if ok else 'failed','sha256':p['sha256'],'chat_id':-1004342917488,'message_id':j.get('result',{}).get('message_id'),'delivered_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'wb_writes':0}
except Exception as e:out={'status':'uncertain','error_type':type(e).__name__,'wb_writes':0}
r=requests.patch(u,headers=h,params={'cache_key':'eq.'+key},json={'payload':out},timeout=30);r.raise_for_status()
print(json.dumps(out))
