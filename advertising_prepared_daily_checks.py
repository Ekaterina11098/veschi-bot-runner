"""Offline check of prepared public runner; never enables a daily run."""
import os,sys,json,subprocess
from pathlib import Path
from stock_deploy_support import seal,error
root=Path(__file__).parent;report=dict(source_calls=0,telegram_calls=0,wb_writes=0)
try:
 prepared=root/'prepared-daily'
 workflow=(prepared/'.github/workflows/advertising-daily-prepared.yml').read_text()
 assert not any(line.strip().startswith('schedule:') and not line.strip().startswith('#') for line in workflow.splitlines())
 assert "IP_DAILY_ADVERTISING_ENABLED == 'true'" in workflow
 assert "IP_LIMITED_TELEGRAM_DELIVERY: 'false'" in workflow and "ADVERTISING_EXECUTION_ENABLED: 'false'" in workflow
 env={k:v for k,v in os.environ.items() if not k.startswith(('SUPABASE_','WB_','MPSTATS_','TELEGRAM_','ADVERTISING_','OPENAI_'))}
 env['IP_DAILY_ADVERTISING_ENABLED']='false';env['PYTHONPATH']=str(root/'private-source')
 code="import runpy,socket;from unittest.mock import patch\nwith patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden in disabled daily runtime')):runpy.run_path("+repr(str(prepared/'advertising_daily_owner.py'))+",run_name='__main__')"
 p=subprocess.run([sys.executable,'-c',code],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 report['disabled_runtime']=dict(exit=p.returncode,log=p.stdout)
 assert p.returncode==0
 assert json.loads(p.stdout.strip())==dict(enabled=False,source_calls=0,telegram_calls=0,wb_writes=0)
 report['verified']=True;report['public_head']='c6bcabe3e56b5e32c03008ebb7ec422a316b7472'
except Exception as exc:report['error']=error(exc)
finally:
 seal('advertising-daily-prepared-checks',report)
 print(json.dumps(dict(verified=report.get('verified',False),source_calls=0,telegram_calls=0,wb_writes=0)))
