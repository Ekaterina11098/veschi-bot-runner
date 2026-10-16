import importlib.util,unittest,os
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
s=importlib.util.spec_from_file_location('driver',Path(__file__).with_name('advertising_sku57_recovery_owner.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Closed:
 def __getattr__(self,key):raise AssertionError('No side effects when disabled')
class Driver(unittest.TestCase):
 def test_off_no_reads_writes(self):self.assertEqual(m.resume_existing(Closed(),Closed(),datetime.now(timezone.utc))['wb_calls'],0)
 def test_global_disabled(self):
  with patch.dict(os.environ,{'ADVERTISING_EXECUTION_ENABLED':'false'}):
   with self.assertRaises(PermissionError):m.resume_existing(Closed(),Closed(),datetime.now(timezone.utc),enabled=True)
 def test_no_new_rows_or_generic_claim(self):
  source=Path(__file__).with_name('advertising_sku57_recovery_owner.py').read_text()
  self.assertNotIn("store.db('POST'",source);self.assertNotIn('claim_advertising_agent_job',source)
 def test_no_expiry_filter(self):
  source=Path(__file__).with_name('advertising_sku57_recovery_owner.py').read_text();self.assertNotIn("'expires_at'",source)
if __name__=='__main__':unittest.main()
