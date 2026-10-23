import os,json,urllib.request,urllib.parse
BASE=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache'
KEY=os.environ['SUPABASE_SECRET_KEY'];TASK='china_agent:incorrect_replies_cleanup:20261023:v1'
def db(method,query='',body=None):
 req=urllib.request.Request(BASE+query,data=None if body is None else json.dumps(body).encode(),method=method,headers={'apikey':KEY,'Authorization':'Bearer '+KEY,'Content-Type':'application/json','Prefer':'resolution=merge-duplicates,return=representation'})
 with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
def save(p):db('POST','?on_conflict=cache_key',dict(cache_key=TASK,payload=p,expires_at='2027-01-01T00:00:00Z'))
def tg(method,args):
 req=urllib.request.Request('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN']+'/'+method,data=json.dumps(args).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=35) as r:j=json.load(r)
 if not j.get('ok'):raise RuntimeError('Telegram rejected cleanup')
 return j['result']
p=db('GET','?cache_key=eq.'+urllib.parse.quote(TASK)+'&select=payload')[0]['payload']
if p['status']=='delivered':print('already delivered');raise SystemExit
if p['status'] in ('sending','uncertain'):raise RuntimeError('Investigate uncertain cleanup')
assert tg('getMe',{})['id']==8780468043 and p['chat_id']==-1004342917488
p['status']='sending';save(p)
try:
 result=tg('deleteMessages',dict(chat_id=p['chat_id'],message_ids=p['message_ids']))
 assert result is True
 p['status']='delivered';p['receipt']=dict(ok=True,method='deleteMessages',message_ids=p['message_ids']);save(p)
except Exception:
 p['status']='uncertain';save(p);raise
print(json.dumps(p['receipt']))
