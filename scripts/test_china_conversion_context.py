import unittest,sys,types
from contextlib import nullcontext
from datetime import datetime,timezone
from unittest.mock import patch
import china_conversion_context as c
class W:
 now=datetime(2026,10,29,15,15,tzinfo=timezone.utc)
 def __init__(self,p=None):self.p=p or {};self.saved={}
 def get(self,k):return self.saved.get(k,self.p.get(k))
 def save(self,k,p):self.saved[k]=p
def snapshot():
 return dict(observed_at='2026-10-29T15:13:00+00:00',cabinet='token_3',scope='all_sources',complete=True,current=dict(day='2026-10-29',views=10000,carts=500,orders=50),previous=dict(day='2026-10-28',views=20000,carts=1000,orders=150))
def state(first,last,counts=((1000,50,10),(10,5,2))):
 rows=[]
 for nm,values in enumerate(counts,1):
  r=dict(period_from=first,period_to=last,scope='all_sources',clicks=values[0],cart_count=values[1],orders=values[2])
  rows.append(dict(nm_id=nm,selected=r))
 return dict(cabinet='token_3',complete=True,rows=rows,observed_at='2026-10-29T15:14:00+00:00',source_key='synthetic')
H=[dict(request_text='Скажи сегодня конверсия хуже или лучше в среднем')]
class Tests(unittest.TestCase):
 def test_original_question(self):self.assertEqual(c.intent(H[0]['request_text']),1)
 def test_exact_pavel_followup(self):self.assertEqual(c.intent('А если сравнить с данными в среднем за неделю',H),7)
 def test_context_is_required(self):self.assertIsNone(c.intent('А если сравнить с данными в среднем за неделю'))
 def test_other_topic_stops_context(self):self.assertIsNone(c.intent('А за неделю?',H+[dict(request_text='Какая цена сумки?')]))
 def test_reject_other_metrics_and_definitions(self):
  for q in ['Что такое конверсия сегодня','Сегодня рекламная конверсия лучше?','Какая сегодня конверсия у111-Zont-black?','В РК сегодня конверсия лучше?','Конверсия органических заказов сегодня?']:
   self.assertIsNone(c.intent(q),q)
 def test_supported_days(self):
  for q,n in [('Конверсия за 14 дней',14),('А за две недели?',14),('Конверсия за 30 дней',30)]:
   self.assertEqual(c.intent(q,H),n)
 def test_unknown_not_zero(self):
  with self.assertRaises(ValueError):c.metrics(dict(views=1,carts=None,orders=0))
  self.assertIsNone(c.metrics(dict(views=0,carts=0,orders=0))['card_order_pct'])
 def test_sum_before_ratio(self):
  x=c.total(state('2026-10-22','2026-10-28'),'selected','2026-10-22','2026-10-28')
  self.assertAlmostEqual(x['card_order_pct'],1200/1010)
  self.assertNotEqual(x['card_order_pct'],10.5)
 def test_bad_scope_period_pagination_duplicates(self):
  for mutation in ['scope','period','partial','duplicate']:
   s=state('2026-10-22','2026-10-28')
   if mutation=='scope':s['rows'][0]['selected']['scope']='advertising'
   if mutation=='period':s['rows'][0]['selected']['period_to']='2026-10-29'
   if mutation=='partial':s['complete']=False
   if mutation=='duplicate':s['rows'].append(s['rows'][0])
   with self.assertRaises(ValueError):c.total(s,'selected','2026-10-22','2026-10-28')
 def test_daily_cache(self):
  x=c.collect(W({c.ROOT+'2026-10-29':snapshot()}))
  self.assertIn('0,50%',c.render(x));self.assertIn('до того же часа нет',c.render(x))
 def test_week_followup_calls_source_exact_period(self):
  w=W({c.ROOT+'2026-10-29':snapshot()})
  with patch.object(c,'read',return_value=state('2026-10-22','2026-10-28')) as read:
   text,trace=c.handle(w,dict(request_text='А если сравнить с данными в среднем за неделю'),H)
  read.assert_called_once()
  self.assertEqual(tuple(map(str,read.call_args.args[1:])),('2026-10-22','2026-10-28'))
  self.assertIn('1 010 переходов',text);self.assertIn('12 заказанных',text)
  self.assertEqual(trace[0]['requested_completed_days'],7)
  with patch.object(c,'read',side_effect=AssertionError('cache expected')):
   again=c.collect_period(w,7)
  self.assertTrue(again['cached'])
 def test_week_failure_keeps_daily_evidence(self):
  w=W({c.ROOT+'2026-10-29':snapshot()})
  with patch.object(c,'read',side_effect=RuntimeError('HTTP429')):
   text,trace=c.handle(w,dict(request_text='А за неделю?'),H)
  self.assertIn('50 заказанных',text);self.assertIn('не получен',text)
  self.assertFalse(trace[0]['result']['comparison_available']);self.assertNotIn('инструмента',text)
 def test_failure_records_attempt(self):
  with patch.object(c,'collect',side_effect=RuntimeError('blocked')):
   text,trace=c.handle(W(),dict(request_text=H[0]['request_text']))
  self.assertFalse(trace[0]['result']['available'])
 def test_wrong_cabinet_stale_or_wrong_dates_not_reused(self):
  for kind in ['cabinet','stale','dates']:
   p=dict(snapshot(),period={'from':'2026-10-22','to':'2026-10-28'},totals=dict(views=100,carts=10,orders=2))
   if kind=='cabinet':p['cabinet']='token_2'
   if kind=='stale':p['observed_at']='2026-10-28T15:13:00+00:00'
   if kind=='dates':p['period']['from']='2026-10-23'
   w=W({c.ROOT+'2026-10-29':snapshot(),c.WEEK_ROOT+'2026-10-29':p})
   with patch.object(c,'read',return_value=state('2026-10-22','2026-10-28')) as read:c.collect_period(w,7)
   read.assert_called_once()
if __name__=='__main__':unittest.main()
