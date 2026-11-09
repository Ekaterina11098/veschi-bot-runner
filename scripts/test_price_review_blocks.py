import ast,re,unittest
from pathlib import Path

class AtomicPriceRows(unittest.TestCase):
    def test_cloud_selection_cannot_drop_buyer_forecast_line(self):
        module=ast.parse((Path(__file__).parent/'china_codex_reports.py').read_text(encoding='utf8'))
        node=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='price_parts')
        env={'re':re};exec(compile(ast.Module(body=[node],type_ignores=[]),'price_parts','exec'),env)
        draft='Повышение · 37-FurManizhka-dbrown Продавец: 100 → 105 ¥\nПокупатель: 1000 → 1050 ₽\n\nСнижение · 531-NoelBag-grey Продавец: 100 → 95 ¥\nПокупатель: 1000 → 950 ₽'
        rows,tables,plain=env['price_parts'](draft)
        self.assertEqual(len(rows),2)
        self.assertTrue(all('Продавец:' in row and '\nПокупатель:' in row for row in rows.values()))
if __name__=='__main__':unittest.main()

