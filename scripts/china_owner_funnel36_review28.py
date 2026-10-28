"""Owner requested per-SKU diagnostic. Bounded reads only; no marketplace or Telegram writes."""
import os,json,time,copy,requests
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_bid_proposals import fresh_stock,sources
KEY='china_agent:owner_funnel36_review:2026-10-28:v1'
CIDS=[41296359,41155824]
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if method!='GET' or write:raise ValueError('Read only')
  return super().req(path,method,body,False)
class History:
 def __init__(self,c):self.c=c;self.now=datetime.now(timezone.utc)
 def get(self,k):return self.c.get(k)
 def db(self,method,table,params=None,**kw):
  if method!='GET' or table!='telegram_api_cache':raise ValueError('Read only')
  return self.c.req('GET',params)
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()!='2026-10-28':raise ValueError('Dated public main only')
 c=Cache()
 if c.get(KEY):print('Existing diagnostic; no repeat');return
 w=ReadWB();validate_identity(c,w)
 out=dict(status='collecting',started_at=stamp(),wb_writes=0,telegram_sends=0,model_calls=0,errors=[])
 if not c.create(KEY,out):return
 def save():out['observed_at']=stamp();c.put(KEY,copy.deepcopy(out))
 def stage(name,fn):
  try:out[name]=fn();out[name+'_at']=stamp()
  except Exception as e:out['errors'].append(dict(stage=name,error=str(e) if isinstance(e,ValueError) else type(e).__name__))
  save()
 def req(host,path,method='GET',body=None,params=None):
  allowed_post={('marketplace-api.wildberries.ru','/api/v3/stocks/2126188'),('content-api.wildberries.cn','/content/v2/get/cards/list')}
  if method!='GET' and (method!='POST' or (host,path) not in allowed_post):raise ValueError('Only documented read POSTs allowed')
  for attempt in range(2):
   try:r=requests.request(method,'https://'+host+path,headers={'Authorization':w.token},json=body,params=params,timeout=45);break
   except requests.exceptions.ConnectionError:
    if attempt:raise
    time.sleep(2)
  if not r.ok:raise ValueError('HTTP '+str(r.status_code)+' '+host+path)
  return r.json()
 stage('campaigns',lambda:w.campaigns(CIDS))
 if not out.get('campaigns'):out['status']='blocked';save();return
 ids={n['nm_id'] for cp in out['campaigns'].values() for n in cp['nm_settings']}
 src=c.get('china_agent:new_ad_source:v1:2026-10-28') or {}
 products={p['nm_id']:p for p in src.get('products',[]) if p['nm_id'] in ids}
 if len(ids)!=36 or len(products)!=36:out['status']='blocked_scope_changed';save();return
 out['identity']=[dict(nm_id=n,article=p['sa_name']) for n,p in products.items()];save()
 stage('stats',lambda:w.req('/adv/v3/fullstats?ids=41296359,41155824&beginDate=2026-10-25&endDate=2026-10-28'))
 stage('budgets',lambda:{str(cid):w.req('/adv/v1/budget?id='+str(cid)) for cid in CIDS})
 stage('minimums',lambda:{str(cid):w.minimums(cid,[n['nm_id'] for n in cp['nm_settings']],'recommendations') for cid,cp in out['campaigns'].items()})
 def prices():
  rows=req('discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter',params=dict(limit=1000,offset=0)).get('data',{}).get('listGoods',[])
  if len(rows)>=1000 or not rows:raise ValueError('Incomplete price pagination')
  selected=[p for p in rows if p['nmID'] in ids]
  if len(selected)!=len(ids):raise ValueError('Missing target prices')
  return selected
 stage('prices',prices)
 def wb_stock():
  sizes={s['sizeID']:p['nmID'] for p in out.get('prices',[]) for s in p.get('sizes',[])}
  if not sizes:raise ValueError('No size mapping')
  rows=req('marketplace-api.wildberries.ru','/api/v3/stocks/2126188','POST',{'chrtIds':list(sizes)}).get('stocks',[]);by={}
  for r in rows:by.setdefault(sizes[r['chrtId']],[]).append(r.get('amount'))
  return {str(n):sum(by[n]) if n in by and all(type(x)is int for x in by[n]) else None for n in ids}
 stage('wb_stock',wb_stock)
 def stock():
  for attempt in range(2):
   try:return fresh_stock({},[p['sa_name'] for p in products.values()])
   except requests.exceptions.ConnectionError:
    if attempt:raise
    time.sleep(2)
 stage('stock',stock)
 stage('changes',lambda:[v for v in sources(History(c))['changes'] if v.get('nm') in ids])
 def cards():
  result={};cursor={'limit':100};finished=False
  for page in range(8):
   r=req('content-api.wildberries.cn','/content/v2/get/cards/list','POST',{'settings':{'sort':{'ascending':True},'cursor':cursor,'filter':{'withPhoto':-1}}},params={'locale':'ru'})
   rows=r.get('cards',[])
   for x in rows:
    if x.get('nmID') in ids:result[str(x['nmID'])]={k:x.get(k) for k in ['nmID','imtID','vendorCode','title','description','subjectID','subjectName','brand','photos','video','dimensions','characteristics','updatedAt']}
   cur=r.get('cursor',{})
   if cur.get('total',len(rows))<100:finished=True;break
   if not cur.get('updatedAt') or not cur.get('nmID'):raise ValueError('Card cursor missing')
   cursor={'limit':100,'updatedAt':cur['updatedAt'],'nmID':cur['nmID']};time.sleep(1)
  return dict(rows=result,pagination_complete=finished,missing_nm_ids=sorted(ids-{int(n) for n in result}))
 stage('cards',cards)
 def orders():
  rows=req('statistics-api.wildberries.ru','/api/v1/supplier/orders',params={'dateFrom':'2026-10-25','flag':0})
  if not isinstance(rows,list) or len(rows)>=80000:raise ValueError('Orders truncated')
  counts={}
  for x in rows:
   if x.get('nmId') not in ids:continue
   day=(x.get('date') or '')[:10]
   if not '2026-10-25'<=day<='2026-10-28':continue
   k=str(x['nmId'])+':'+day;counts.setdefault(k,dict(total=0,cancelled=0,active=0));counts[k]['total']+=1;counts[k]['cancelled' if x.get('isCancel') else 'active']+=1
  return dict(counts=counts,raw_count=len(rows),complete=True,meaning='all-source placed orders, not buyouts or organic attribution')
 stage('orders',orders)
 out['status']='complete' if not out['errors'] else 'partial';save()
 print(json.dumps(dict(status=out['status'],errors=out['errors'],sku_count=len(ids),cards=len(out.get('cards',{}).get('rows',{})),wb_writes=0,telegram_sends=0,model_calls=0)))
if __name__=='__main__':main()
