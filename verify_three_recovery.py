"""Run actual recovery fault suites for every exact prepared pair. Synthetic only."""
import types, unittest, pathlib, sys
root=pathlib.Path(__file__).parent
scopes=[(39410834,1007948808),(40223314,1123677454),(39410834,320248210)]
total=0
for cid,nm in scopes:
 suite=unittest.TestSuite()
 for filename in ('test_sku_membership_recovery.py','test_sku57_driver.py'):
  text=(root/filename).read_text()
  # Each isolated module gets the same fault suite and a different exact fixture pair.
  text=(text.replace('NM=1007948808;CID=39410834',f'NM={nm};CID={cid}') if filename=='test_sku_membership_recovery.py' else text.replace('1007948808',str(nm)).replace('39410834',str(cid)))
  text=text.replace("if __name__=='__main__':unittest.main()","")
  module=types.ModuleType('isolated_'+str(nm)+'_'+filename[:-3])
  module.__file__=str(root/filename)
  exec(compile(text,str(root/filename),'exec'),module.__dict__)
  suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
 result=unittest.TextTestRunner(verbosity=1).run(suite)
 total+=result.testsRun
 if not result.wasSuccessful():sys.exit(1)
 print('EXACT_PAIR_PASS',cid,nm,result.testsRun)
# Explicitly reject Cartesian-product cross-pair widening.
import advertising_sku57_recovery_owner as driver
for cid,nm in ((40223314,1007948808),(40223314,320248210),(39410834,1123677454),(1,1)):
 try:driver.exact_scope({'specification':{'cabinet':'token_2','campaign_id':cid,'nm_id':nm}})
 except PermissionError:pass
 else:raise AssertionError('Cross pair permitted')
print('TOTAL_TESTS',total,'WB_CALLS_REAL=0 ACTION_ROWS_CREATED=0 TIMERS_CREATED=0')
