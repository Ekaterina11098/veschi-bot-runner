import unittest,copy
from datetime import datetime,timezone,date
from unittest.mock import patch
import china_intraday_analysis as h
import china_conversion_context as c
import china_single_price_command as s
class W:
 now=datetime(2026,10,30,18,30,tzinfo=timezone.utc)
 def __init__(self):self.data={}
 def get(self,k):return self.data.get(k)
 def save(self,k,v,**kw):self.data[k]=v
 def catalog(self):return [('10','10-Bag-black'),('11','11-Bag-white')]
 def authorized(self,j):return True
def source(currency='CNY'):
 return dict(cabinet='token_3',seller_identity_verified=True,complete=True,currency=currency,source='fixture',
  period_from='2026-10-30',period_to='2026-10-30',timezone='Europe/Moscow',observed_at='2026-10-30T18:30:00+00:00',
  rows=[dict(order_id='1',nm_id=10,created_at='2026-10-30T15:00:00+03:00',amount=120,cancelled=False)])
class Tests(unittest.TestCase):
 def test_cny_never_fetches_fx(self):
  with patch.object(h,'rate',side_effect=AssertionError('unexpected FX')):r=h.hourly(W(),source(),date(2026,10,30))
  self.assertEqual(r['rows'][15]['amount_cny'],120)
 def test_rub_only_when_needed(self):
  p=source('RUB')
  with patch.object(h,'rate',return_value=dict(effective_date='2026-10-30',rub_per_cny='12')):
   r=h.hourly(W(),p,date(2026,10,30))
  self.assertEqual(r['rows'][15]['amount_cny'],10)
 def test_identity_before_fx(self):
  for field,value in [('cabinet','token_2'),('seller_identity_verified',False),('complete',False)]:
   p=source('RUB');p[field]=value
   with patch.object(h,'rate',side_effect=AssertionError('foreign FX')),self.assertRaises(ValueError):h.hourly(W(),p,date(2026,10,30))
 def test_foreign_product(self):
  p=source();p['rows'][0]['nm_id']=999
  with self.assertRaises(ValueError):h.hourly(W(),p,date(2026,10,30))
 def test_missing_amount_not_zero(self):
  p=source();p['rows'][0]['amount']=None;r=h.hourly(W(),p,date(2026,10,30))
  self.assertEqual(r['rows'][15]['orders'],1);self.assertIsNone(r['rows'][15]['amount_cny'])
 def test_missing_fx_preserves_counts(self):
  with patch.object(h,'rate',side_effect=RuntimeError('CBR unavailable')):r=h.hourly(W(),source('RUB'),date(2026,10,30))
  self.assertEqual(r['rows'][15]['orders'],1);self.assertIsNone(r['rows'][15]['amount_cny'])
 def test_duplicate_and_partial_hour(self):
  p=source();p['rows']*=2;r=h.hourly(W(),p,date(2026,10,30))
  self.assertEqual(r['rows'][15]['orders'],1);self.assertFalse(r['rows'][21]['complete_hour'])
 def test_cbr_nominal(self):
  x='<ValCurs Date="30.10.2026"><Valute><CharCode>CNY</CharCode><Nominal>10</Nominal><Value>120,00</Value></Valute></ValCurs>'
  self.assertEqual(h.parse_rate(x,date(2026,10,30))['rub_per_cny'],'12.00')
 def test_real_dates(self):
  w=W()
  self.assertEqual(str(c.requested_day(w,'Вчера какая конверсия за день?')),'2026-10-29')
  self.assertEqual(str(c.requested_day(w,'А какой показатель за 27 число?')),'2026-10-27')
  self.assertEqual(str(c.requested_day(w,'Хочу общий',[dict(request_text='А какой показатель за 27 число?')])),'2026-10-27')
 def test_hourly_no_daily_denominator(self):
  w=W();w.data[h.ROOT+'2026-10-30']=source()
  text,t=h.handle(w,dict(request_text='Конверсия и суммы по часам'))
  self.assertIn('конверсию не вычисляю',text);self.assertTrue(t[0]['read_only'])
 def test_price_explicit_only(self):
  self.assertEqual(s.parse_single('Подними цену на артикул 10 на 10%')['percent'],'10')
  self.assertEqual(s.parse_single('Снизь цену артикул 10 на 10%')['percent'],'-10')
  for q in ['Можно поднять цену 10 на 10%?','Не поднимай цену артикул10 на10%','Ты поднял цену артикул10 на10%?','Подними ставку артикул10 на10%','Вчера поднимали цену артикул10 на10%','Не исполняй: подними цену артикул10 на10%','Подними цену артикул10 на10% завтра']:
   self.assertIsNone(s.parse_single(q),q)
 def test_price_request_exact_and_dedup(self):
  w=W();j=dict(id=999,sender_id=1,request_text='Подними цену артикул 10 на 10%')
  text,t=s.handle(w,j);p=next(iter(w.data.values()))
  self.assertEqual(p['rules']['include_nm_ids'],['10']);self.assertEqual(t[0]['wb_writes'],0)
  s.handle(w,j);self.assertEqual(len(w.data),1)
 def test_other_cabinet_not_changed(self):
  w=W();text,t=s.handle(w,dict(id=1,sender_id=1,request_text='Подними цену ООО артикул10 на10%'))
  self.assertEqual(t[0]['status'],'cabinet_mismatch');self.assertFalse(w.data)

