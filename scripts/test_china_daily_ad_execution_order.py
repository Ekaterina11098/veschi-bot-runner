"""A same-plan exclusion must not remove an addition's live minimum context."""
import ast,copy,unittest
from pathlib import Path
class Order(unittest.TestCase):
 def test_addition_precedes_exclusion_without_changing_approved_items(self):
  tree=ast.parse(Path(__file__).with_name('china_daily_ad_actions.py').read_text(encoding='utf8'))
  fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='execution_order')
  ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'order','exec'),ns)
  items=[dict(id='exclude50',kind='ad_exclude_sku'),dict(id='raise',kind='ad_set_bid'),dict(id='add50',kind='ad_add_sku')]
  original=copy.deepcopy(items);ordered=ns['execution_order'](items)
  self.assertLess([x['id']for x in ordered].index('add50'),[x['id']for x in ordered].index('exclude50'))
  self.assertEqual(items,original);self.assertEqual(sorted(x['id']for x in ordered),sorted(x['id']for x in items))
if __name__=='__main__':unittest.main()
