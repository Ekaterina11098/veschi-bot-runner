import ast,pathlib,unittest
source=pathlib.Path('advertising_daily_tables_owner.py').read_text()
tree=ast.parse(source)
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='publication_coverage')
scope={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'coverage','exec'),scope)
class Test(unittest.TestCase):
 def test_empty(self):self.assertFalse(scope['publication_coverage']({'campaigns':[]})['ready'])
 def test_missing(self):self.assertFalse(scope['publication_coverage']({'campaigns':[{'metrics_complete':False}]*11})['ready'])
 def test_zero_spend_is_valid(self):self.assertTrue(scope['publication_coverage']({'campaigns':[{'metrics_complete':True,'spend':0}]})['ready'])
 def test_partial_explicit(self):self.assertEqual(scope['publication_coverage']({'campaigns':[{'metrics_complete':True},{'metrics_complete':False}]}),{'ready':True,'known':1,'total':2})
if __name__=='__main__':unittest.main()
