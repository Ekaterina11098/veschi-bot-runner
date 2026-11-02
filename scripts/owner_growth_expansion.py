"""Owner read-only growth review, completed days only. No sends or marketplace mutations."""
import os,json,requests
from datetime import datetime,date,timezone
from china_advertising_state import AdvertisingIO
from china_advertising_v2 import http,history,read_price_experience
from china_analytic_dialog import Analyst,reading
from china_advertising_economic_review import model_rows
ROOT='china_agent:owner_growth_expansion:2026-11-02:v1'
IDS=[1473243916,1473243906,1473243913,1473243891,1535337772,1473245502,1560230898,1560345283,1473244992]
class IO(AdvertisingIO):
 def wb(self,*a,**k):raise RuntimeError('No WB mutation capability')
io=IO()
def main():
 if io.get(ROOT):print('Existing immutable review; no repeated reads');return
 source=io.get('china_agent:advertising_source:2026-11-02:v2')
 if source['cabinet']!='token_3' or source['period_to']!='2026-11-01' or 1473243903 in IDS:raise RuntimeError('Scope mismatch')
 class W:
  now=datetime.now(timezone.utc)
  def get(self,k):return io.get(k)
  def save(self,k,v,**kw):raise RuntimeError('Unexpected shared save')
  def catalog(self):return [(str(r['nmID']),r['vendorCode'])for r in source['catalogue']['rows']]
 an=Analyst(W(),dict(request_text='Проверить другие артикулы на повышение и добавление'),[])
 with reading():stock=an.collect('stock',IDS,date(2026,10,3),date(2026,11,1))
 stock['observed_at']=datetime.now(timezone.utc).isoformat()
 rr=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params=dict(limit=1000,offset=0),headers={'Authorization':io.token},timeout=50)
 if not rr.ok:raise RuntimeError('Prices HTTP '+str(rr.status_code))
 goods=rr.json()['data']['listGoods']
 if len(goods)>=1000:raise RuntimeError('Price pagination incomplete')
 goods=[g for g in goods if g['nmID'] in IDS]
 if {g['nmID']for g in goods}!=set(IDS) or any(g['currencyIsoCode4217']!='CNY'for g in goods):raise RuntimeError('Candidate price identity mismatch')
 prices=dict(rows=[dict(nm_id=g['nmID'],article=g['vendorCode'],seller_price=g['sizes'][0]['discountedPrice'])for g in goods],observed_at=datetime.now(timezone.utc).isoformat())
 if any(len({z['discountedPrice']for z in g['sizes']})!=1 for g in goods):raise RuntimeError('Ambiguous candidate price')
 size_nm={z['sizeID']:g['nmID']for g in goods for z in g['sizes']}
 rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',json=dict(chrtIds=list(size_nm)),headers={'Authorization':io.token},timeout=50)
 if not rr.ok:raise RuntimeError('Published stock HTTP '+str(rr.status_code))
 pub=rr.json()['stocks']
 if {r['chrtId']for r in pub}!=set(size_nm):raise RuntimeError('Published stock coverage incomplete')
 campaigns=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,source['ids'])))['adverts']
 targets={}
 quotes={};errors={}
 for c in campaigns:
  if c['status']!=9 or c['settings']['payment_type']!='cpc':continue
  ids=sorted({n['nm_id']for n in c['nm_settings']if n['nm_id']in IDS}|{n for n,cid in targets.items()if cid==c['id']})
  if not ids:continue
  zone='search'if c['settings']['placements'].get('search')else'recommendation'
  try:quotes[str(c['id'])]=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=c['id'],nm_ids=ids,payment_type='cpc',placement_types=[zone]))
  except Exception as ex:errors[str(c['id'])]=type(ex).__name__+':'+str(ex)
 products=io.get('china_agent:analytic_read:v1:893557e46ce1918d55ff958ce88fd1f202ee06e10e60792aeabbbb67cd857b35')
 economics=model_rows(dict(products=products,prices=prices,stock=stock,fx=io.get('china_agent:cbr_cny:v1:2026-11-01')),io.get('china_agent:new_ad_economics_policy:v1')or{},io.get('china_agent:expected_profit_delivery_model:v1')or{})
 events=[e for e in history(source['executions'])if e.get('nm')in IDS]
 active=[dict(c,nm_settings=[n for n in c['nm_settings']if n['nm_id']in IDS])for c in campaigns if any(n['nm_id']in IDS for n in c['nm_settings'])]
 own=[r for r in products['rows']if r['nm_id']in IDS]
 result=dict(status='complete',cabinet='token_3',observed_at=datetime.now(timezone.utc).isoformat(),period_to='2026-11-01',prices=prices,stock=stock,published_stock=[dict(nm_id=n,amount=sum(v['amount']for v in pub if size_nm[v['chrtId']]==n))for n in IDS],economics=economics,events=events,campaigns=active,quotes=quotes,quote_errors=errors,products=own,wb_writes=0,telegram_calls=0,grants_action_permission=False)
 if not io.create(ROOT,result):raise RuntimeError('Concurrent immutable growth review')
 if io.get(ROOT)!=result:raise RuntimeError('Growth review readback mismatch')
 print(json.dumps(dict(status='complete',economic_missing=economics['missing'],quote_errors=errors,wb_writes=0)))


def isolated_quotes():
 key=ROOT+':quotes2'
 if io.get(key):return
 import time
 result=dict(observed_at=datetime.now(timezone.utc).isoformat(),quotes={},errors={},wb_writes=0)
 for nm in [1473245505,1473243909]:
  time.sleep(3)
  r=requests.post('https://advert-api.wildberries.ru/api/advert/v1/bids/min',json=dict(advert_id=40933588,nm_ids=[nm],payment_type='cpc',placement_types=['recommendation']),headers={'Authorization':io.token},timeout=45)
  if r.ok:result['quotes'][str(nm)]=r.json()
  else:
   try:body=r.json()
   except Exception:body={}
   result['errors'][str(nm)]=dict(status=r.status_code,error=body.get('detail')or body.get('title')or body.get('message')or body.get('error')or body.get('errors'))
 if not io.create(key,result):raise RuntimeError('Concurrent quote inputs')
 if io.get(key)!=result:raise RuntimeError('Quotes readback mismatch')
 print('Isolated read-only bid quotes saved')

def rating():
 key=ROOT+':rating584'
 if io.get(key):return
 from china_hourly_sales_read import collect_funnel,Cache
 from zoneinfo import ZoneInfo
 cut=datetime.now(ZoneInfo('Europe/Moscow')).replace(minute=0,second=0,microsecond=0)
 result=collect_funnel(Cache(),cut,[1473245505])
 if not io.create(key,result):raise RuntimeError('Concurrent rating input')
 if io.get(key)!=result:raise RuntimeError('Rating readback mismatch')
 print('Targeted WB product rating source saved')
if __name__=='__main__':
 main()
