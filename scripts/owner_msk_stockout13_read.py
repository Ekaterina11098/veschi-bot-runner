"""Owner-requested MSK-only stockout/order audit; no marketplace writes or sends."""
import json,os,time
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_moysklad_read import Reader,BASE
from moysklad_warehouses import select_store
from china_hourly_sales_read import read_orders,select_rows
ROOT='china_agent:owner_msk_stockout:2026-11-13:v1'
MSK=ZoneInfo('Europe/Moscow')
GZ={2128711871,2128836687,2128836688,2128972258,2128990207,2129004929,2129199357,2129199358,2129199359,2129199360,2129199361,2129309882,2129309883,2129309884,2129309885,2129309886,2129309887,2129309888}
def main():
 c=Cache()
 if (c.get(ROOT)or{}).get('status')=='complete':return
 validate_identity(c,WB())
 source=c.get('china_agent:advertising_full_growth:2026-11-13:v1:inputs:midday')or{}
 catalog=[r for r in source.get('catalogue',{}).get('rows',[])if r['nmID']not in GZ]
 if len(catalog)<300 or len(catalog)>500:raise ValueError('Catalogue coverage')
 bynm={r['nmID']:r for r in catalog};articles={r['vendorCode']for r in catalog};mapping={s['sizeID']:r['nmID']for r in catalog for s in r['sizes']}
 result=c.get(ROOT)or dict(status='reading',cabinet='token_3',warehouse_role='msk',created_at=stamp(),inputs={},errors={},wb_writes=0,telegram_calls=0,model_calls=0,grants_action_permission=False)
 def save():
  v=json.loads(json.dumps(result))
  if c.get(ROOT):c.put(ROOT,v)
  else:c.create(ROOT,v)
 def stage(name,fn):
  if name in result['inputs']:return
  try:result['inputs'][name]=fn()
  except Exception as ex:result['errors'][name]=str(ex)[:220]if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__
  save()
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  u=urlparse(url);m=method.upper()
  private=url.startswith(c.url)and u.path.endswith('/telegram_api_cache')and m in ['GET','POST','PATCH']
  ms=m=='GET'and u.hostname=='api.moysklad.ru'and u.path in ['/api/remap/1.2/entity/store','/api/remap/1.2/report/stock/all']
  wb=u.hostname=='marketplace-api.wildberries.ru'and ((m=='GET'and u.path=='/api/v3/orders')or(m=='POST'and u.path=='/api/v3/stocks/2126188'and kw.get('json')=={'chrtIds':sorted(mapping)}))
  if not(private or ms or wb):raise ValueError('Read-only exact MSK audit guard')
  return original(session,method,url,**kw)
 requests.sessions.Session.request=guard
 def msk():
  reader=Reader();store=select_store(reader.pages('/entity/store',{}),'msk');rows=[];offset=0;expected=None
  for page in range(15):
   body=reader.get('/report/stock/all',dict(filter='store='+store['meta']['href']+';stockMode=all;quantityMode=all',limit=1000,offset=offset));part=body.get('rows');size=body.get('meta',{}).get('size')
   if not isinstance(part,list)or type(size)is not int or(expected is not None and expected!=size):raise ValueError('MSK pagination coverage')
   expected=size;rows.extend(r for r in part if r.get('article')in articles);offset+=len(part)
   if offset==size:break
   if not part or offset>size:raise ValueError('MSK pagination incomplete')
  else:raise ValueError('MSK page bound')
  counts={a:sum(1 for r in rows if r.get('article')==a)for a in articles}
  return dict(observed_at=stamp(),warehouse_id=store['id'],rows=[{k:r.get(k)for k in ['article','stock','reserve','inTransit','quantity','price']}for r in rows],missing_articles=[a for a,n in counts.items()if n==0],ambiguous_articles=[a for a,n in counts.items()if n>1],report_rows_scanned=expected,catalogue_count=len(catalog),coverage_complete=all(n==1 for n in counts.values()))
 def published():
  r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':os.environ['WB_TOKEN_3']},json={'chrtIds':sorted(mapping)},timeout=50)
  if not r.ok:raise ValueError('Published MSK HTTP '+str(r.status_code))
  rows=r.json().get('stocks')
  if not isinstance(rows,list):raise ValueError('Published MSK response')
  seen=set();amounts={}
  for r in rows:
   z=r['chrtId']
   if z not in mapping or z in seen or type(r.get('amount'))is not int:raise ValueError('Published MSK identity')
   seen.add(z);nm=mapping[z];amounts[nm]=amounts.get(nm,0)+r['amount']
  missing={mapping[z]for z in mapping if z not in seen}
  for n in missing:amounts.pop(n,None)
  return dict(observed_at=stamp(),warehouse_id=2126188,amounts=amounts,missing_nm_ids=sorted(missing))
 def orders():
  first=datetime(2026,10,16,tzinfo=MSK);end=datetime(2026,11,13,tzinfo=MSK);recent=end-timedelta(days=7)
  def get(path,params):
   r=requests.get('https://marketplace-api.wildberries.ru'+path,params=params,headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=50)
   if not r.ok:raise ValueError('FBS orders HTTP '+str(r.status_code))
   return r.json()
  raw=read_orders(get,first,end);allrows=select_rows(raw.values(),first,end);rows={};unknown=[]
  for r in allrows:
   nm=r['nmId']
   if nm not in bynm:continue
   if r['convertedCurrencyCode']!=156 or type(r['convertedPrice'])not in(int,float):unknown.append(nm);continue
   at=datetime.fromisoformat(r['createdAt'].replace('Z','+00:00')).astimezone(MSK);day=at.date().isoformat();a=r['convertedPrice']/100
   z=rows.setdefault(nm,dict(nm_id=nm,article=bynm[nm]['vendorCode'],count=0,amount_cny=0,recent7_count=0,recent7_amount_cny=0,daily={},last_order_msk=None))
   z['count']+=1;z['amount_cny']+=a;z['last_order_msk']=max(z['last_order_msk']or'',at.isoformat())
   d=z['daily'].setdefault(day,dict(count=0,amount_cny=0));d['count']+=1;d['amount_cny']+=a
   if at>=recent:z['recent7_count']+=1;z['recent7_amount_cny']+=a
  if unknown:raise ValueError('Unknown currency/amount in target orders')
  return dict(observed_at=stamp(),period_from=str(first.date()),period_to='2026-11-12',recent7_from='2026-11-06',source='WB FBS created,all statuses,id dedup; buyer-discounted CNY,not buyouts/profit/wholecabinet',rows=list(rows.values()),all_fbs_records=len(allrows),coverage_complete=True)
 try:
  stage('msk',msk);stage('published',published);stage('orders',orders)
 finally:requests.sessions.Session.request=original
 result.update(status='complete'if not result['errors']else'partial',completed_at=stamp());save()
 print(json.dumps(dict(status=result['status'],errors=result['errors'],wb_writes=0,telegram_calls=0)))
if __name__=='__main__':main()

