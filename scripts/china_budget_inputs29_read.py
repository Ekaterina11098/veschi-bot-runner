"""Owner-requested budget inputs29Oct. Reads only; private cache; no Telegram."""
import os,json,requests
from datetime import datetime,timezone,timedelta
from china_advertising_state import AdvertisingIO
from china_advertising_v2 import http,stamp
KEY='china_agent:budget_inputs:2026-10-29:v2'
IDS=[40933588,41055480,41270309,41298169,41325637,41332083]
class ReadIO(AdvertisingIO):
 def wb(self,path,method='GET',body=None):
  if method!='GET' or not path.startswith('/api/v2/list/goods/filter?'):raise ValueError('Price reads only')
  return super().wb(path,method,body)
 def tg(self,*args,**kwargs):raise ValueError('No Telegram calls')
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()=='2026-10-29'
 io=ReadIO();state=io.get(KEY) or dict(status='collecting',observed_at=stamp(),wb_writes=0,telegram_sends=0)
 if state.get('status')=='complete':print('Existing complete snapshot; no repeat reads');return
 if io.get(KEY) is None and not io.create(KEY,state):raise ValueError('Concurrent collection')
 if io.get(KEY+':campaigns') is None:
  data=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,IDS)))
  rows=data.get('adverts',[])
  if {c['id'] for c in rows}!=set(IDS) or any(c.get('currency')!='CNY' for c in rows):raise ValueError('Campaign identities/currency incomplete')
  io.create(KEY+':campaigns',dict(observed_at=stamp(),rows=rows))
 campaigns=io.get(KEY+':campaigns')['rows'];catalog=io.get('china_agent:prices:v1') or {};assert catalog.get('cabinet')=='token_3'
 nms=sorted({int(p['nmID']) for p in catalog['rows']})
 if io.get(KEY+':budgets') is None:io.create(KEY+':budgets',dict(observed_at=stamp(),data=http(io,'/api/advert/v2/budget','POST',dict(advertIds=IDS))))
 if io.get(KEY+':prices') is None:
  prices=io.prices(nms)
  if any(p.get('currencyIsoCode4217')!='CNY' for p in prices.values()):raise ValueError('Wrong price currency')
  io.create(KEY+':prices',dict(observed_at=stamp(),rows=list(prices.values())))
 articles={p['vendorCode'] for p in io.get(KEY+':prices')['rows']}
 if io.get(KEY+':stock') is None:
  headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'}
  def get(path,params):
   response=requests.get('https://api.moysklad.ru/api/remap/1.2'+path,params=params,headers=headers,timeout=60)
   if not response.ok:raise RuntimeError('MoySklad read HTTP '+str(response.status_code))
   return response.json()
  stores=get('/entity/store',dict(limit=1000))
  if stores.get('meta',{}).get('size',1001)>len(stores.get('rows',[])):raise ValueError('Warehouse coverage')
  selected=[r for r in stores['rows'] if r.get('name')=='МСК' and not r.get('archived')]
  if len(selected)!=1:raise ValueError('MSK warehouse ambiguous')
  rows=[];offset=0
  while True:
   data=get('/report/stock/all',dict(filter='store='+selected[0]['meta']['href']+';stockMode=all;quantityMode=all',limit=1000,offset=offset))
   part=data.get('rows');size=data.get('meta',{}).get('size')
   if not isinstance(part,list) or type(size)is not int:raise ValueError('Stock coverage unknown')
   rows.extend({k:r.get(k) for k in ['article','price','stock','reserve']} for r in part if r.get('article') in articles)
   offset+=len(part)
   if offset>=size:break
   if not part or offset>50000:raise ValueError('Stock pagination incomplete')
  io.create(KEY+':stock',dict(observed_at=stamp(),warehouse='МСК',complete=True,raw_count=offset,rows=rows))
 state.update(status='complete',completed_at=stamp());io.put(KEY,state)
 print('Budget input snapshot saved privately; WB writes0; Telegram sends0')
if __name__=='__main__':main()
