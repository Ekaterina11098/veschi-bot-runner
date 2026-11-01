import unittest
from unittest.mock import patch
from china_advertising_v2 import refresh_budget_context,history

class RegistryHistory(unittest.TestCase):
 def test_recovery_receipt_outside_old_prefix_is_loaded_and_verified(self):
  receipt=dict(status='verified',verified_at='2026-10-31T07:14:25+00:00',before=dict(id=1,nm_settings=[dict(nm_id=10,bids_kopecks=dict(search=36))]),after=dict(id=1,nm_settings=[dict(nm_id=10,bids_kopecks=dict(search=28))]))
  class IO:
   def db(self,path):self.query=path;return []
   def get(self,key):return {'1':'china_agent:new_recovery:execution'} if key=='china_agent:verified_campaign_state:v1' else receipt
  io=IO()
  with patch('china_advertising_v2.read_price_experience',return_value=[]),patch('china_advertising_v2.read_economics',return_value={}):s=refresh_budget_context(io,{},'2026-11-01')
  events=history(s['executions']);self.assertEqual(len(events),1);self.assertEqual(events[0]['at'],'2026-10-31T07:14:25+00:00')
  self.assertIn('cache_key.like.china_agent:*:execution',io.query)
 def test_registry_pointer_with_wrong_campaign_is_not_proof(self):
  class IO:
   def db(self,path):return []
   def get(self,key):return {'1':'receipt'} if key=='china_agent:verified_campaign_state:v1' else dict(status='verified',after=dict(id=2))
  with patch('china_advertising_v2.read_price_experience',return_value=[]),patch('china_advertising_v2.read_economics',return_value={}):s=refresh_budget_context(IO(),{},'2026-11-01')
  self.assertEqual(s['executions'],[])

if __name__=='__main__':unittest.main()