class SingleExecutionScopeTests(unittest.TestCase):
 def test_prepare_exact_product_raise_and_lower(self):
  import china_catalog_price_execute as e
  from china_catalog_price_command import signature
  goods={str(n):dict(nmID=n,vendorCode=str(n)+'-Bag',currencyIsoCode4217='CNY',editableSizePrice=False,discount=50,clubDiscount=0,sizes=[dict(price=200,discountedPrice=100)]) for n in (10,11)}
  class IO:
   def capability(self):pass
   def catalog(self):return copy.deepcopy(goods)
   def put(self,k,v):self.saved=v
  for pct,target in [('10','110.0'),('-10','90.0')]:
   p=dict(scope='single',day='2026-10-30',actor_user_id=1,source_channel='telegram',request_text='fixture',job_id=999,expires_at='2099-01-01T00:00:00+00:00',
    rules=dict(default_percent=pct,overrides=[],include_nm_ids=['10'],single_exact_percent=True))
   p['signature']=signature(p);io=IO()
   with patch.object(e,'validate_identity'),patch.object(e,'Cache'),patch.object(e,'WB'):r=e.prepare(io,'fixture',p)
   self.assertEqual([s['nm_id'] for s in r['selections']],['10'])
   self.assertEqual(set(r['source_goods']),{'10'});self.assertEqual(h.Decimal(r['selections'][0]['target_cny']),h.Decimal(target))
 def test_catalog_request_not_captured_as_single(self):
  self.assertIsNone(s.parse_single('Подними цены на 5% на все товары'))
  self.assertIsNone(s.parse_single('Подними цену на 10%'))


class CancellationTests(unittest.TestCase):
 def test_current_cancellation_blocks_price_before_write(self):
  import china_catalog_price_execute as e
  from china_catalog_price_command import signature,digest
  p=dict(day='2026-10-30',actor_user_id=1,source_channel='telegram',request_text='fixture',job_id=5,last_human_job_id=5,
   expires_at='2099-01-01T00:00:00+00:00',rules=dict(default_percent='10'),selections=[dict(nm_id='10',article='10-Bag',target_cny='110',seller_discount=50)])
  p['signature']=signature(p);io=object.__new__(e.CatalogIO);io.get=lambda _:p
  cfg=[dict(active=True,chat_id=e.CHAT,bot_id=e.BOT,owner_user_id=5122667182)]
  def db(path):
   if path.startswith('business_agent_config'):return cfg
   if 'id=eq.5' in path:return [dict(chat_id=e.CHAT,sender_id=1,request_text='fixture')]
   return [dict(id=6,request_text='Стоп, не меняй цену')]
  io.db=db;io.tg=lambda *a:dict(user=dict(is_bot=False),status='member')
  a=dict(command_key='key',command_signature=p['signature'],basis='explicit_catalog_percent',selections=p['selections'],selections_sha256=digest(p['selections']))
  with self.assertRaisesRegex(ValueError,'cancellation'):io.validate(a)
if __name__=='__main__':unittest.main()

