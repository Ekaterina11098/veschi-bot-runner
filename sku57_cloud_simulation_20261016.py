"""Two-process cloud restart simulation; only local synthetic fixtures, no DB or network."""
import sys,os,json,importlib.util,socket
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from stock_deploy_support import seal
os.chdir(ROOT/'private-source')
p=Path('tests/test_sku_membership_recovery.py')
s=importlib.util.spec_from_file_location('actual_offline_core',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
f=Path(os.environ['RUNNER_TEMP'])/'sku57-synthetic-not-executable.json'
port=m.Port()
with patch.object(socket.socket,'connect',side_effect=AssertionError('No network in simulation')):
 if sys.argv[1]=='exclude':
  a=m.action();a['id']='simulation-only-not-a-production-action'
  m.advance(a,port,m.T,enabled=True);m.advance(a,port,m.T,enabled=True)
  assert port.state['phase']=='excluded' and port.request_count==1
  f.write_text(json.dumps(dict(simulation_only=True,action=a,state=port.state,campaign=port.c,request_count=port.request_count)))
  seal('sku57-simulation-exclude',dict(simulation_only=True,persisted_local_fixture=True,phase=port.state['phase'],real_wb_calls=0,production_rows_created=0))
 else:
  data=json.loads(f.read_text());assert data['simulation_only']
  port.state=data['state'];port.c=data['campaign'];port.request_count=data['request_count']
  # New Python process wakes seven minutes late, using persisted prior state.
  at=m.T+timedelta(hours=24,minutes=7)
  for _ in range(4):m.advance(data['action'],port,at,enabled=True)
  assert port.state['phase']=='restored' and port.request_count==2
  assert any(x['nm_id']==7 for x in port.c['nm_settings'])
  assert next(x for x in port.c['nm_settings'] if x['nm_id']==m.NM)['bids_kopecks']['recommendations']==10500
  seal('sku57-simulation-resume',dict(simulation_only=True,separate_process=True,wakeup_delay_seconds=420,phase=port.state['phase'],other_member_preserved=True,real_wb_calls=0,production_rows_created=0,total_fake_patch_calls=port.request_count))
 print(json.dumps(dict(simulation_only=True,phase=port.state['phase'],real_wb_calls=0,production_rows_created=0)))
