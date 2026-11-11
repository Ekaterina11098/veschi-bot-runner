import ast,re,unittest
from decimal import Decimal
from pathlib import Path
ns={'re':re,'Decimal':Decimal}
for node in ast.parse(Path(__file__).with_name('china_price_apply.py').read_text(encoding='utf-8')).body:
 if isinstance(node,ast.FunctionDef) and node.name in ('dec','report_contains_selection'):exec(compile(ast.Module(body=[node],type_ignores=[]),'<test>','exec'),ns)
class PriceFormatTest(unittest.TestCase):
 def test_exact_values_both_punctuation(self):
  s=dict(action='Повышение',article='A',current_cny='208',target_cny='218.5');f=ns['report_contains_selection']
  self.assertTrue(f('Повышение · A Продавец: 208 → 218.5 ¥',s))
  self.assertTrue(f('Повышение · A Продавец: 208 → 218,5 ¥',s))
  for line in ['Повышение · A Продавец: 208 → 219 ¥','Повышение · B Продавец: 208 → 218.5 ¥','Снижение · A Продавец: 208 → 218.5 ¥','Повышение · A Продавец: 208 → 218.5 ¥\nПовышение · A Продавец: 208 → 218,5 ¥']:
   self.assertFalse(f(line,s))
if __name__=='__main__':unittest.main()
