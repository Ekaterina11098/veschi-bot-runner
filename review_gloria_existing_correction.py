"""Correct only the explicitly authorized article in one already accepted answer."""
import os,json,hmac,hashlib,time,re
import requests,psycopg
PLAN='owner-article-correction:20261021:gloria:v1:plan'
RECEIPT=PLAN+':existing-answer-correction'
def norm(s):return re.sub(r'\s+',' ',s).strip()
def main():
 root=os.environ['SUPABASE_SECRET_KEY'].encode()
 pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
 with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15) as conn:
  conn.execute("SELECT pg_advisory_lock(hashtextextended('review-gloria-article-correction:20261021',0))")
  def get(key):
   row=conn.execute('SELECT payload FROM review_approval.events WHERE id=%s',(key,)).fetchone()
   return json.loads(row[0]) if row else None
  def put(data):
   conn.execute('INSERT INTO review_approval.events(id,payload) VALUES(%s,%s) ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload',(RECEIPT,json.dumps(dict(data,checked_at=time.time(),run_id=os.getenv('GITHUB_RUN_ID')),ensure_ascii=False)))
  plan=get(PLAN)
  if not plan or plan.get('authorization_channel')!='owner_chat':raise RuntimeError('Owner authorization unavailable')
  target=plan['targets'][0]
  if len(plan['targets'])!=1 or target['item_id']!='qFh_WKEBACfpILHUn2Dx' or target['cabinet']!='token_3' or target['from_article']!='1473246032' or target['to_article']!='1473244000':raise RuntimeError('Exact correction scope mismatch')
  rows=conn.execute("SELECT id,payload FROM review_approval.intents WHERE payload::jsonb->>'cabinet'='token_3' AND payload::jsonb->>'item_id'=%s",(target['item_id'],)).fetchall()
  if len(rows)!=1:raise RuntimeError('Exactly one existing intent required')
  intent_id,raw=rows[0];intent=json.loads(raw)
  if intent['status']!='confirmed' or intent['answer'].count(target['from_article'])!=1:raise RuntimeError('Exact accepted original required')
  old=intent['answer'];new=old.replace(target['from_article'],target['to_article'])
  previous=get(RECEIPT) or {}
  if previous.get('status')=='verified':print('Existing answer correction already verified');return
  base=dict(previous,intent_id=intent_id,item_id=target['item_id'],cabinet='token_3',authorization_ref=PLAN,old_answer=old,corrected_answer=new)
  def read():
   r=requests.get('https://feedbacks-api.wildberries.ru/api/v1/question',headers={'Authorization':os.environ['WB_TOKEN_3']},params={'id':target['item_id']},timeout=20)
   if r.status_code==429:
    put(dict(base,status='rate_limited',retry_at=time.time()+float(r.headers.get('X-RateLimit-Retry') or 720)));raise RuntimeError('WB rate limit: no write attempted')
   if r.status_code!=200:raise RuntimeError('Exact WB read unavailable')
   b=r.json();d=b.get('data')
   if b.get('error') or not isinstance(d,dict) or d.get('id')!=target['item_id'] or (d.get('productDetails') or {}).get('nmId')!=1473244000:raise RuntimeError('Exact WB question/product mismatch')
   return d
  def verify(d):
   answer=d.get('answer') or {}
   if norm(answer.get('text',''))!=norm(new):return False
   put(dict(base,status='verified',verified_at=time.time(),answer_state=answer.get('state'),editable=answer.get('editable'),duplicate_publications_created=0))
   with conn.transaction():
    current=json.loads(conn.execute('SELECT payload FROM review_approval.intents WHERE id=%s FOR UPDATE',(intent_id,)).fetchone()[0])
    current.update(owner_corrected_answer=new,owner_correction_ref=PLAN,owner_corrected_answer_verified_at=time.time(),owner_corrected_answer_sha256=hashlib.sha256(new.encode()).hexdigest())
    current.pop('public_verified_at',None)
    current.pop('wb_ui_status',None)
    conn.execute('UPDATE review_approval.intents SET payload=%s WHERE id=%s',(json.dumps(current,ensure_ascii=False),intent_id))
   return True
  d=read()
  if verify(d):print('Corrected existing answer verified');return
  a=d.get('answer') or {}
  if base.get('write_attempted_at'):put(dict(base,status='verify_only_pending'));print('Prior correction result remains unknown: read only');return
  if norm(a.get('text',''))!=norm(old) or a.get('editable') is not True:raise RuntimeError('Existing answer changed or cannot be edited')
  base.update(write_attempted_at=time.time());put(dict(base,status='write_intent'))
  try:
   r=requests.patch('https://feedbacks-api.wildberries.ru/api/v1/questions',headers={'Authorization':os.environ['WB_TOKEN_3']},json={'id':target['item_id'],'answer':{'text':new},'state':'wbRu'},timeout=20)
   base['write_http_status']=r.status_code
   put(dict(base,status='verify'))
  except requests.RequestException:
   put(dict(base,status='verify_unknown'))
  time.sleep(2)
  if verify(read()):print('Existing answer corrected and exact text verified; no duplicate created')
  else:print('Correction result unconfirmed; read-only follow-up required')
if __name__=='__main__':
 try:main()
 except Exception:
  print('Correction stopped safely. No blind retry or duplicate publication.');raise SystemExit(1)
