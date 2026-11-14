import importlib.util,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
class Disabled(unittest.TestCase):
 def test_owner_disabled_policy_prevents_context_source_and_model_calls(self):
  calls=[]
  class DB:
   def get(self,key):
    calls.append(key);self.assert_policy(key)
    return dict(enabled=False)
   def assert_policy(self,key):
    if key!='china_agent:hourly_codex_analysis:v1:policy':raise AssertionError('Source read while disabled')
  def forbidden(*a,**k):raise AssertionError('Model/context active while disabled')
  modules={'china_codex_cloud':types.SimpleNamespace(DB=DB,Worker=forbidden),'china_codex_analysis':types.SimpleNamespace(Core=forbidden,active=forbidden)}
  spec=importlib.util.spec_from_file_location('hourly_disabled_test',Path(__file__).with_name('china_codex_hourly.py'));m=importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules,modules):spec.loader.exec_module(m);m.main()
  self.assertEqual(calls,['china_agent:hourly_codex_analysis:v1:policy'])
if __name__=='__main__':unittest.main()

