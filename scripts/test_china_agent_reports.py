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

if __name__=='__main__':unittest.main()
