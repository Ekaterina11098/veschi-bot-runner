"""Exact five owner-approved growth tests, no other marketplace writes."""
import os,time,json,hashlib,datetime,copy,base64
import ooo_owner_apply_all_20261102 as w
ROOT='ooo_agent:growth_apply:2026-11-04:v1'
MANIFEST={'cabinet':'token_1','currency':'KGS','additions':[{'cid':41516310,'nm':1124312592,'placements':['search'],'bid':325},{'cid':41516310,'nm':1124312599,'placements':['search'],'bid':325},{'cid':39605581,'nm':851230666,'placements':['search','recommendations'],'bid':325}],'raises':[{'cid':40385586,'nm':1124312598,'placement':'recommendations','old':325,'new':360},{'cid':40385586,'nm':850720070,'placement':'recommendations','old':325,'new':360}],'topups':[],'pauses':[],'prices':[]}
HASH=hashlib.sha256(json.dumps(MANIFEST,sort_keys=True,separators=(',',':')).encode()).hexdigest()
w.KEY=ROOT+':execution';w.state={'status':'starting','run_id':os.environ.get('GITHUB_RUN_ID'),'started_at':w.stamp(),'steps':{},'manifest_sha256':HASH,'telegram_calls':0}
def scope():
 a=w.get(ROOT+':authorization')
 if not a or a.get('status')!='approved'or a.get('manifest')!=MANIFEST or a.get('manifest_sha256')!=HASH:raise PermissionError('Exact five-test owner approval required')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Dated approval expired')
 return a
w.authorize=scope
def run():
 scope();claims=json.loads(base64.urlsafe_b64decode(w.TOKEN.split('.')[1]+'==='))
 identities=w.database('GET','analytics_snapshots',params={'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})or[]
 if claims.get('exp',0)<time.time()or claims.get('t')is not False or int(claims.get('s',0))&(1<<30)or not claims.get('sid')or{r['payload'].get('sid')for r in identities}!={claims['sid']}:raise PermissionError('Seller/write capability mismatch')
 evidence=w.get('ooo_agent:growth_candidates:2026-11-04:2135')or{};src=evidence.get('sources',{});c=src.get('configurations',{})
 if evidence.get('status')!='finished'or c.get('status')!='complete'or time.time()-datetime.datetime.fromisoformat(c['observed_at']).timestamp()>7200:raise RuntimeError('Reviewed configuration baseline stale')
 ids=[41516310,39605581,40385586];before={cid:copy.deepcopy(c['data'][str(cid)])for cid in ids}
 for cid,v in before.items():
  if v['status']!=9 or v['currency']!='KGS'or v['bid_type']!='manual'or v['settings']['payment_type']!='cpc':raise RuntimeError('Expected active manual KGS CPC')
 for a in MANIFEST['additions']:
  if any(n['nm_id']==a['nm']for v in c['data'].values()if v['status']==9 for n in v['nm_settings']):raise RuntimeError('New SKU already active; no overlap')
  if any(not before[a['cid']]['settings']['placements'].get(p)for p in a['placements']):raise RuntimeError('Placement drift')
 for a in MANIFEST['raises']:
  n=next(n for n in before[a['cid']]['nm_settings']if n['nm_id']==a['nm'])
  if n['bids_kopecks'].get(a['placement'])!=a['old']:raise RuntimeError('Bid baseline drift')
 memberships={};bids={}
 for a in MANIFEST['additions']:
  memberships.setdefault(a['cid'],[]).append(a['nm'])
  for p in a['placements']:bids.setdefault(a['cid'],[]).append({'nm_id':a['nm'],'placement':p,'bid_kopecks':a['bid']})
 for a in MANIFEST['raises']:bids.setdefault(a['cid'],[]).append({'nm_id':a['nm'],'placement':a['placement'],'bid_kopecks':a['new']})
 mb={'nms':[{'advert_id':cid,'nms':{'add':nms,'delete':[]}}for cid,nms in memberships.items()]}
 bb={'bids':[{'advert_id':cid,'nm_bids':nms}for cid,nms in bids.items()]}
 orig=w.req
 def bounded(path,method='GET',body=None,step=None):
  ok=(step=='add_three'and method=='PATCH'and path=='/adv/v0/auction/nms'and body==mb)or(step=='set_six_placement_bids'and method=='PATCH'and path=='/api/advert/v1/bids'and body==bb)if step else method=='GET'and path.split('?')[0]=='/api/advert/v2/adverts'
  if not ok:raise PermissionError('Request outside exact five tests')
  return orig(path,method,body,step)
 w.req=bounded
 w.state.update(before=before,baseline_observed_at=c['observed_at'],manifest=MANIFEST);w.save()
 w.req('/adv/v0/auction/nms','PATCH',mb,'add_three')
 w.req('/api/advert/v1/bids','PATCH',bb,'set_six_placement_bids')
 w.state.update(status='all_writes_accepted',accepted_at=w.stamp());w.save()
 after=w.configs(ids)
 for cid in ids:
  for k in['id','status','currency','bid_type','settings','restrictions']:
   if after[cid].get(k)!=before[cid].get(k):raise RuntimeError('Unapproved campaign difference')
  if w.member_ids(after[cid])!=w.member_ids(before[cid])|set(memberships.get(cid,[])):raise RuntimeError('Membership readback mismatch')
  for old in before[cid]['nm_settings']:
   expected=copy.deepcopy(old)
   for a in MANIFEST['raises']:
    if a['cid']==cid and a['nm']==old['nm_id']:expected['bids_kopecks'][a['placement']]=a['new']
   actual=next(n for n in after[cid]['nm_settings']if n['nm_id']==old['nm_id'])
   if actual!=expected:raise RuntimeError('Unapproved existing SKU difference')
  for b in bids[cid]:
   actual=next(n for n in after[cid]['nm_settings']if n['nm_id']==b['nm_id'])
   if actual['bids_kopecks'][b['placement']]!=b['bid_kopecks']:raise RuntimeError('Exact bid readback mismatch')
 day=(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()+datetime.timedelta(days=1)).isoformat()
 w.state.update(status='verified',after=after,verified_at=w.stamp(),first_full_test_day=day,test_full_days=2);w.save()
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Expected main repository')
 if not w.claim(w.state):raise SystemExit('Existing execution retained; no replay')
 try:run()
 except Exception as e:w.state.update(status='attention',error=str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError,KeyError))else type(e).__name__);w.save()
 print(json.dumps({'status':w.state['status']}))

