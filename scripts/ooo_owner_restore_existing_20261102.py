"""Recover original OOO CPC membership and resume existing advertising only."""
import os,time,json,copy,base64
import ooo_owner_apply_all_20261102 as w
w.KEY=w.ROOT+':restore_existing'
w.state={'status':'starting','started_at':w.stamp(),'run_id':os.environ['GITHUB_RUN_ID'],'steps':{}}
def authorization():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('status')!='recovery_hold' or a.get('plan_sha256')!=w.HASH or a.get('cabinet')!='token_1':raise PermissionError('Recovery hold scope required')
 if w.datetime.datetime.now(w.datetime.timezone.utc)>=w.datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Dated recovery scope expired')
 return a
w.authorize=authorization
if not w.claim(w.state):print('Existing recovery receipt preserved');raise SystemExit(0)
try:
 a=authorization()
 for _ in range(12):
  old=w.get(w.ROOT+':apply_all') or {}
  if old.get('status')=='attention':break
  time.sleep(5)
 else:raise RuntimeError('Original executor has not stopped; no concurrent writes')
 if any(k.startswith(('deposit_','start_','apply_approved_bids','restore_existing_')) for k in old.get('steps',{})):raise RuntimeError('Unexpected later mutations; recovery needs fresh review')
 pre=w.get(w.ROOT+':preflight_cost_reduction')
 claims=json.loads(base64.urlsafe_b64decode(w.TOKEN.split('.')[1]+'==='))
 identities=w.database('GET','analytics_snapshots',params={'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100}) or []
 if not claims.get('sid') or {r['payload'].get('sid') for r in identities}!={claims['sid']}:raise PermissionError('OOO identity mismatch')
 ids=[39605581,39605579]
 before={cid:pre['before'][str(cid)] for cid in ids}
 live=w.configs(ids)
 deletes=[]
 for cid in ids:
  c=live[cid];b=before[cid]
  group='G05' if cid==39605581 else 'G11'
  added={r['nm'] for r in a['approved_candidates'] if r['group']==group}
  if c.get('currency')!='KGS' or c.get('settings')!=b['settings'] or c.get('status')!=11:raise RuntimeError('Recovery baseline changed')
  if w.member_ids(c)!=w.member_ids(b)|added:raise RuntimeError('Unexpected live membership')
  base={n['nm_id']:n for n in b['nm_settings']}
  for n in c['nm_settings']:
   if n['nm_id'] in base and n!=base[n['nm_id']]:raise RuntimeError('Original SKU settings changed')
  deletes.append({'advert_id':cid,'nms':{'add':[],'delete':sorted(added-w.member_ids(b))}})
 w.state['before_recovery']={str(k):v for k,v in live.items()};w.save()
 w.req('/adv/v0/auction/nms','PATCH',{'nms':deletes},'remove_unverified_additions')
 for cid in ids:w.req('/adv/v0/start?id='+str(cid),step='restore_'+str(cid))
 w.state.update(status='starts_accepted',accepted_at=w.stamp());w.save()
 statuses=w.inventory(force=True)
 if any(statuses.get(cid)!=9 for cid in ids):raise RuntimeError('Existing CPC start confirmation pending')
 w.state.update(status='existing_campaigns_running_verified',verified_at=w.stamp());w.save()
except Exception as e:
 w.state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);w.save()
print(json.dumps({'status':w.state['status']}))
