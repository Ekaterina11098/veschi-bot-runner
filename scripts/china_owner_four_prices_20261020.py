"""One owner-authorized batch; durable state, exact targets, no Telegram."""
import os,json,time
from china_price_apply import IO,plan,dec,now
KEY='china_agent:manual_price_install:2026-10-20:15-63-119-38:v1'
S=[
dict(nm_id='1535337778',article='15-FurPanama-cream',current_cny='79',target_cny='85.5',base_cny='158',seller_discount=50,club_discount=0),
dict(nm_id='1560230897',article='63-4belts115-brown',current_cny='97',target_cny='104.5',base_cny='194',seller_discount=50,club_discount=0),
dict(nm_id='1473243898',article='119-NoelBag-darkblack',current_cny='146.4',target_cny='207.6',base_cny='366',seller_discount=60,club_discount=0),
dict(nm_id='1560345289',article='38-FurManizhka-white',current_cny='203.5',target_cny='221.65',base_cny='370',seller_discount=45,club_discount=0)]
TARGETS=[dict(nmID=1535337778,price=171,discount=50),dict(nmID=1560230897,price=209,discount=50),dict(nmID=1473243898,price=519,discount=60),dict(nmID=1560345289,price=403,discount=45)]
def summary(e):
 print(json.dumps(dict(status=e['status'],upload_id=e.get('upload_id'),completed_at=e.get('completed_at'),items=[dict(article=x['selection']['article'],status=x['status'],request=x.get('request')) for x in e.get('items',[])]),ensure_ascii=False))
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_EVENT_NAME')!='push' or os.environ.get('GITHUB_REF')!='refs/heads/china-owner-four-prices-20261020':
  raise ValueError('Wrong execution scope')
 io=IO();io.capability()
 e=io.get(KEY)
 if e and e['status'] in ['done','uncertain','blocked']:summary(e);return
 if e and e['status']=='submitting':
  e['status']='uncertain';e['reason']='Possible WB submission without receipt; no blind retry';io.put(KEY,e);summary(e);return
 if not e:
  e=dict(status='preflight',created_at=now().isoformat(),actor_user_id=5122667182,authorization='Explicit Codex owner instructions:15/63/119 and screenshot38; preserve discounts',selections=S,items=[],telegram_calls=0)
  if not io.create(KEY,e):raise ValueError('Concurrent manual audit')
 if e['status']=='preflight':
  fresh=io.prices([s['nm_id'] for s in S])
  planned=[plan(s,fresh[s['nm_id']]) for s in S]
  for index,(s,request) in enumerate(zip(S,planned)):
   if request and request!=TARGETS[index]:raise ValueError('Target mismatch')
   lk='china_agent:price_write_lock:v1:'+s['nm_id'];prior=io.get(lk)
   if prior and prior.get('execution')!=KEY and prior.get('status') in ['submitting','submitted','uncertain']:raise ValueError('Active item lock')
  for s,request in zip(S,planned):
   lk='china_agent:price_write_lock:v1:'+s['nm_id']
   if request:
    prior=io.get(lk);state=dict(execution=KEY,status='submitting',selection=s,created_at=now().isoformat())
    if prior:io.put(lk,state)
    elif not io.create(lk,state):raise ValueError('Concurrent item lock')
   e['items'].append(dict(selection=s,request=request,status='ready' if request else 'already_at_target',lock=lk,preflight=fresh[s['nm_id']]))
  io.put(KEY,e)
  # Fresh validation immediately before single POST; no other price proposals.
  again=io.prices([s['nm_id'] for s in S])
  for x in e['items']:
   if plan(x['selection'],again[x['selection']['nm_id']])!=x['request']:raise ValueError('Price changed during preparation')
  req=[x['request'] for x in e['items'] if x['request']]
  if not req:
   e['status']='done';e['completed_at']=now().isoformat();io.put(KEY,e);summary(e);return
  e['request']=dict(data=req);e['status']='submitting';io.put(KEY,e)
  try:
   result=io.wb('/api/v2/upload/task','POST',e['request'])
   if type(result.get('id')) is not int or result['id']<=0:raise ValueError('No upload receipt')
   e['upload_id']=result['id'];e['upload_response']=result;e['status']='submitted';io.put(KEY,e)
   for x in e['items']:
    if x['request']:io.put(x['lock'],dict(execution=KEY,status='submitted',upload_id=e['upload_id']))
  except Exception:
   e['status']='uncertain';e['reason']='Submission result uncertain; retries blocked';io.put(KEY,e);summary(e);return
 if e['status']=='submitted':
  for _ in range(12):
   state=io.wb('/api/v2/history/tasks?uploadID='+str(e['upload_id']))
   if state.get('uploadID')!=e['upload_id']:raise ValueError('Task mismatch')
   e['wb_state']=state;io.put(KEY,e)
   if state.get('status') in [3,4,5,6]:
    details=io.wb('/api/v2/history/goods/task?uploadID='+str(e['upload_id'])+'&limit=1000&offset=0')
    if details.get('uploadID')!=e['upload_id']:raise ValueError('Details mismatch')
    e['wb_details']=details;fresh=io.prices([s['nm_id'] for s in S])
    for x in e['items']:
     s=x['selection'];p=fresh[s['nm_id']];expected=TARGETS[S.index(s)]
     goods=[g for g in details.get('historyGoods',[]) if str(g.get('nmID'))==s['nm_id']]
     ok=(p.get('vendorCode')==s['article'] and p.get('currencyIsoCode4217')=='CNY' and p.get('discount')==expected['discount'] and p.get('clubDiscount')==0 and p.get('sizes') and all(dec(z['price'])==dec(expected['price']) and dec(z['discountedPrice'])==dec(s['target_cny']) for z in p['sizes']))
     if x['request']:ok=ok and state['status'] in [3,5] and bool(goods) and not any(g.get('errorText') for g in goods)
     x['status']='applied' if ok else 'failed';x['readback']=p
     if x['request']:io.put(x['lock'],dict(execution=KEY,status='done' if ok else 'uncertain',upload_id=e['upload_id'],readback=p))
    e['status']='done' if all(x['status']=='applied' for x in e['items']) else 'uncertain';e['completed_at']=now().isoformat();io.put(KEY,e);summary(e);return
   time.sleep(15)
  summary(e)
if __name__=='__main__':main()
