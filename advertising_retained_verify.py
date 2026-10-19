"""Credential-free targeted runner regression verification; only encrypted logs leave the runner."""
import subprocess,sys,os,json
from stock_deploy_support import seal
code="""import unittest,sys,socket
from unittest.mock import patch
suite=unittest.TestSuite()
for p in ('test_advertising_daily_repair.py','test_advertising_budget_telemetry.py','test_advertising_retained_analysis.py'):
 suite.addTests(unittest.defaultTestLoader.discover('.',pattern=p))
with patch.object(socket.socket,'connect',side_effect=AssertionError('Offline verification network forbidden')):
 r=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if r.wasSuccessful() else 1)
"""
env={k:v for k,v in os.environ.items() if not any(k.startswith(p) for p in ('SUPABASE_','WB_','MPSTATS_','TELEGRAM_','ADVERTISING_','OPENAI_'))}
p=subprocess.run([sys.executable,'-c',code],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
seal('advertising-retained-inventory',dict(tests=dict(exit=p.returncode,log=p.stdout),source_calls=0,telegram_calls=0,wb_writes=0,configuration_writes=0))
print(json.dumps(dict(tests_exit=p.returncode,source_calls=0,telegram_calls=0,wb_writes=0)))
raise SystemExit(p.returncode)
