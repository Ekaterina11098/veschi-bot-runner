import unittest,types,sys
from unittest.mock import patch
from china_price_linked_period import repair
class ExactLinkedPeriod(unittest.TestCase):
 def context(self):return dict(status='incomplete',baseline_membership_known=True,membership_changed=False,membership={'members':['1','2']},baseline_from='2026-11-01',baseline_to='2026-11-04',period_from='2026-11-06',period_to='2026-11-09')
 def inputs(self):
  ds={('2026-11-01','2026-11-04'):{'1':{'sales_count':3},'2':{'sales_count':4}},('2026-11-06','2026-11-09'):{'1':{'sales_count':2},'2':{'sales_count':3}}}
  marks={key:{'id':i,'payload':[{}]}for i,key in enumerate(ds,1)}
  return ds,marks
 def test_complete_group_uses_exact_totals(self):
  ds,m=self.inputs();mod=types.ModuleType('advertising_agent.mpstats_economics')
  mod.calculate=lambda *a,**k:{1:{'finance_complete':True,'economics_status':'complete','net_profit':10},2:{'finance_complete':True,'economics_status':'complete','net_profit':20}}
  parent=types.ModuleType('advertising_agent');parent.__path__=[]
  with patch.dict(sys.modules,{'advertising_agent':parent,'advertising_agent.mpstats_economics':mod}):
   r=repair(self.context(),ds,m,{})
  self.assertEqual('not_growing',r['status']);self.assertEqual(7,r['sales_before']);self.assertEqual(30,r['profit_before']);self.assertFalse(r['daily_series_available'])
 def test_missing_member_never_becomes_zero(self):
  ds,m=self.inputs();del ds[('2026-11-01','2026-11-04')]['2'];c=self.context()
  mod=types.ModuleType('advertising_agent.mpstats_economics');mod.calculate=lambda *a,**k:(_ for _ in()).throw(AssertionError('No finance call'))
  with patch.dict(sys.modules,{'advertising_agent.mpstats_economics':mod}):self.assertEqual(c,repair(c,ds,m,{}))
 def test_changed_membership_not_repaired(self):
  c=dict(self.context(),membership_changed=True);self.assertEqual(c,repair(c,{}, {},{}))
 def test_missing_finance_stays_unknown(self):
  ds,m=self.inputs();c=self.context();mod=types.ModuleType('advertising_agent.mpstats_economics');mod.calculate=lambda *a,**k:{1:{'finance_complete':False}}
  with patch.dict(sys.modules,{'advertising_agent.mpstats_economics':mod}):self.assertEqual(c,repair(c,ds,m,{}))
if __name__=='__main__':unittest.main()
