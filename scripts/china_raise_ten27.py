"""Dated owner-selected ten CPC increases, explicit Codex authorization; no funding."""
import argparse,copy,hashlib,json,os,time
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,projection
from china_price_apply import IO
ROOT='china_agent:owner_raise_ten:2026-10-27:v1'
def stamp():return datetime.now(timezone.utc).isoformat()
def norm(c):return projection(c)
def snapshot(stats,items,day):
 out={str(i['cid'])+':'+str(i['nm']):dict(spend=0,amount=0,orders=0,clicks=0) for i in items}
 for c in stats:
  if c.get('currency')!='CNY':raise ValueError('Wrong statistics currency')
  for d in c.get('days',[]):
   if d['date'][:10]!=day:continue
   for app in d.get('apps',[]):
    for n in app.get('nms',[]):
     key=str(c['advertId'])+':'+str(n['nmId'])
     if key in out:
      for k,f in [('spend','sum'),('amount','sum_price'),('orders','orders'),('clicks','clicks')]:out[key][k]+=n.get(f,0)
 return out
def run(apply=False):
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 c=Cache();w=WB();validate_identity(c,w);a=c.get(ROOT+':approval') or {}
 if a.get('status')!='approved' or a.get('source')!='explicit_human_codex_message' or a.get('owner_id')!=5122667182:raise ValueError('Owner instruction missing')
 p=json.loads(a['plan_json']);h=hashlib.sha256(a['plan_json'].encode()).hexdigest()
 items=p['items'];ids=sorted({i['cid'] for i in items})
 if len(items)!=10 or len({i['nm'] for i in items})!=10 or p['percent']!=30 or p['cabinet']!='token_3' or p['budget_writes'] or datetime.now(timezone.utc)>=datetime.fromisoformat(p['expires_at']):raise ValueError('Exact scope invalid')
 for i in items:
  if not i['days'] or i['days'][-1]!='2026-10-26' or not 0<i['drr']<5 or i['expected_cny_at5']<=0 or i['target']!=round(i['old']*1.3) or i['target']<=i['old']:raise ValueError('Candidate evidence or target invalid')
 if not apply:
  if c.get(ROOT+':preflight'):print('Preflight already saved; no repeat');return
  cs=w.campaigns(ids)
  stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-27&endDate=2026-10-27')
  if {x['advertId'] for x in stats}!=set(ids):raise ValueError('Missing campaign statistics')
  metrics=snapshot(stats,items,p['day']);io=IO()
  prices=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
  if len(prices)>=1000:raise ValueError('Prices truncated')
  prices={x['nmID']:x for x in prices}
  headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN']};base='https://api.moysklad.ru/api/remap/1.2'
  r=requests.get(base+'/entity/store',headers=headers,params={'limit':1000},timeout=45)
  if not r.ok:raise RuntimeError('Stock store unavailable')
  stores=[s for s in r.json().get('rows',[]) if s.get('name')=='МСК' and not s.get('archived')]
  if len(stores)!=1:raise ValueError('Ambiguous MSK stock')
  r=requests.get(base+'/report/stock/all',headers=headers,params={'filter':'store='+stores[0]['meta']['href'],'stockMode':'all','limit':1000},timeout=55)
  if not r.ok:raise RuntimeError('MSK stock unavailable')
  stock=r.json()
  if stock.get('meta',{}).get('size',0)>len(stock.get('rows',[])):raise ValueError('Stock truncated')
  r=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':w.token},timeout=45)
  if not r.ok:raise RuntimeError('Bid config unavailable')
  cfg=r.json()
  if cfg.get('currency')!='CNY' or cfg.get('cpcStep')!=1:raise ValueError('Unexpected bid step/currency')
  mins={}
  for cid in ids:
   for zone in ['search','recommendations']:
    ns=[i['nm'] for i in items if i['cid']==cid and i['zone']==zone]
    if ns:mins.update({str(cid)+':'+str(n):v for n,v in w.minimums(cid,ns,zone).items()})
  checked=[];blocked=[]
  for i in items:
   try:
    before=cs[str(i['cid'])];n=next((n for n in before['nm_settings'] if n['nm_id']==i['nm']),{})
    if before['status']!=9 or before['currency']!='CNY' or before['bid_type']!='manual' or before['settings']['payment_type']!='cpc' or not before['settings']['placements'].get(i['zone']) or n.get('bids_kopecks',{}).get(i['zone'])!=i['old']:raise ValueError('Current member/bid/placement changed')
    if not mins[str(i['cid'])+':'+str(i['nm'])]<=i['target']<=cfg['cpcMaxBid']:raise ValueError('Bid outside current WB minimum/maximum')
    pr=prices.get(i['nm'],{});st=[s for s in stock['rows'] if s.get('article','').casefold()==i['article'].casefold()]
    if pr.get('vendorCode')!=i['article'] or pr.get('currencyIsoCode4217')!='CNY' or pr.get('sizes',[{}])[0].get('discountedPrice')!=i['price']:raise ValueError('Seller price changed; recalculate economics')
    if len(st)!=1 or st[0].get('stock') is None or st[0].get('reserve') is None or st[0]['stock']-st[0]['reserve']<=0 or abs(st[0].get('price',0)-i['cogs'])>.01:raise ValueError('Stock/COGS changed')
    v=metrics[str(i['cid'])+':'+str(i['nm'])]
    if v['amount'] and v['spend']/v['amount']>.05:raise ValueError('Today DRR above5')
    if not v['amount'] and v['spend']>=i['price']*.05:raise ValueError('Today no orders and material expense')
    checked.append(dict(item=i,current=v,minimum=mins[str(i['cid'])+':'+str(i['nm'])],available=st[0]['stock']-st[0]['reserve']))
   except ValueError as ex:blocked.append(dict(article=i['article'],reason=str(ex)))
  out=dict(status='ready' if len(checked)==10 else 'blocked',plan_sha256=h,observed_at=stamp(),campaigns=cs,fullstats=stats,checked=checked,blocked=blocked,wb_writes=0)
  if not c.create(ROOT+':preflight',out):raise ValueError('Concurrent preflight')
  print(json.dumps(dict(status=out['status'],checked=len(checked),blocked=blocked)));return
 f=c.get(ROOT+':preflight') or {}
 if f.get('status')!='ready' or f.get('plan_sha256')!=h or a.get('reviewed_preflight')!=f.get('observed_at') or (datetime.now(timezone.utc)-datetime.fromisoformat(f['observed_at'])).total_seconds()>1200:raise ValueError('Reviewed fresh preflight missing')
 key=ROOT+':execution'
 if c.get(key):print('Existing execution; no repeat writes');return
 current=w.campaigns(ids)
 if any(norm(current[str(cid)])!=norm(f['campaigns'][str(cid)]) for cid in ids):raise ValueError('Campaign changed after preflight')
 body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm'],bid_kopecks=i['target'],placement=i['zone']) for i in items if i['cid']==cid]) for cid in ids])
 e=dict(status='submitting',plan_sha256=h,items=items,before=current,baseline=f['fullstats'],request=body,started_at=stamp(),wb_writes=0,budget_writes=0,telegram_sends=0)
 if not c.create(key,e):raise ValueError('Concurrent execution')
 try:
  # The only marketplace write in this worker. No retry after crossing this boundary.
  result=w.req('/api/advert/v1/bids','PATCH',body,write=True)
  e.update(status='accepted',response=result,wb_writes=1);c.put(key,e)
  expected=copy.deepcopy(current)
  for i in items:next(n for n in expected[str(i['cid'])]['nm_settings'] if n['nm_id']==i['nm'])['bids_kopecks'][i['zone']]=i['target']
  for attempt in range(3):
   after=w.campaigns(ids);e['after']=after
   if all(norm(after[str(cid)])==norm(expected[str(cid)]) for cid in ids):break
   if attempt<2:time.sleep(3)
  else:raise RuntimeError('Exact ten-bid readback not confirmed')
  e.update(status='verified',verified_at=stamp());c.put(key,e)
  registry=c.get('china_agent:verified_campaign_state:v1') or {}
  for cid in ids:
   child=ROOT+':'+str(cid)+':execution'
   c.put(child,dict(status='verified',before=current[str(cid)],after=after[str(cid)],items=[i for i in items if i['cid']==cid],verified_at=e['verified_at'],parent=key))
   registry[str(cid)]=child
  c.put('china_agent:verified_campaign_state:v1',registry)
 except Exception as ex:
  e.update(status='uncertain',reason=str(ex) if isinstance(ex,(RuntimeError,ValueError)) else type(ex).__name__,completed_at=stamp());c.put(key,e);raise RuntimeError('Outcome uncertain; no write retry') from None
 # Separate deduplicated notification. A send failure never causes a bid-write retry.
 note=ROOT+':telegram'
 text='Ставки изменены, проверено WB:\n'+'\n'.join(i['article']+': '+format(i['old']/100,'.2f')+' → '+format(i['target']/100,'.2f')+' ¥' for i in items)+'\nОкруглено к шагу WB 0,01 ¥; фактический рост 27–30%.'
 if c.create(note,dict(status='sending',text=text,execution_key=key)):
  try:
   io=IO();me=io.tg('getMe',{})
   if me.get('id')!=8780468043:raise ValueError('Bot identity mismatch')
   r=io.tg('sendMessage',dict(chat_id=-1004342917488,text=text,reply_parameters=dict(message_id=327,allow_sending_without_reply=False),link_preview_options=dict(is_disabled=True)))
   if r.get('chat',{}).get('id')!=-1004342917488 or r.get('from',{}).get('id')!=8780468043:raise ValueError('Telegram receipt mismatch')
   c.put(note,dict(status='sent',text=text,message_id=r['message_id'],receipt=r,completed_at=stamp(),execution_key=key))
  except Exception:c.put(note,dict(status='uncertain',text=text,execution_key=key))
 print(json.dumps(dict(status=e['status'],verified_items=len(items),wb_writes=e['wb_writes'],budget_writes=0)))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');run(parser.parse_args().apply)
