"""Offline assertions against the installed pinned source; no credentials or writes."""
import ast,sys,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_CEILING
source=Path(sys.argv.pop(1)).read_text()
tree=ast.parse(source)
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('offer','observe_prices')]
env=dict(Decimal=Decimal,ROUND_CEILING=ROUND_CEILING,timedelta=timedelta,MSK=timezone(timedelta(hours=3)),membership=lambda *a:{'available':False})
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<installed price policy>','exec'),env)
def row(base=676,discount=50):
 return dict(nmID=1,vendorCode='145',currencyIsoCode4217='CNY',discount=discount,sizes=[dict(price=base,discountedPrice=base*(100-discount)/100)])
class InstalledPolicyTests(unittest.TestCase):
 def test_raise_integer_base_and_discount(self):
  p=env['offer'](row())
  self.assertEqual((p['target_base_cny'],p['target_cny'],p['discount']),(710,355,50))
 def test_second_card(self):
  p=env['offer'](row(754))
  self.assertEqual((p['target_base_cny'],p['target_cny']),(792,396))
 def test_step_change_does_not_reset_history(self):
  p=env['offer'](row());p.update(target_base_cny=744,target_cny=372)
  increase={'start_date':'2026-10-16'}
  state={'price_history':{'1':{'price':p,'increase':increase.copy(),'daily_observation':{'enabled':True}}}}
  data=type('Data',(),{'excluded':lambda *a:False})()
  notices=env['observe_prices'](data,state,{'rows':[row()]},datetime(2026,10,20,tzinfo=timezone.utc),{})
  entry=state['price_history']['1']
  self.assertEqual(notices,[])
  self.assertEqual(entry['increase'],increase)
  self.assertNotIn('last_price_change',entry)
  self.assertTrue(entry['daily_observation']['enabled'])
 def test_actual_raise_still_observed(self):
  p=env['offer'](row());state={'price_history':{'1':{'price':p}}}
  data=type('Data',(),{'excluded':lambda *a:False})()
  self.assertEqual(len(env['observe_prices'](data,state,{'rows':[row(710)]},datetime(2026,10,20,tzinfo=timezone.utc),{})),1)
  self.assertEqual(state['price_history']['1']['increase']['start_date'],'2026-10-21')
if __name__=='__main__':unittest.main()
