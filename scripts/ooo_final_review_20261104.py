"""Complete read-only checks before final OOO recommendations."""
import os,datetime,json
import ooo_owner_apply_all_20261102 as w
from china_moysklad_read import read_stock
w.KEY='ooo_agent:final_review:2026-11-04:evidence'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'sources':{}}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO scope')
 return a
w.authorize=scope
if not w.claim(w.state):raise SystemExit('No duplicate review')
def read(label,fn):
 try:w.state['sources'][label]={'status':'complete','data':fn(),'observed_at':w.stamp()}
 except Exception as e:w.state['sources'][label]={'status':'unavailable','error':str(e)[:1000]}
 w.save()
read('moysklad',lambda:read_stock(['177-AngelaBag-brown','123-EmraBag-black','542-CelineaBag-darkbrown','449-AngelaBag-chocolate','658-FioreBag-brown','681-CalmiraBag-chocolate','588-ReginaBag-dbrown','122-EmraBag-red','143-ReginaBag-black']))
read('minimum_177',lambda:w.minima(39605581,{850843947},['search','recommendation']))
base=w.get('ooo_agent:morning:2026-11-04:evidence')
if base.get('status')!='finished':raise RuntimeError('Complete morning evidence required')
w.state['reviewed_morning_source']={'key':'ooo_agent:morning:2026-11-04:evidence','finished_at':base['finished_at'],'statuses':{k:v['status'] for k,v in base['sources'].items()}}
w.state.update(status='finished',finished_at=w.stamp());w.save()
print('Checks saved privately; zero WB writes')
