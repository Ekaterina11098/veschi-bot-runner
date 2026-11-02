"""Read-only OOO state verification after owner manual restore."""
import os,json
import ooo_owner_apply_all_20261102 as w
w.KEY=w.ROOT+':status_after_manual_restore'
w.state={'status':'starting','run_id':os.environ['GITHUB_RUN_ID'],'steps':{},'started_at':w.stamp()}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO scope missing')
 return a
w.authorize=scope
if not w.claim(w.state):print('Existing read-only receipt preserved');raise SystemExit(0)
try:
 a=scope();old=w.get(w.ROOT+':apply_all')
 ids=[39605579,39605581,39605582,40385586]+[int(k) for k in old['new_campaigns']]
 cs=w.configs(ids)
 w.state.update(status='verified',observed_at=w.stamp(),configurations={str(k):v for k,v in cs.items()},owner_manual_restore=a.get('owner_manual_restore'))
 w.save()
except Exception as e:
 w.state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);w.save()
print(json.dumps({'status':w.state['status']}))
