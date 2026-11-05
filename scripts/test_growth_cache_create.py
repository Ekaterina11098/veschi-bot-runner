import copy, unittest
from china_advertising_full_growth import save_analytic_cache
KEY='china_agent:analytic_read:v1:fixture'
class IO:
 def __init__(self):self.rows={};self.calls=[]
 def get(self,k):return copy.deepcopy(self.rows.get(k))
 def create(self,k,v):
  self.calls.append('create')
  if k in self.rows:return False
  self.rows[k]=copy.deepcopy(v);return True
 def put(self,k,v):
  self.calls.append('patch')
  if k in self.rows:self.rows[k]=copy.deepcopy(v)
class Tests(unittest.TestCase):
 def test_missing_created_not_patched(self):
  io=IO();save_analytic_cache(io,KEY,{'rows':{1:{'orders':2}}})
  self.assertEqual(io.calls,['create']);self.assertEqual(io.rows[KEY]['rows'],{'1':{'orders':2}})
 def test_existing_refreshed(self):
  io=IO();io.rows[KEY]={'old':True};save_analytic_cache(io,KEY,{'new':True})
  self.assertEqual(io.calls,['patch']);self.assertEqual(io.get(KEY),{'new':True})
 def test_failed_create_not_accepted(self):
  io=IO();io.create=lambda *a:False
  with self.assertRaisesRegex(RuntimeError,'readback mismatch'):save_analytic_cache(io,KEY,{'rows':[]})
 def test_racing_create_not_overwritten(self):
  io=IO()
  def race(k,v):io.rows[k]={'other':True};return False
  io.create=race
  with self.assertRaisesRegex(RuntimeError,'readback mismatch'):save_analytic_cache(io,KEY,{'rows':[]})
  self.assertEqual(io.rows[KEY],{'other':True})
 def test_unrelated_state_not_created(self):
  io=IO()
  with self.assertRaises(ValueError):save_analytic_cache(io,'china_agent:advertising_delivery:day:v1',{})
  self.assertEqual(io.calls,[])
if __name__=='__main__':unittest.main()

