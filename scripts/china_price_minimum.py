"""Required price/auto-promotion minimum parity. Pure preparation and verification; no WB API."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation,ROUND_FLOOR
POLICY='seller_discounted_floor_preserve_blocks_v1'
OWNER_DATE='2026-10-28'
def price(value):
 try:
  if isinstance(value,bool):raise ValueError()
  n=Decimal(str(value))
  if not n.is_finite() or n<=0:raise ValueError()
  return n
 except (ValueError,TypeError,InvalidOperation):raise ValueError('Нужна положительная текущая цена CNY')
def floor_price(value):return int(price(value).to_integral_value(rounding=ROUND_FLOOR))
def requirement(item):
 s=item.get('selection') or {};p=item.get('readback') or {};req=item.get('request') or {}
 if item.get('status')!='applied':return None
 sizes=p.get('sizes') or []
 if (str(p.get('nmID'))!=str(s.get('nm_id')) or p.get('vendorCode')!=s.get('article') or
     p.get('currencyIsoCode4217')!='CNY' or p.get('editableSizePrice') is not False or
     p.get('discount')!=req.get('discount') or p.get('clubDiscount')!=s.get('club_discount') or not sizes):
  raise ValueError('Нет точной WB-квитанции новой цены')
 target=price(s['target_cny'])
 if not all(price(z['discountedPrice'])==target and price(z['price'])==price(req['price']) for z in sizes):
  raise ValueError('Новая цена не подтверждена WB')
 return dict(nm_id=str(s['nm_id']),article=s['article'],currency='CNY',seller_cny=str(target),
  minimum_cny=floor_price(target),status='required_not_verified',block_policy='preserve_exact_existing',
  write_route='official_seller_cabinet_xlsx',execution_authorized=False)
def attach(execution):
 if execution.get('minimum_price_policy')!=POLICY:return execution
 rows=[]
 for item in execution.get('items',[]):
  try:r=requirement(item)
  except (ValueError,KeyError,TypeError,InvalidOperation):
   r=dict(nm_id=str((item.get('selection') or {}).get('nm_id')),status='needs_fresh_seller_readback')
  if r:rows.append(r)
 execution['minimum_prices']=dict(policy=POLICY,status='required_not_verified' if rows else 'not_applicable',
  rows=rows,minimums_wb_verified=False,reason='Отдельно обновить в кабинете WB и проверить минимум/срок/сохранение блокировок. Ценовой API этого не подтверждает.')
 return execution
def note(execution):
 p=execution.get('minimum_prices') or {}
 if p.get('status')=='required_not_verified':
  return 'Минимальные цены для автоакций ещё не подтверждены: нужно обновить до цены после скидки продавца, округлённой вниз, и сверить блокировки. Изменение обычной цены не завершает этот шаг.'
 return ''
def _time(value):
 d=datetime.fromisoformat(value.replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('Нужна дата с часовым поясом')
 return d
def verify(rows,before,after,now):
 """No mutation/transport. Each snapshot is exact, independently observed seller UI/export."""
 try:
  for snap in (before,after):
   if not 0<=(now-_time(snap['observed_at'])).total_seconds()<=900:raise ValueError('Устаревшая проверка')
   if snap.get('source')!='WB_seller_cabinet_export':raise ValueError('Не подтверждён источник WB')
  for required in rows:
   nm=required['nm_id'];old=before['rows'][nm];new=after['rows'][nm]
   if any(x.get('nm_id')!=nm or x.get('article')!=required['article'] or x.get('currency')!='CNY' for x in (old,new)):raise ValueError('Идентичность товара')
   if price(new['seller_cny'])!=price(required['seller_cny']):raise ValueError('Цена изменилась')
   minimum=new.get('minimum_cny')
   if type(minimum)is not int or minimum!=required['minimum_cny']:raise ValueError('Минимум не совпал')
   if _time(new['minimum_expires_at'])<=now:raise ValueError('Минимум истёк')
   if old.get('block') is None or old['block']!=new.get('block'):raise ValueError('Блокировка не подтверждена или изменилась')
  if not rows:raise ValueError('Пустая проверка')
 except (KeyError,TypeError,ValueError,InvalidOperation):return dict(status='not_verified',minimums_wb_verified=False)
 return dict(status='verified',minimums_wb_verified=True,verified_at=now.isoformat(),count=len(rows))
