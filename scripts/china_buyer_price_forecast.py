"""Conditional RUB forecast from saved MPStats buyer price; no exchange-rate guess."""
from datetime import datetime,timedelta
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
def positive(value):
 if isinstance(value,bool):raise ValueError('Boolean price')
 try:n=Decimal(str(value))
 except InvalidOperation:raise ValueError('Unknown price')
 if not n.is_finite() or n<=0:raise ValueError('Unknown price')
 return n

def build(rows,marker,catalogue,day):
 result=dict(report_date=str(day),status='unavailable',rows={},assumption='unchanged_WB_discounts_and_conversion',source='MPStats price_after_spp')
 try:
  observed=datetime.fromisoformat(marker['collected_at'].replace('Z','+00:00'))
  prices_at=datetime.fromisoformat(catalogue['observed_at'].replace('Z','+00:00'))
  if observed.tzinfo is None or prices_at.tzinfo is None:return result
  if observed.astimezone(MSK).date()!=day or prices_at.astimezone(MSK).date()!=day:return result
  yesterday=str(day-timedelta(days=1))
  if str(marker['period_from'])!=yesterday or str(marker['period_to'])!=yesterday or catalogue.get('cabinet')!='token_3':return result
 except (KeyError,TypeError,ValueError):return result
 result.update(status='available',snapshot_id=marker['id'],period_from=yesterday,period_to=yesterday,observed_at=marker['collected_at'],seller_observed_at=catalogue['observed_at'])
 by_nm={};catalogue_by_nm={}
 for row in rows:by_nm.setdefault(str(row.get('nm_id')),[]).append(row)
 for row in catalogue.get('rows',[]):catalogue_by_nm.setdefault(str(row.get('nmID')),[]).append(row)
 for nm,variants in by_nm.items():
  if len(variants)!=1 or len(catalogue_by_nm.get(nm,[]))!=1:continue
  raw=variants[0];seller=catalogue_by_nm[nm][0]
  try:
   if seller.get('currencyIsoCode4217')!='CNY' or raw['sa_name'].casefold()!=seller['vendorCode'].casefold():continue
   sizes=seller['sizes']
   values={positive(s['discountedPrice']) for s in sizes}
   if len(values)!=1:continue
   cny=values.pop()
   rub=positive(raw['price_after_spp'])
   if positive(raw['price_final'])!=rub:continue
   before_spp=positive(raw['price_after_discount'])
   spp=Decimal(str(raw['price_spp']))
   if not spp.is_finite() or not 0<=spp<100:continue
   if abs(before_spp*(1-spp/100)-rub)>2:continue
   result['rows'][nm]=dict(article=raw['sa_name'],current_cny=str(cny),buyer_rub=str(rub),spp_percent=str(spp))
  except (KeyError,TypeError,ValueError,InvalidOperation):continue
 return result

def forecast(basis,nm,article,current,target,day):
 try:
  if basis.get('report_date')!=str(day) or basis.get('status')!='available':return None
  row=basis['rows'][str(nm)]
  if row['article'].casefold()!=article.casefold() or positive(row['current_cny'])!=positive(str(current).replace(',','.')):return None
  amount=positive(row['buyer_rub'])*positive(str(target).replace(',','.'))/positive(row['current_cny'])
  return int(amount.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
 except (KeyError,TypeError,ValueError,InvalidOperation):return None

def load(worker):
 from analytics.mpstats_primary import products
 yesterday=str(worker.day-timedelta(days=1))
 read=lambda table,params:worker.db('GET',table,params=params)
 rows,marker=products(read,'token_3',yesterday,yesterday,worker.now)
 basis=build(rows,marker,worker.get('china_agent:prices:v1') or {},worker.day)
 return basis
