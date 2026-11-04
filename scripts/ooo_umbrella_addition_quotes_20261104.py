"""Read-only quote for best non-member umbrella candidates; never changes membership."""
import os,time
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:full_review:2026-11-04:umbrella_addition_quotes'
w.state={'status':'waiting_other_minimum_reader','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{}}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO scope')
 return a
w.authorize=scope
if not w.claim(w.state):raise SystemExit('No duplicate quote')
while (w.get('ooo_agent:full_review:2026-11-04:regina_minima')or{}).get('status')not in ['finished','attention']:
 time.sleep(20)
try:
 w.state['result']=w.minima(39605579,{863423589,863423593,863551851},['recommendation'])
 w.state.update(status='finished',finished_at=w.stamp());w.save()
except Exception as e:
 w.state.update(status='unavailable',error=str(e)[:1200],finished_at=w.stamp());w.save()
