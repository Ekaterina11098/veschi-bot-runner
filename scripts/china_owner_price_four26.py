"""Owner-confirmed four exact seller price increases; no stock reads or Telegram."""
import os,time,json
from datetime import datetime,timezone
from china_price_apply import IO,plan,dec
KEY='china_agent:codex_price_four:2026-10-26:v1:execution'
AUTH='china_agent:codex_price_four:2026-10-26:v1:approval'
SS=json.loads('[{"nm_id":"1473243916","article":"64-NoelBag-zchocolate","current_cny":216,"target_cny":226.8,"base_cny":360,"seller_discount":40,"club_discount":0},{"nm_id":"1473243909","article":"57-NoelBag-burgundy","current_cny":198,"target_cny":207.9,"base_cny":360,"seller_discount":45,"club_discount":0},{"nm_id":"1535337780","article":"17-FurPanama-leo","current_cny":120,"target_cny":126,"base_cny":240,"seller_discount":50,"club_discount":0},{"nm_id":"1473245502","article":"524-SamiraBag-black","current_cny":299.5,"target_cny":314.5,"base_cny":599,"seller_discount":50,"club_discount":0}]')
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 os.environ.setdefault('CHINA_TELEGRAM_BOT_TOKEN','')
 io=IO();a=io.get(AUTH) or {}
 if a.get('owner_id')!=5122667182 or a.get('selections')!=SS or a.get('status')!='approved' or a.get('stock_recheck') is not False:raise RuntimeError('Exact approval missing')
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(a['created_at'])).total_seconds()
 if not 0<=age<=7200:raise RuntimeError('Approval expired')
 if io.get(KEY):raise RuntimeError('Execution exists; no blind repeat')
 io.capability()
 cfg=io.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id,owner_user_id')
 if cfg!=[dict(active=True,chat_id=-1004342917488,bot_id=8780468043,owner_user_id=5122667182)]:raise RuntimeError('Owner registration changed')
 fresh=io.prices([s['nm_id'] for s in SS]);items=[]
 for s in SS:
  p=fresh[s['nm_id']];req=plan(s,p)
  lk='china_agent:price_write_lock:v1:'+s['nm_id'];prev=io.get(lk)
  if prev and prev.get('status') in ['submitting','submitted','uncertain']:raise RuntimeError('Previous price write unresolved')
  items.append(dict(selection=s,before=p,request=req,lock=lk,status='ready' if req else 'already_at_target'))
 e=dict(status='preflight',approval_key=AUTH,items=items,telegram_sends=0,stock_reads=0,created_at=datetime.now(timezone.utc).isoformat())
 if not io.create(KEY,e):raise RuntimeError('Concurrent execution')
 for x in items:
  if not x['request']:continue
  lock=dict(execution=KEY,status='submitting',selection=x['selection'])
  if io.get(x['lock']):io.put(x['lock'],lock)
  elif not io.create(x['lock'],lock):raise RuntimeError('Concurrent SKU write')
 requests_body=[x['request'] for x in items if x['request']]
 if not requests_body:
  e['status']='verified';io.put(KEY,e);return
 e.update(status='submitting',request=dict(data=requests_body));io.put(KEY,e)
 try:
  result=io.wb('/api/v2/upload/task','POST',e['request']);task=result.get('id')
  if type(task) is not int or task<=0:raise RuntimeError('Missing upload ID')
  e.update(status='submitted',upload_id=task);io.put(KEY,e)
 except Exception:
  e['status']='uncertain';io.put(KEY,e);raise
 for _ in range(24):
  time.sleep(10)
  state=io.wb('/api/v2/history/tasks?uploadID='+str(task))
  if state.get('uploadID')!=task:raise RuntimeError('Upload identity mismatch')
  if state.get('status') not in [3,4,5,6]:continue
  detail=io.wb('/api/v2/history/goods/task?uploadID='+str(task)+'&limit=1000&offset=0')
  after=io.prices([x['selection']['nm_id'] for x in items if x['request']])
  for x in items:
   if not x['request']:continue
   s=x['selection'];req=x['request'];p=after[s['nm_id']]
   goods=[g for g in detail.get('historyGoods',[]) if str(g.get('nmID'))==s['nm_id']]
   ok=(state['status'] in [3,5] and detail.get('uploadID')==task and goods and not any(g.get('errorText') for g in goods) and p.get('vendorCode')==s['article'] and p.get('currencyIsoCode4217')=='CNY' and p.get('discount')==req['discount'] and p.get('clubDiscount')==s['club_discount'] and p.get('sizes') and all(dec(z['price'])==req['price'] and dec(z['discountedPrice'])==dec(s['target_cny']) for z in p['sizes']))
   x.update(status='applied' if ok else 'failed',readback=p)
   io.put(x['lock'],dict(execution=KEY,status='done' if ok else 'uncertain',upload_id=task,readback=p))
  ok=all(x['status'] in ['applied','already_at_target'] for x in items)
  e.update(status='verified' if ok else 'failed',wb_state=state,wb_details=detail,completed_at=datetime.now(timezone.utc).isoformat());io.put(KEY,e)
  if not ok:raise RuntimeError('Price readback mismatch')
  print('All four exact seller prices WB verified. No stock reads or Telegram.')
  return
 raise RuntimeError('WB still processing; no repeat')
if __name__=='__main__':run()
