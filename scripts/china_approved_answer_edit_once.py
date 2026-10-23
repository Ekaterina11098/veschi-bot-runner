import os,json,urllib.request,urllib.parse,datetime,hashlib
BASE=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache'
KEY=os.environ['SUPABASE_SECRET_KEY']
TASK='china_agent:approved_answer_edit:20261023:v1'
def db(method,query='',body=None):
 data=None if body is None else json.dumps(body).encode()
 req=urllib.request.Request(BASE+query,data=data,method=method,headers={'apikey':KEY,'Authorization':'Bearer '+KEY,'Content-Type':'application/json','Prefer':'resolution=merge-duplicates,return=representation'})
 with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
def save(p):
 db('POST','?on_conflict=cache_key',{'cache_key':TASK,'payload':p,'expires_at':'2027-01-01T00:00:00Z'})
rows=db('GET','?cache_key=eq.'+urllib.parse.quote(TASK)+'&select=payload')
p=rows[0]['payload']
token=os.environ['CHINA_TELEGRAM_BOT_TOKEN']
def tg(method,args):
 req=urllib.request.Request('https://api.telegram.org/bot'+token+'/'+method,data=json.dumps(args).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=35) as r:result=json.load(r)
 if not result.get('ok'):raise RuntimeError('Telegram operation rejected')
 return result['result']
me=tg('getMe',{})
assert me['id']==8780468043 and p['chat_id']==-1004342917488
for item in p['operations']:
 if item.get('status')=='delivered':continue
 if item.get('status') in ('sending','uncertain'):raise RuntimeError('Uncertain operation requires investigation')
 item['status']='sending';save(p)
 try:
  result=tg(item['method'],item['arguments'])
  item['status']='delivered';item['receipt']={'message_id':result.get('message_id'),'chat_id':result.get('chat',{}).get('id'),'date':result.get('date'),'edit_date':result.get('edit_date')}
  assert item['receipt']['chat_id']==p['chat_id']
  save(p)
 except Exception:
  item['status']='uncertain';save(p);raise
p['status']='delivered';save(p)
print(json.dumps({'status':'delivered','operations':[{'status':x['status'],'receipt':x.get('receipt')} for x in p['operations']]}))
