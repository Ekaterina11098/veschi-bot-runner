import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import china_conversion_context as c
class W:
 now=datetime(2026,10,29,15,15,tzinfo=timezone.utc)
 def __init__(self,p=None):self.p=p;self.saved={}
 def get(self,k):return self.p
 def save(self,k,p):self.saved[k]=p
def snapshot():
 return dict(observed_at='2026-10-29T15:13:00+00:00',cabinet='token_3',scope='all_sources',complete=True,current=dict(day='2026-10-29',views=10000,carts=500,orders=50),previous=dict(day='2026-10-28',views=20000,carts=1000,orders=150))
class Tests(unittest.TestCase):
 def test_current_general_question_detected(self):
  self.assertTrue(c.is_question('Скажи сегодня конверсия хуже или лучше в среднем'))
  for q in ['Что такое конверсия сегодня','Сегодня рекламная конверсия лучше?','Какая сегодня конверсия у111-Zont-black?']:self.assertFalse(c.is_question(q))
 def test_weighted_ratio_not_mean_of_products(self):
  m=c.metrics(dict(views=1000,carts=20,orders=5));self.assertEqual(m['card_order_pct'],.5)
 def test_unknown_never_zero_and_empty_denominator(self):
  with self.assertRaises(ValueError):c.metrics(dict(views=10,carts=None,orders=0))
  self.assertIsNone(c.metrics(dict(views=0,carts=0,orders=0))['card_order_pct'])
 def test_dated_cache_and_honest_full_day_reference(self):
  data=c.collect(W(snapshot()));text=c.render(data)
  self.assertIn('0,50%',text);self.assertIn('0,75%',text);self.assertIn('до того же часа нет',text)
  self.assertFalse(data['matched_clock'])
 def test_unavailable_still_records_attempt(self):
  with patch.object(c,'collect',side_effect=RuntimeError('blocked')):
   text,trace=c.handle(W(),dict(request_text='Сегодня конверсия лучше или хуже?'))
  self.assertEqual(trace[0]['name'],'conversion_funnel_evidence');self.assertFalse(trace[0]['result']['available'])
 def test_other_cabinet_not_reused(self):
  p=snapshot();p['cabinet']='token_2'
  import sys,types
  a=types.ModuleType('china_analytic_dialog');a.reading=__import__('contextlib').nullcontext
  b=types.ModuleType('china_wb_evidence');calls=[]
  class Reports:
   def __init__(self,w):pass
   def funnel(self,*args):calls.append(args);return dict(complete=False)
  b.Reports=Reports
  with patch.dict(sys.modules,{'china_analytic_dialog':a,'china_wb_evidence':b}):
   with self.assertRaises(RuntimeError):c.collect(W(p))
  self.assertTrue(calls)
if __name__=='__main__':unittest.main()
