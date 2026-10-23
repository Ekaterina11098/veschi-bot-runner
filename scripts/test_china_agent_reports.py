import base64,copy,hashlib,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import china_agent_reports as r

class W:
 now=datetime(2026,10,23,17,tzinfo=timezone.utc)
 active_question_id=1
 def __init__(self):self.data={}
 def get(self,key):return copy.deepcopy(self.data.get(key))
 def save(self,key,value,insert=False):
  if insert and key in self.data:return False
  self.data[key]=copy.deepcopy(value);return True

class Reports(unittest.TestCase):
 def test_request_identity_does_not_reset_daily_delivery(self):
  w=W();w.data['china_agent:advertising_delivery:2026-10-23:v1']=dict(status='delivered')
  image=b'fixed test bytes';w.data['china_agent:advertising_artifacts:2026-10-23:v1']=dict(files=[dict(kind='drr',b64=base64.b64encode(image).decode())],bundle=dict(period='2026-10-22'))
  output=r.make(w,dict(id=1,chat_id=-1004342917488),'advertising',repeat=True)
  self.assertIn('requested_report:v1:1',output['marker']);self.assertFalse(output['execution_authorized'])
  self.assertEqual(w.data['china_agent:advertising_delivery:2026-10-23:v1']['status'],'delivered')
  blob,caption=r.photo(w,-1004342917488,output['marker']);self.assertEqual(blob,image);self.assertIn('исходного среза',caption)
 def test_report_cannot_be_reused_by_other_job_or_chat(self):
  w=W();out=r.freeze(w,dict(id=1,chat_id=-1004342917488),'loss',[b'image'],dict(period='test'))
  w.active_question_id=2
  with self.assertRaises(PermissionError):r.photo(w,-1004342917488,out['marker'])
  w.active_question_id=1
  with self.assertRaises(PermissionError):r.photo(w,99,out['marker'])
 def test_repeat_with_new_request_gets_separate_identity(self):
  w=W();a=r.freeze(w,dict(id=1,chat_id=-1004342917488),'loss',[b'image'],{})
  b=r.freeze(w,dict(id=2,chat_id=-1004342917488),'loss',[b'image'],{})
  self.assertNotEqual(a['marker'],b['marker'])
 def test_registry_preserves_schedules_and_no_write_authority(self):
  c=r.catalog();self.assertTrue(c['schedules_unchanged']);self.assertEqual(c['reports']['price_day']['schedule'],'15:00 МСК')
 def test_no_future_report(self):
  with self.assertRaises(ValueError):r.make(W(),dict(id=1,chat_id=-1004342917488),'loss',repeat=True,report_day='2026-10-24')
 def test_dynamics_exposes_method_and_missing_counts_not_zero(self):
  source=dict(products=[dict(nm_id=1,sa_name='bag',finished_orders=10,is_payed=8,price_after_spp=100,price_after_discount=100)],prices=[dict(nmID=1,sizes=[dict(discountedPrice=100)])],stock=[dict(article='bag',price=10000)],policy=dict(fx_rub_cny=12,logistics_by_nm={'1':dict(delivery_cny=1)}))
  cohort=dict(items=[dict(nm_id=1,article='bag',no_new_ad_change=True)],before_from='2026-10-18',before_to='2026-10-21',after_from='2026-10-23',after_to='2026-10-26')
  valid=dict(nm_id=1,orders_count=4,funnel_orders_count=4,sparkline_orders=[1,1,1,1],orders_sum=4000,advertisement=40)
  with patch('china_analytic_dialog.Analyst.live',return_value=dict(rows=[valid])):
   text=' '.join(r.loss_dynamics(W(),source,cohort))
   self.assertIn('ожидаемая общая прибыль',text);self.assertIn('без нашего отключения',text);self.assertIn('не закрытая чистая прибыль',text)
  invalid=dict(valid,funnel_orders_count=5)
  with patch('china_analytic_dialog.Analyst.live',return_value=dict(rows=[invalid])):
   text=' '.join(r.loss_dynamics(W(),source,cohort));self.assertIn('нет данных',text)

if __name__=='__main__':unittest.main()

