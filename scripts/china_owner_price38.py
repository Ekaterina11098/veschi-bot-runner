"""One-off exact Codex owner-confirmed38 seller price; no Telegram."""
import os,time
from datetime import datetime,timezone
from china_price_apply import IO,plan,dec
KEY='china_agent:codex_price38:2026-10-26:v1:execution'
AUTH='china_agent:codex_price38:2026-10-26:v1:approval'
S=dict(nm_id='1560345289',article='38-FurManizhka-white',current_cny=247.5,target_cny=260.15,base_cny=450,seller_discount=45,club_discount=0)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 os.environ.setdefault('CHINA_TELEGRAM_BOT_TOKEN','')
 io=IO();a=io.get(AUTH) or {}
 if a.get('owner_id')!=5122667182 or a.get('selection')!=S or a.get('status')!='approved':raise RuntimeError('Exact approval missing')
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(a['created_at'])).total_seconds()
 if not 0<=age<=7200:raise RuntimeError('Approval expired')
 if io.get(KEY):raise RuntimeError('Execution exists; no blind repeat')
 io.capability()
 cfg=io.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id,owner_user_id')
 if cfg!=[dict(active=True,chat_id=-1004342917488,bot_id=8780468043,owner_user_id=5122667182)]:raise RuntimeError('Owner registration changed')
 p=io.prices([S['nm_id']])[S['nm_id']]
 req=plan(S,p)
 if not req:raise RuntimeError('Already at target; no write')
 lk='china_agent:price_write_lock:v1:'+S['nm_id'];prev=io.get(lk)
 if prev and prev.get('status') in ['submitting','submitted','uncertain']:raise RuntimeError('Previous price write unresolved')
 e=dict(status='preflight',approval_key=AUTH,selection=S,before=p,request={'data':[req]},telegram_sends=0,created_at=datetime.now(timezone.utc).isoformat())
 if not io.create(KEY,e):raise RuntimeError('Concurrent execution')
 lock=dict(execution=KEY,status='submitting',selection=S)
 if prev:io.put(lk,lock)
 elif not io.create(lk,lock):raise RuntimeError('Concurrent SKU write')
 e['status']='submitting';io.put(KEY,e)
 try:
  result=io.wb('/api/v2/upload/task','POST',e['request'])
  task=result.get('id')
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
  goods=[g for g in detail.get('historyGoods',[]) if str(g.get('nmID'))==S['nm_id']]
  p=io.prices([S['nm_id']])[S['nm_id']]
  ok=(state['status'] in [3,5] and detail.get('uploadID')==task and goods and not any(g.get('errorText') for g in goods) and p.get('vendorCode')==S['article'] and p.get('currencyIsoCode4217')=='CNY' and p.get('discount')==45 and p.get('clubDiscount')==0 and p.get('sizes') and all(dec(z['price'])==473 and dec(z['discountedPrice'])==dec(260.15) for z in p['sizes']))
  e.update(status='verified' if ok else 'failed',after=p,wb_state=state,wb_details=detail,completed_at=datetime.now(timezone.utc).isoformat());io.put(KEY,e)
  io.put(lk,dict(execution=KEY,status='done' if ok else 'uncertain',upload_id=task,readback=p))
  if not ok:raise RuntimeError('Price readback mismatch')
  print('38 seller price247.50 to260.15CNY verified; base473,discount45.')
  return
 raise RuntimeError('WB still processing; no repeat')
if __name__=='__main__':run()
