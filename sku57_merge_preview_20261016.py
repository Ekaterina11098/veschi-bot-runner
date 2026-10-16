"""Exact merge preview verification. No production imports, network in tests, or deployment."""
import os,sys,json,subprocess
from pathlib import Path
from stock_deploy_support import seal,error
ROOT=Path(__file__).resolve().parent
r=dict(private_main='6eb5f990aecfa1a92909169ffd76f05ac6da469d',private_pr26='ac3b1c439b2ef1bd6ad9e7e8093c91ecb86ae0db',
 runner_main='559bdb873ebf831c15163daa4b35986ebc6485dd',runner_pr5='6fbad90af06ccbc7a06f6f3d33378dbe3043988f',wb_calls=0,wb_writes=0,telegram_calls=0,rows_created=0,merged_production=False)
def call(args,cwd,env=None):
 p=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if p.returncode:raise RuntimeError('Offline command failed: '+p.stdout[-4000:])
 return p.stdout
try:
 for target,other,label in [('private-source','pr26','private'),('runner-preview','pr5','runner')]:
  folder=ROOT/target
  call(['git','fetch',str(ROOT/other),'HEAD'],folder)
  call(['git','-c','user.name=ReadOnlyPreview','-c','user.email=preview@invalid.local','merge','--no-commit','--no-ff','FETCH_HEAD'],folder)
  r[label+'_merge_diff']=call(['git','diff','--cached','--stat'],folder)
 env={k:v for k,v in os.environ.items() if not any(k.startswith(x) for x in ['SUPABASE_','WB_','MPSTATS_','MOYSKLAD_','TELEGRAM_','ADVERTISING_','OPENAI_'])}
 env['PYTHONPATH']=str(ROOT/'private-source')
 test="""import sys,socket,unittest
from unittest.mock import patch
suite=unittest.TestSuite()
for name in ('test_sku_membership_recovery.py','test_financial_finality.py'):
 suite.addTests(unittest.defaultTestLoader.discover('tests',pattern=name))
with patch.object(socket.socket,'connect',side_effect=AssertionError('No network in compatibility tests')):
 result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""
 r['private_tests']=call([sys.executable,'-c',test],ROOT/'private-source',env)
 r['runner_tests']=call([sys.executable,'-c',"""import socket,unittest,sys
from unittest.mock import patch
suite=unittest.defaultTestLoader.discover('.',pattern='test_sku57_driver.py')
with patch.object(socket.socket,'connect',side_effect=AssertionError('No network')):
 r=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if r.wasSuccessful() else 1)
"""],ROOT/'runner-preview',env)
 r['status']='compatible'
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('sku57-merge-preview',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),wb_writes=0)))
if r.get('status')!='compatible':raise SystemExit(1)
