"""Read-only exact search minima for owner-requested continued CPC tests."""
import os
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:continue_tests:2026-11-04:minimums'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'results':{}}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO scope')
 return a
w.authorize=scope
if not w.claim(w.state):raise SystemExit('No duplicate reader')
try:
 base=w.get('ooo_agent:full_review:2026-11-04:evidence')['sources']['configurations']['data']
 for cid in [41516310,41517233]:
  cfg=base[str(cid)]
  if cfg['status']!=9 or cfg['settings']['placements']!={'search':True,'recommendations':False}:raise ValueError('Active search-only baseline required')
  ids={n['nm_id']for n in cfg['nm_settings']}
  w.state['results'][str(cid)]=w.minima(cid,ids,['search']);w.save()
 w.state.update(status='finished',finished_at=w.stamp());w.save()
except Exception as e:
 w.state.update(status='attention',error=str(e)[:1000]);w.save()
