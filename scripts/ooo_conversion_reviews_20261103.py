"""Read-only review evidence for OOO conversion diagnosis; no replies or ad changes."""
import os,time,json,re,hashlib,datetime,requests
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:conversion_review:2026-11-03:feedbacks'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'parts':{}}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO scope required')
 return a
w.authorize=scope
if not w.claim(w.state):print('Existing review evidence preserved');raise SystemExit(0)
host='feedbacks-api.wildberries.ru';path='/api/v1/feedbacks'
pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+path).encode()).hexdigest()
def clean(s):
 s=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[email removed]',str(s or ''))
 return re.sub(r'(?<!\w)\+?\d[\d ()-]{8,}\d','[phone removed]',s)
since=int(datetime.datetime(2026,10,20,tzinfo=datetime.timezone(datetime.timedelta(hours=3))).timestamp())
for answered in (True,False):
 label='answered' if answered else 'unanswered'
 until=float((w.get(pk) or {}).get('until',0))
 if until>time.time():
  w.state['parts'][label]={'status':'provider_cooldown','resume_epoch':until};w.save();continue
 try:
  scope()
  r=requests.get('https://'+host+path,headers={'Authorization':w.TOKEN},params={'isAnswered':str(answered).lower(),'take':5000,'skip':0,'order':'dateDesc','dateFrom':since,'dateTo':int(time.time())},timeout=(10,90),allow_redirects=False)
  delay=r.headers.get('Retry-After') or r.headers.get('X-Ratelimit-Retry') or r.headers.get('X-Ratelimit-Reset')
  try:seconds=float(delay) if delay else 0
  except ValueError:seconds=0
  if r.status_code==429 or (r.headers.get('X-Ratelimit-Remaining')=='0' and seconds>0):w.put(pk,{'until':time.time()+max(seconds,60)+3,'basis':'provider_header'})
  if not r.ok:raise RuntimeError('Feedback API HTTP '+str(r.status_code)+' '+r.text[:1000])
  rows=r.json().get('data',{}).get('feedbacks')
  if not isinstance(rows,list):raise RuntimeError('Feedback schema invalid')
  safe=[]
  for x in rows:
   p=x.get('productDetails') or {}
   safe.append({'nm_id':p.get('nmId'),'article':p.get('supplierArticle'),'valuation':x.get('productValuation'),'created_at':x.get('createdDate'),'text':clean(x.get('text')),'pros':clean(x.get('pros')),'cons':clean(x.get('cons'))})
  w.state['parts'][label]={'status':'complete' if len(rows)<5000 else 'partial_pagination_needed','rows':safe,'count':len(rows),'observed_at':w.stamp()}
 except Exception as e:w.state['parts'][label]={'status':'unavailable','error':str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__}
 w.save();time.sleep(2)
w.state.update(status='finished',finished_at=w.stamp());w.save()
print('Review evidence saved privately; no customer communication')
