import ast,unittest
from pathlib import Path
tree=ast.parse(Path('runner/advertising_source_owner.py').read_text())
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='campaign_day_gaps')
ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-gap-planner','exec'),ns)
gap=ns['campaign_day_gaps']
def snap(days,**kw):
 pack=dict(campaign_id=1,report='days',spending_reconciled=True,scope_nm_id=None,rows=[dict(date='2026-10-%02d'%d,ac_spending_sum=v) for d,v in days]);pack.update(kw);return dict(payload=[pack])
class Gaps(unittest.TestCase):
 def test_independent_weekly_and_daily(self):
  self.assertEqual(gap([snap([(9,2)],report='products')],1,'2026-10-12','2026-10-15'),[('2026-10-12','2026-10-15')])
 def test_reuse_disjoint_spans(self):
  self.assertEqual(gap([snap([(9,1),(10,0),(11,2)]),snap([(12,3),(13,4),(14,5),(15,6)])],1,'2026-10-09','2026-10-15'),[])
 def test_sku_days_do_not_cover_campaign(self):
  self.assertEqual(gap([snap([(12,5)],scope_nm_id=7)],1,'2026-10-12','2026-10-12'),[('2026-10-12','2026-10-12')])
 def test_unknown_not_zero(self):
  self.assertEqual(gap([snap([(12,None)])],1,'2026-10-12','2026-10-12'),[('2026-10-12','2026-10-12')])
 def test_unverified_not_coverage(self):
  self.assertEqual(gap([snap([(12,0)],spending_reconciled=False)],1,'2026-10-12','2026-10-12'),[('2026-10-12','2026-10-12')])
 def test_only_exact_holes(self):
  self.assertEqual(gap([snap([(9,1),(11,1),(12,1),(15,1)])],1,'2026-10-09','2026-10-15'),[('2026-10-10','2026-10-10'),('2026-10-13','2026-10-14')])
if __name__=='__main__':unittest.main()
