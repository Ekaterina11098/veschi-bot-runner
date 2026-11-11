import sys,types,unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
from china_codex_appserver import encode,decode
from china_economics_recovery import extend_catalog
class W:
 def __init__(self,source):self.source=source
 def get(self,key):return self.source
 def catalog(self):return [('1','old')]
class Native(unittest.TestCase):
 def test_persisted_rollout_roundtrip(self):
  raw='{"work":"память", "tools":[]}\n'.encode();self.assertEqual(decode(encode(raw)),raw)
 def test_new_product_uses_verified_china_catalogue(self):
  w=W({'cabinet':'token_3','status':'complete','catalogue':{'rows':[{'nmID':2,'vendorCode':'new'}]}})
  self.assertEqual(dict(extend_catalog(w)),{'1':'old','2':'new'});self.assertEqual(dict(w.catalog())['2'],'new')
 def test_other_cabinet_not_merged(self):
  w=W({'cabinet':'token_1','status':'complete','catalogue':{'rows':[{'nmID':2,'vendorCode':'foreign'}]}})
  self.assertEqual(dict(extend_catalog(w)),{'1':'old'})
 def test_no_arbitrary_tools_or_secret_cache(self):
  from china_codex_runtime import Tools
  modules={'china_analytic_dialog':types.SimpleNamespace(Analyst=lambda *args:None)}
  with patch.dict(sys.modules,modules):t=Tools(W({}),{'id':1})
  for key in ['china_agent:bot_transport:token','china_agent:owner_secret:v1','china_agent:codex_bridge:v1:policy']:
   with self.assertRaises(PermissionError):t('read_saved_data',{'cache_key':key,'nm_ids':[]})
  with self.assertRaises(PermissionError):t('run_shell',{'command':'anything'})
if __name__=='__main__':unittest.main()