import os,json,requests
from datetime import datetime,timezone
BASE=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache'
H={'apikey':os.environ['SUPABASE_SECRET_KEY'],'Authorization':'Bearer '+os.environ['SUPABASE_SECRET_KEY'],'Content-Type':'application/json'}
KEY='china_agent:owner_delete:194:v1'
def get(key):
 r=requests.get(BASE,headers=H,params={'cache_key':'eq.'+key,'select':'payload'},timeout=40);r.raise_for_status();rows=r.json();return rows[0]['payload'] if rows else None
def put(key,value):
 r=requests.post(BASE,headers=dict(H,Prefer='resolution=merge-duplicates'),params={'on_conflict':'cache_key'},json={'cache_key':key,'payload':value,'updated_at':datetime.now(timezone.utc).isoformat(),'expires_at':'2030-01-01T00:00:00Z'},timeout=40);r.raise_for_status()
old=get(KEY)
if old:
 print(json.dumps({'status':old.get('status'),'no_retry':True}));raise SystemExit(0)
delivery=get('china_agent:loss_report:2026-10-25:v2')
parts=delivery.get('parts',[])
part=next((p for p in parts if p.get('message_id')==194),None)
assert part and part['receipt']['from']['id']==8780468043 and part['receipt']['chat']['id']==-1004342917488
assert part['receipt'].get('caption')=='Китай · требует внимания · 2026-10-25. Рекомендации не применены.'
token=os.environ['CHINA_TELEGRAM_BOT_TOKEN'];url='https://api.telegram.org/bot'+token
me=requests.get(url+'/getMe',timeout=30).json();assert me.get('ok') and me['result']['id']==8780468043
audit={'status':'sending','message_id':194,'chat_id':-1004342917488,'operation':'deleteMessage','authorization':'explicit human request 25Oct screenshot loss report; preserve original receipt','started_at':datetime.now(timezone.utc).isoformat()}
put(KEY,audit)
try:
 r=requests.post(url+'/deleteMessage',json={'chat_id':-1004342917488,'message_id':194},timeout=40);j=r.json()
 audit.update(status='deleted' if j.get('ok') and j.get('result') is True else 'failed',http=r.status_code,receipt=j,completed_at=datetime.now(timezone.utc).isoformat());put(KEY,audit)
 if audit['status']=='deleted':
  part['owner_deleted_at']=audit['completed_at'];part['owner_delete_receipt_key']=KEY;put('china_agent:loss_report:2026-10-25:v2',delivery)
 print(json.dumps({'status':audit['status'],'message_id':194,'wb_writes':0}))
except Exception:
 audit.update(status='uncertain');put(KEY,audit);raise RuntimeError('Deletion result uncertain; do not retry')
