import os,sys,types,unittest
from unittest.mock import patch
from china_price_state_transport import safe,install
class Retry(unittest.TestCase):
 def test_only_idempotent_cache_operations_retried(self):
  class ConnectionError(Exception):pass
  calls=[]
  def raw(session,method,url,**kw):
   calls.append(url)
   if len(calls)==1:raise ConnectionError()
   return types.SimpleNamespace(status_code=200)
  fake=types.SimpleNamespace(ConnectionError=ConnectionError,Timeout=TimeoutError,sessions=types.SimpleNamespace(Session=types.SimpleNamespace(request=raw)))
  with patch.dict(os.environ,{'SUPABASE_URL':'https://cache.example'}),patch.dict(sys.modules,{'requests':fake}),patch('time.sleep'):
   install();fake.sessions.Session.request(None,'POST','https://cache.example/rest/v1/telegram_api_cache',params=dict(on_conflict='cache_key'),json=dict(cache_key='test',payload={}))
   self.assertEqual(len(calls),2);calls.clear()
   with self.assertRaises(ConnectionError):fake.sessions.Session.request(None,'POST','https://api.telegram.org/bot/sendMessage',json={})
   self.assertEqual(len(calls),1)
   self.assertFalse(safe('POST','https://cache.example/rest/v1/business_agent_jobs',dict(json={})))
if __name__=='__main__':unittest.main()
