"""OOO owner-requested budget check. Read-only WB endpoint."""
import os,json
import ooo_owner_apply_all_20261102 as w
w.KEY=w.ROOT+':evening_budget_check'
w.state={'status':'starting','run_id':os.environ['GITHUB_RUN_ID'],'steps':{},'started_at':w.stamp()}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO scope missing')
 return a
w.authorize=scope
if not w.claim(w.state):print('Existing budget check preserved');raise SystemExit(0)
try:
 a=scope();old=w.get(w.ROOT+':apply_all')
 ids=[39605579,39605581,39605582,40385586]+[int(k) for k in old['new_campaigns']]
 b=w.budget(ids)
 w.state.update(status='verified',observed_at=w.stamp(),budgets_kgs={str(k):v for k,v in b.items()});w.save()
except Exception as e:
 w.state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);w.save()
print(json.dumps({'status':w.state['status']}))
