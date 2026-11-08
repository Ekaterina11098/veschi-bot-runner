import sys,types,unittest
from unittest.mock import patch
from datetime import datetime,timezone
import china_no_paid as n
import china_codex_cloud as cloud
import china_model_usage as meter
from test_china_codex_bridge import W,job,CHAT,ROOT,handle

class NoPaid(unittest.TestCase):
 def enabled(self,w):
  w.values[n.POLICY]={'enabled':True,'chat_id':n.CHAT,'bot_id':n.BOT,'paid_api_allowed':False}
 def test_sdk_blocked_before_client_creation(self):
  # Unit guards must not read mutable live policy or create a real API client.
  db=types.SimpleNamespace(get=lambda key:dict(enabled=False,paid_api_allowed=False,chat_id=n.CHAT,bot_id=n.BOT,model='gpt-6.1-sol'))
  w=cloud.Worker(db)
  with self.assertRaisesRegex(PermissionError,'no request'):w.sdk()
  self.assertIsNone(w.client)
 def test_legacy_meter_blocked_before_network(self):
  called=[]
  with self.assertRaises(PermissionError):meter.metered_request(lambda body:called.append(body),{})
  self.assertFalse(called)
 def test_policy_bound_to_exact_bot_and_chat(self):
  w=W();self.assertFalse(n.enabled(w));self.enabled(w);self.assertTrue(n.enabled(w))
  w.values[n.POLICY]['chat_id']=3;self.assertFalse(n.enabled(w))
 def test_free_reply_delivered_with_existing_receipt_and_no_collector(self):
  w=W();self.enabled(w);j=job();j['request_text']='/codex Помощь'
  with patch('china_codex_bridge.prepare_analytics',side_effect=AssertionError('Unexpected cloud collector')):
   self.assertEqual(handle(w,j,{'chat_id':CHAT}),'codex_bridge_delivered')
  out=w.get(ROOT+'outbox:224')
  self.assertEqual(out['source_channel'],'deterministic_no_paid')
  self.assertEqual(out['paid_model_calls'],0)
  self.assertIn('Платные обращения',w.sends[0][2])
 def test_foreign_sender_gets_no_free_reply(self):
  w=W();self.enabled(w);j=job();j['sender_id']=2
  self.assertEqual(handle(w,j,{'chat_id':CHAT}),'codex_bridge_sender_rejected')
  self.assertFalse(w.sends)
 def test_existing_uncertain_outbox_never_replaced(self):
  w=W();self.enabled(w);old={'status':'uncertain'};w.values[ROOT+'outbox:224']=old.copy()
  self.assertEqual(handle(w,job(),{'chat_id':CHAT}),'codex_bridge_invalid_reply')
  self.assertEqual(w.get(ROOT+'outbox:224'),old)
 def test_conversion_uses_deterministic_handler(self):
  mod=types.SimpleNamespace(handle=lambda *a:('Срез WB: 10 заказов / 100 просмотров = 10%.',[]))
  with patch.dict(sys.modules,{'china_conversion_context':mod}):
   w=W()
   self.assertIn('10%',n.answer(w,dict(job(),request_text='Конверсия сегодня')))
 def test_unavailable_data_never_falls_back_to_model(self):
  mod=types.SimpleNamespace(handle=lambda *a:(_ for _ in ()).throw(ValueError('gap')))
  with patch.dict(sys.modules,{'china_conversion_context':mod}):
   value=n.safe_answer(W(),dict(job(),request_text='Конверсия сегодня'))
   self.assertIn('Платный API не использовался',value)
 def test_multiple_report_pages_keep_existing_identities(self):
  from conversion_watches import split_message
  self.assertEqual(split_message('CHINA_AGENT_REPORT:a:0\n[[ПРЕДЛОЖЕНИЯ]]\nCHINA_AGENT_REPORT:a:1'),
                   ['CHINA_AGENT_REPORT:a:0','CHINA_AGENT_REPORT:a:1'])
if __name__=='__main__':unittest.main()
