import copy,unittest
from datetime import datetime,timezone
from china_order_decline import relevant,compare,validated,context,prepared_answer,KEY
NOW=datetime(2026,10,23,6,tzinfo=timezone.utc)
class W:
 now=NOW
 def __init__(self,e):self.e=e
 def get(self,k):assert k==KEY;return copy.deepcopy(self.e)
def sample():
 return dict(cabinet='token_3',day_before='2026-10-21',day_yesterday='2026-10-22',orders_complete=True,orders_before=10,orders_yesterday=8,observed_at='2026-10-23T05:00:00Z',today=dict(date='2026-10-23',orders_complete=True,cutoff_msk='2026-10-23T08:00:00+03:00',yesterday_same_clock=5,orders=3))
class Tests(unittest.TestCase):
 def test_adjacent_days_and_same_clock_only(self):
  x=validated(sample(),NOW);self.assertEqual(x['orders']['delta'],-2);self.assertEqual(x['today_same_clock']['comparison']['before'],5);self.assertFalse(x['today_same_clock']['is_full_day'])
 def test_wrong_day_not_reused(self):
  p=sample();p['day_before']='2026-10-15';self.assertFalse(validated(p,NOW)['available'])
 def test_non_china_not_used(self):
  p=sample();p['cabinet']='token_1';self.assertFalse(validated(p,NOW)['available'])
 def test_missing_not_zero(self):
  self.assertFalse(compare(None,8)['available']);self.assertIsNone(compare(0,8)['percent'])
 def test_partial_pages_not_full_day(self):
  p=sample();p['orders_complete']=False;self.assertFalse(validated(p,NOW)['available'])
 def test_unrelated_question_no_context(self):
  self.assertEqual(context(W(sample()),{'request_text':'Какие размеры сумки?'}),'')
 def test_followup_and_ad_decline(self):
  self.assertTrue(relevant('Почему реклама стала работать хуже'));self.assertTrue(relevant('не выкупы',[{'request_text':'Упали продажи'}]))
 def test_prepared_answer_exact_job_and_text(self):
  p=sample();p['prepared_answers']={'7':dict(request_text='Почему упали заказы?',owner_authorized_delivery=True,answer='Проверенный ответ')}
  self.assertEqual(prepared_answer(W(p),{'id':7,'request_text':'Почему упали заказы?'})[0],'Проверенный ответ');self.assertIsNone(prepared_answer(W(p),{'id':8,'request_text':'Почему упали заказы?'}));self.assertIsNone(prepared_answer(W(p),{'id':7,'request_text':'Сделай всё'}))
if __name__=='__main__':unittest.main()
