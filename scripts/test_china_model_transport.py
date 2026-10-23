import unittest,os,sys,types,copy
from unittest.mock import patch
from china_model_transport import ModelResponseError,seconds,request

class TransportTests(unittest.TestCase):
 def test_billing_is_never_retried(self):
  for code in ['insufficient_quota','billing_hard_limit_reached','spend_limit_exceeded']:
   self.assertFalse(ModelResponseError(429,dict(code=code)).retryable)
 def test_transient_retry_after_is_minimum_not_cap(self):
  self.assertTrue(ModelResponseError(429,dict(code='rate_limit_exceeded')).retryable)
  self.assertGreaterEqual(seconds('900'),900)
  self.assertGreaterEqual(seconds(None),60)
 def test_diagnostic_details_do_not_leak_into_exception(self):
  response=types.SimpleNamespace(ok=False,status_code=429,headers={'retry-after':'120'},json=lambda:dict(error=dict(code='rate_limit_exceeded',message='Private org quota detail')))
  module=types.ModuleType('requests');module.post=lambda *a,**kw:response
  with patch.dict(sys.modules,{'requests':module}),patch.dict(os.environ,{'OPENAI_API_KEY':'test-secret'}):
   with self.assertRaises(ModelResponseError) as ctx:request(dict(model='test'))
  self.assertEqual(ctx.exception.details['message'],'Private org quota detail')
  self.assertNotIn('Private',str(ctx.exception));self.assertNotIn('test-secret',str(ctx.exception))

if __name__=='__main__':unittest.main()
