"""Bounded seller-price reads and reusable exact-SKU diagnostic inputs; no writes."""
import hashlib,json,math
from datetime import date,datetime,timedelta,timezone
from china_article_diagnostic import fresh,MSK

def read_prices(get,ids):
 ids=sorted(set(ids));rows={};url='https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter'
 if len(ids)>30:raise ValueError('At most30 exact price IDs')
 def add(part):
  if not isinstance(part,list):raise ValueError('WB price response incomplete')
  for r in part:
   nm=r.get('nmID')
   if type(nm)is not int or nm in rows:raise ValueError('Duplicate/unknown price ID')
   if ids and nm not in ids:raise ValueError('Wrong exact price ID')
   sizes=r.get('sizes') or [];prices={z.get('discountedPrice') for z in sizes}
   if r.get('currencyIsoCode4217')!='CNY' or len(prices)!=1:raise ValueError('Ambiguous price/currency; exact variant required')
   p=next(iter(prices))
   if type(p) not in (int,float) or not math.isfinite(p) or p<=0:raise ValueError('Seller price unknown')
   rows[nm]=dict(nm_id=nm,article=r.get('vendorCode'),currency='CNY',discount=r.get('discount'),seller_price=p,size_ids=[z.get('sizeID') for z in sizes])
 if ids:
  for nm in ids:
   part=get(url,{'limit':1000,'offset':0,'filterNmID':nm}).get('data',{}).get('listGoods')
   if not part or any(r.get('nmID')!=nm for r in part):raise ValueError('Exact WB seller price missing')
   add(part)
 else:
  for offset in range(0,20000,1000):
   part=get(url,{'limit':1000,'offset':offset}).get('data',{}).get('listGoods')
   add(part)
   if len(part)<1000:break
  else:raise ValueError('Price pagination exceeds bound')
 return dict(source='WB seller prices, exact IDs' if ids else 'WB seller prices, complete pages',rows=list(rows.values()),coverage_complete=True,note='Цена продавца CNY после его скидки; не цена покупателя/СПП и не прибыль.')

def scoped(analyst,topic,ids,first,last,ttl=900):
 """A fixed diagnostic budget is independent of model turns' three-read allowance."""
 from china_analytic_dialog import reading
 args=[topic,sorted(ids),str(first),str(last)]
 key='china_agent:article_inputs:v2:'+hashlib.sha256(json.dumps(args).encode()).hexdigest()
 value=analyst.w.get(key)
 if value and fresh(value,analyst.w.now,ttl):return value
 with reading():value=analyst.collect(topic,ids,date.fromisoformat(str(first)),date.fromisoformat(str(last)))
 value=dict(value,source_key=key,observed_at=datetime.now(timezone.utc).isoformat(),period_from=str(first),period_to=str(last),cabinet='token_3',wb_writes=0)
 analyst.w.save(key,value)
 return value
