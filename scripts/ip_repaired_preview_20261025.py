"""Build exact repaired daily preview from saved data; never send or collect."""
import os,sys,json,base64,hashlib
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store
from advertising_budget_evidence import load_daily_table_view
from advertising_daily_png import render_daily_png
from stock_deploy_support import seal
proof=dict(complete=False,source_calls=0,wb_writes=0,telegram_calls=0)
try:
 view=load_daily_table_view(store,datetime.now(timezone.utc))
 if view['period']!='2026-10-24' or view['observed_day']!='2026-10-25':raise ValueError('Exact authorized day only')
 if len(view['campaigns'])!=11 or not all(x['metrics_complete'] and x.get('weekly_spend') is not None for x in view['campaigns']):raise ValueError('Complete 11 campaign daily and weekly coverage required')
 proof['view']=view
 images=render_daily_png(view,Path(os.environ['RUNNER_TEMP'])/'ip-repaired-preview')
 proof['images']=[dict(kind=x['kind'],sha256=hashlib.sha256(Path(x['path']).read_bytes()).hexdigest(),data=base64.b64encode(Path(x['path']).read_bytes()).decode()) for x in images]
 if [x['kind'] for x in proof['images']]!=['drr','budgets']:raise ValueError('Expected exact PNG pair')
 proof['complete']=True
except Exception as ex:proof['error']=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__
finally:
 seal('ip-repaired-preview-20261025',proof)
 print(json.dumps({k:proof.get(k) for k in ['complete','error','source_calls','wb_writes','telegram_calls']}))
if not proof['complete']:raise SystemExit(1)
