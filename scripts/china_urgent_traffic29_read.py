"""Owner29Oct urgent traffic/order diagnosis. Read-only WB/MS, no messages."""
import os,json,time,requests
from datetime import datetime,timezone,timedelta
from collections import Counter
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
DAY='2026-10-29';ROOT='china_agent:urgent_traffic:'+DAY+':v1';MSK=timezone(timedelta(hours=3))
FIELDS={'spend':'sum','amount':'sum_price','orders':'orders','clicks':'clicks','views':'views','baskets':'atbs'}
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write or method!='GET' and not(method=='POST' and path=='/api/advert/v2/budget'):raise ValueError('Read-only advertising')
  return super().req(path,method,body,write=False)
def save(c,key,p):c.put(key,json.loads(json.dumps(p,allow_nan=False)))
def metric(d):return {k:d.get(v) for k,v in FIELDS.items()}
def main():
 assert os.environ.get('GITHUB_REPOSITORY')=='Ekaterina11098/veschi-bot-runner' and os.environ.get('GITHUB_REF')=='refs/heads/main'
 assert datetime.now(MSK).date().isoformat()==DAY
 c=Cache();w=ReadWB();validate_identity(c,w)
 if c.get(ROOT):print('Existing diagnosis; no repeated collection');return
 cut=datetime.now(MSK);out=dict(status='collecting',cutoff_msk=cut.isoformat(),started_at=stamp(),wb_writes=0,telegram_sends=0,errors=[])
 if not c.create(ROOT,out):raise ValueError('Concurrent diagnosis')
 def get(url,params=None,body=None):
  r=requests.get(url,params=params,headers={'Authorization':w.token},timeout=70) if body is None else requests.post(url,json=body,headers={'Authorization':w.token},timeout=70)
  if not r.ok:raise RuntimeError('Read HTTP '+str(r.status_code))
  return r.json()
 # Created FBS orders, same definition and same Moscow clock for all days.
 try:
  rows={};nxt=0;seen=set();raw_count=0
  for _ in range(30):
   j=get('https://marketplace-api.wildberries.ru/api/v3/orders',dict(limit=1000,next=nxt,dateFrom=int(datetime(2026,10,22,tzinfo=MSK).timestamp()),dateTo=int(cut.timestamp())))
   part=j.get('orders')
   if not isinstance(part,list):raise ValueError('Orders shape')
   raw_count+=len(part)
   for r in part:
    if not r.get('id') or not r.get('createdAt') or not r.get('nmId'):raise ValueError('Order identity missing')
    rows[r['id']]={k:r[k] for k in ['id','createdAt','nmId','article','rid','price','convertedPrice','currencyCode','convertedCurrencyCode'] if k in r}
   if not part:break
   new=j.get('next')
   if not isinstance(new,int) or new==nxt or new in seen:raise ValueError('Order pagination incomplete')
   seen.add(nxt);nxt=new;time.sleep(.5)
  else:raise ValueError('Order page bound')
  rows=list(rows.values())
  for pos in range(0,len(rows),500):save(c,ROOT+':orders:'+str(pos//500),dict(observed_at=stamp(),rows=rows[pos:pos+500]))
  totals=[]
  for n in range(8):
   day=(datetime(2026,10,22)+timedelta(days=n)).date().isoformat();full=[];same=[]
   for row in rows:
    at=datetime.fromisoformat(row['createdAt'].replace('Z','+00:00')).astimezone(MSK)
    if at.date().isoformat()!=day:continue
    full.append(row)
    if at.strftime('%H:%M:%S')<=cut.strftime('%H:%M:%S'):same.append(row)
   totals.append(dict(day=day,full_created=len(full),same_clock_created=len(same),same_clock_by_nm=dict(Counter(str(x['nmId']) for x in same)),same_clock_cny_buyer_amount=sum(x['convertedPrice']/100 for x in same if x.get('convertedCurrencyCode')==156)))
  out['orders']=dict(complete=True,unique_count=len(rows),raw_count=raw_count,pages=(len(rows)+499)//500,days=totals,basis='created FBS orders including later cancellations; buyer convertedPrice is not seller revenue')
  save(c,ROOT,out)
 except Exception as ex:out['errors'].append(dict(stage='orders',error=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__))
 # Current advertising state, budget and daily history. No same-hour view comparison inferred.
 try:
  inv=w.req('/adv/v1/promotion/count');ids=sorted({x['advertId'] for g in inv.get('adverts',[]) for x in g.get('advert_list',[])})
  save(c,ROOT+':inventory',dict(observed_at=stamp(),data=inv))
  campaigns={};budgets=[];stats=[]
  for pos in range(0,len(ids),50):
   group=ids[pos:pos+50];campaigns.update(w.campaigns(group))
   budgets+=w.req('/api/advert/v2/budget','POST',dict(advertIds=group)).get('adverts',[])
   stats+=w.req('/adv/v3/fullstats?ids='+','.join(map(str,group))+'&beginDate=2026-10-22&endDate='+DAY)
  if any(x.get('currency')!='CNY' for x in budgets) or any(x.get('currency')!='CNY' for x in campaigns.values()):raise ValueError('Advertising currency')
  save(c,ROOT+':campaigns',dict(observed_at=stamp(),campaigns=campaigns,budgets=budgets))
  summaries=[]
  for st in stats:
   raw_keys=sorted({k for d in st.get('days',[]) for k in d})
   days=[]
   for d in st.get('days',[]):
    nm={}
    for app in d.get('apps',[]):
     for x in app.get('nms',[]):
      row=nm.setdefault(str(x['nmId']),{k:0 for k in FIELDS})
      for k,field in FIELDS.items():
       if x.get(field) is None:raise ValueError('Unknown SKU metric')
       row[k]+=x[field]
    days.append(dict(day=d['date'][:10],total=metric(d),nms=nm))
   item=dict(id=st['advertId'],days=days,raw_day_keys=raw_keys)
   save(c,ROOT+':stats:'+str(st['advertId']),dict(observed_at=stamp(),data=item))
   summaries.append(dict(id=st['advertId'],days=[dict(day=d['day'],**d['total']) for d in days]))
  out['advertising']=dict(ids=ids,stats_ids=[x['advertId'] for x in stats],missing_ids=[x for x in ids if x not in {s['advertId'] for s in stats}],daily=summaries,same_clock_impressions_available=False);save(c,ROOT,out)
 except Exception as ex:out['errors'].append(dict(stage='advertising',error=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__))
 try:
  data=get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',dict(limit=1000,offset=0)).get('data',{})
  if len(data.get('listGoods',[]))>=1000:raise ValueError('Price pagination')
  save(c,ROOT+':prices',dict(observed_at=stamp(),rows=data.get('listGoods',[])))
 except Exception as ex:out['errors'].append(dict(stage='prices',error=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__))
 # Stock reads are explicit read-only POST requests; absence is not zero.
 try:
  mapping=(c.get(ROOT+':catalog') or {}).get('rows',[])
  nms={int(x['nm_id']):x for x in mapping}
  fallback=(c.get('china_agent:new_ad_source:v1:2026-10-28') or {}).get('products',[])
  for r in fallback:
   if int(r['nm_id']) not in nms and r.get('barcode'):nms[int(r['nm_id'])]=dict(nm_id=r['nm_id'],article=r['sa_name'],sizes=[dict(skus=[str(r['barcode'])])],source='dated MPStats barcode mapping28Oct')
  warehouses=get('https://marketplace-api.wildberries.ru/api/v3/warehouses')
  wh=[x for x in warehouses if not x.get('isDeleting') and x.get('id')]
  skus=sorted({str(b) for r in nms.values() for s in r.get('sizes',[]) for b in s.get('skus',[])})
  stock=[]
  for whrow in wh:
   for pos in range(0,len(skus),1000):
    data=get('https://marketplace-api.wildberries.ru/api/v3/stocks/'+str(whrow['id']),body={'skus':skus[pos:pos+1000]})
    if not isinstance(data.get('stocks'),list):raise ValueError('Stock shape')
    stock.extend(dict(warehouse_id=whrow['id'],warehouse_name=whrow.get('name'),**r) for r in data['stocks'])
    time.sleep(.5)
  save(c,ROOT+':wb_stocks',dict(observed_at=stamp(),mapping=list(nms.values()),rows=stock,warehouses=[{k:x.get(k) for k in ['id','name','officeId','isDeleting']} for x in wh],requested_skus=len(skus)))
 except Exception as ex:out['errors'].append(dict(stage='wb_stocks',error=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__))
 try:
  h={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'};base='https://api.moysklad.ru/api/remap/1.2'
  def ms(path,params):
   r=requests.get(base+path,headers=h,params=params,timeout=60)
   if not r.ok:raise RuntimeError('MS read HTTP '+str(r.status_code))
   return r.json()
  stores=ms('/entity/store',dict(limit=1000));found=[x for x in stores['rows'] if x.get('name')=='МСК' and not x.get('archived')]
  if len(found)!=1:raise ValueError('MSK warehouse ambiguous')
  articles={r['vendorCode'] for r in (c.get('china_agent:prices:v1') or {})['rows']};rows=[];offset=0
  for _ in range(15):
   j=ms('/report/stock/all',dict(filter='store='+found[0]['meta']['href']+';stockMode=all;quantityMode=all',limit=1000,offset=offset))
   part=j.get('rows');size=j.get('meta',{}).get('size')
   if not isinstance(part,list) or type(size)is not int:raise ValueError('MSK coverage')
   rows.extend({k:r.get(k) for k in ['article','stock','reserve','price']} for r in part if r.get('article') in articles)
   offset+=len(part)
   if offset>=size:break
   if not part:raise ValueError('MSK pagination')
  else:raise ValueError('MSK page bound')
  save(c,ROOT+':msk',dict(observed_at=stamp(),rows=rows,warehouse='МСК',complete=True,raw_count=offset))
 except Exception as ex:out['errors'].append(dict(stage='msk',error=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__))
 out.update(status='complete' if not out['errors'] else 'partial',completed_at=stamp());save(c,ROOT,out)
 print(json.dumps(dict(status=out['status'],errors=out['errors'],wb_writes=0,telegram_sends=0)))
if __name__=='__main__':main()
