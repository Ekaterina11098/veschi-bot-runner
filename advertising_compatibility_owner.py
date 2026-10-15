"""Owner-authorized advertising preparation. No source, Telegram, or marketplace calls."""
import os,sys,json,subprocess,time
from pathlib import Path
from stock_deploy_support import seal,error
root=Path(__file__).parent
source=root/'combined';pr=root/'pr19'
report={'main':'1b4201067880e379d8dacbe5f6ca3f9848d6ffb0','pr19':'30ac7853a245ae6ea7cbbf069ab15f051db9fe5b','source_calls':0,'telegram_calls':0,'wb_writes':0}
def command(args):
 p=subprocess.run(args,cwd=source,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 return {'exit':p.returncode,'log':p.stdout}
try:
 report['fetch']=command(['git','fetch',str(pr),'HEAD'])
 report['merge']=command(['git','-c','user.name=ReadOnlyAcceptance','-c','user.email=acceptance@invalid.local','merge','--no-commit','--no-ff','FETCH_HEAD'])
 if report['merge']['exit']:raise RuntimeError('Combined main/PR19 has conflicts; inspect sealed report')
 report['changed']=command(['git','diff','--cached','--name-status'])
 child=dict(os.environ)
 for k in list(child):
  if any(k.startswith(p) for p in ('SUPABASE_','WB_','MPSTATS_','MOYSKLAD_','TELEGRAM_','ADVERTISING_','OPENAI_')):child.pop(k)
 testcode="""import socket,unittest,sys
from unittest.mock import patch
patterns=('test_ip_offline_decision_quality.py','test_ip_full_offline_pipeline.py','test_ip_daily_recommendations.py','test_ip_campaign_audit.py','test_ip_final_status.py','test_ip_delivery_boundary.py','test_ip_working_mode_replay.py','test_ip_completed_investigations.py','test_advertising_experiments.py','test_experiment_data_quality.py','test_experiment_journal_coverage.py','test_profit_stability.py','test_payload_storage.py','test_storage_collection_gate.py','test_mpstats_primary_policy.py','test_sku_finance_isolation.py','test_ip_data_preservation.py','test_ip_snapshot_periods.py','test_ip_unknown_identity_controls.py','test_ip_native_checkpoints.py','test_ip_price_event_analysis.py')
suite=unittest.TestSuite()
for p in patterns:suite.addTests(unittest.defaultTestLoader.discover('tests',pattern=p))
with patch.object(socket.socket,'connect',side_effect=AssertionError('External network forbidden')):
 result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""
 p=subprocess.run([sys.executable,'-c',testcode],cwd=source,env=child,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 report['regressions']={'exit':p.returncode,'log':p.stdout}
 report['compatible']=p.returncode==0
except Exception as exc:report['error']=error(exc)
finally:
 seal('advertising-compatibility',report)
 print(json.dumps({'compatible':report.get('compatible',False),'merge_exit':report.get('merge',{}).get('exit'),'tests_exit':report.get('regressions',{}).get('exit'),'source_calls':0,'wb_writes':0,'telegram_calls':0}))
