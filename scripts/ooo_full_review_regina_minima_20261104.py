"""Read-only remaining existing Regina/Angela minima for full review."""
import os,json,datetime
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:full_review:2026-11-04:regina_minima'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{}}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO scope')
 return a
w.authorize=scope
if not w.claim(w.state):raise SystemExit('Receipt exists')
try:
 b=w.get('ooo_agent:morning:2026-11-04:evidence')['sources']['configurations']['data']['39605581']
 ids={n['nm_id']for n in b['nm_settings']}
 w.state['result']=w.minima(39605581,ids,['search','recommendation'])
 w.state.update(status='finished',finished_at=w.stamp());w.save()
except Exception as e:
 w.state.update(status='attention',error=str(e)[:1000]);w.save()
