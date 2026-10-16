import unittest
from types import SimpleNamespace
from advertising_cached_finance_reader import install
class Reader(unittest.TestCase):
 def setup_reader(self):
  self.calls=[]
  def read(table,params):
   self.calls.append(params)
   if params['select']=='id':return [{'id':3},{'id':2},{'id':1}]
   return [{'id':int(params['id'][3:]),'payload':[]} ]
  original=lambda *a:['original']
  stage=SimpleNamespace(snapshots=original);install(stage)
  return stage,read
 def test_only_first_payload_loaded(self):
  stage,read=self.setup_reader();it=stage.snapshots(read,('mpstats_lk_wb_products',),'token_2','2026-10-15','2026-10-15')
  self.assertEqual(next(it)['id'],3);self.assertEqual(len(self.calls),2);self.assertEqual(self.calls[0]['limit'],5);self.assertNotIn('payload',self.calls[0]['select'])
 def test_retained_fallback_lazy(self):
  stage,read=self.setup_reader();it=stage.snapshots(read,('mpstats_lk_wb_products',),'token_2','2026-10-15','2026-10-15')
  self.assertEqual([next(it)['id'],next(it)['id']],[3,2]);self.assertEqual(len(self.calls),3)
 def test_other_sources_unmodified(self):
  stage,read=self.setup_reader();self.assertEqual(stage.snapshots(read,('other',),'token_2'),['original']);self.assertEqual(self.calls,[])
 def test_weekly_reads_unmodified(self):
  stage,read=self.setup_reader();self.assertEqual(stage.snapshots(read,('mpstats_lk_wb_products',),'token_2','2026-10-09','2026-10-15'),['original'])
 def test_missing_is_empty_not_zero(self):
  stage,read=self.setup_reader();self.assertEqual(list(stage.snapshots(lambda *a:[],('mpstats_lk_wb_products',),'token_2','2026-10-15','2026-10-15')),[])
if __name__=='__main__':unittest.main()
