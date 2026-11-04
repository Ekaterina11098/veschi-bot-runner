"""Single dated owner-approved execution; exact scope and durable no-replay receipts."""
import os,time,json,copy,datetime,base64,hashlib
import ooo_owner_apply_all_20261102 as w
ROOT='ooo_agent:approved_actions:2026-11-04:v1'
MANIFEST={'cabinet':'token_1','currency':'KGS','raises':[
 {'cid':39605579,'nm':863502844,'placement':'recommendations','old':270,'new':300},
 {'cid':39605579,'nm':863502834,'placement':'recommendations','old':270,'new':300},
 {'cid':41516310,'nm':1124182932,'placement':'search','old':325,'new':360},
 {'cid':41516310,'nm':851150199,'placement':'search','old':325,'new':360},
 {'cid':41516310,'nm':850659971,'placement':'search','old':325,'new':360},
 {'cid':41517233,'nm':1028594711,'placement':'search','old':325,'new':360},
 {'cid':41517233,'nm':1124152097,'placement':'search','old':325,'new':360},
 {'cid':41517233,'nm':1124251055,'placement':'search','old':325,'new':360}],
 'exclusions':[{'cid':39605581,'nm':863222654}],
 'topups':[{'cid':39605581,'amount':3000}],'pauses':[],'starts':[]}
HASH=hashlib.sha256(json.dumps(MANIFEST,sort_keys=True,separators=(',',':')).encode()).hexdigest()
w.KEY=ROOT+':execution';w.state={'status':'starting','run_id':os.environ.get('GITHUB_RUN_ID'),'started_at':w.stamp(),'steps':{},'manifest_sha256':HASH,'telegram_calls':0}
def scope():
 a=w.get(ROOT+':authorization')
 if not a or a.get('status')!='approved' or a.get('manifest')!=MANIFEST or a.get('manifest_sha256')!=HASH:raise PermissionError('Exact current owner approval required')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Dated approval expired')
 return a
w.authorize=scope
def projection(c):
 return {k:copy.deepcopy(c.get(k))for k in ('id','status','currency','bid_type','settings','restrictions')}|{'nm_settings':sorted(copy.deepcopy(c['nm_settings']),key=lambda n:n['nm_id'])}
def execute():
 scope()
 claims=json.loads(base64.urlsafe_b64decode(w.TOKEN.split('.')[1]+'==='))
 identities=w.database('GET','analytics_snapshots',params={'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})or[]
 if claims.get('exp',0)<time.time()or claims.get('t')is not False or int(claims.get('s',0))&(1<<30)or not claims.get('sid')or{r['payload'].get('sid')for r in identities}!={claims['sid']}:raise PermissionError('Seller/write capability mismatch')
 e=w.get('ooo_agent:full_review:2026-11-04:evidence')or{}
 source=e.get('sources',{}).get('configurations',{})
 ids=[39605579,39605581,41516310,41517233]
 if source.get('status')!='complete'or time.time()-datetime.datetime.fromisoformat(source['observed_at']).timestamp()>7200:raise RuntimeError('Reviewed native configuration cache stale; no blind execution')
 before={cid:copy.deepcopy(source['data'][str(cid)])for cid in ids}
 for cid,c in before.items():
  if c.get('id')!=cid or c.get('status')!=9 or c.get('currency')!='KGS'or c.get('bid_type')!='manual'or c.get('settings',{}).get('payment_type')!='cpc':raise RuntimeError('Reviewed active KGS CPC configuration required')
 for a in MANIFEST['raises']:
  c=before[a['cid']];n=next((n for n in c['nm_settings']if n['nm_id']==a['nm']),None)
  if not n or not c['settings']['placements'].get(a['placement'])or n['bids_kopecks'].get(a['placement'])!=a['old']:raise RuntimeError('Current bid/membership drift')
 if 863222654 not in w.member_ids(before[39605581])or len(w.member_ids(before[39605581]))<2:raise RuntimeError('Exclusion baseline mismatch')
 # Reuse the already confirmed category and placement minima; no additional minimum requests.
 um=e['sources']['minimum_umbrellas']['data']
 for a in MANIFEST['raises']:
  if a['cid']==39605579 and um[str(a['nm'])]['recommendation']>a['new']:raise RuntimeError('Approved umbrella bid below cached minimum')
  if a['cid']!=39605579 and a['new']<325:raise RuntimeError('Approved bag bid below confirmed category minimum')
 grouped={}
 for a in MANIFEST['raises']:grouped.setdefault(a['cid'],[]).append({'nm_id':a['nm'],'bid_kopecks':a['new'],'placement':a['placement']})
 bid_body={'bids':[{'advert_id':cid,'nm_bids':v}for cid,v in grouped.items()]}
 delete_body={'nms':[{'advert_id':39605581,'nms':{'add':[],'delete':[863222654]}}]}
 original=w.req
 def bounded(path,method='GET',body=None,step=None):
  if step:
   if step=='raise_eight':ok=method=='PATCH'and path=='/api/advert/v1/bids'and body==bid_body
   elif step=='exclude_588':ok=method=='PATCH'and path=='/adv/v0/auction/nms'and body==delete_body
   elif step=='deposit_3000':ok=method=='POST'and path=='/adv/v1/budget/deposit?id=39605581'and body=={'sum':3000,'type':w.state.get('funding_source')}and body['type']in(0,1)
   else:ok=False
   if not ok:raise PermissionError('Write outside exact consolidated approval')
  elif (method,path.split('?')[0])not in{('GET','/api/advert/v2/adverts'),('GET','/adv/v1/balance'),('POST','/api/advert/v2/budget')}:raise PermissionError('Read outside required verification')
  return original(path,method,body,step)
 w.req=bounded
 w.state.update(before=before,baseline_observed_at=source['observed_at'],baseline_basis='reviewed_native_cache_under_two_hours',manifest=MANIFEST);w.save()
 w.req('/api/advert/v1/bids','PATCH',bid_body,'raise_eight')
 w.req('/adv/v0/auction/nms','PATCH',delete_body,'exclude_588')
 w.state.update(status='bids_and_exclusion_accepted',advertising_accepted_at=w.stamp());w.save()
 wallet=w.req('/adv/v1/balance')
 if wallet.get('currency')!='KGS':raise RuntimeError('Funding wallet currency mismatch')
 funding_source=0 if wallet.get('balance',0)>=3000 else 1 if wallet.get('net',0)>=3000 else None
 if funding_source is None:raise RuntimeError('Insufficient existing advertising wallet for approved 3000 KGS')
 w.state.update(funding_source=funding_source,wallet_before=wallet);w.save()
 w.req('/adv/v1/budget/deposit?id=39605581','POST',{'sum':3000,'type':funding_source},'deposit_3000')
 w.state.update(status='all_writes_accepted',all_writes_accepted_at=w.stamp());w.save()
 # Shared Retry-After is respected by the helper. No repeated writes while waiting.
 after=w.configs(ids)
 expected=copy.deepcopy(before)
 for a in MANIFEST['raises']:
  for n in expected[a['cid']]['nm_settings']:
   if n['nm_id']==a['nm']:n['bids_kopecks'][a['placement']]=a['new']
 expected[39605581]['nm_settings']=[n for n in expected[39605581]['nm_settings']if n['nm_id']!=863222654]
 if any(projection(after[cid])!=projection(expected[cid])for cid in ids):raise RuntimeError('Exact permitted-difference readback mismatch; no additional writes')
 w.state.update(status='advertising_verified',after=after,advertising_verified_at=w.stamp());w.save()
 balances=w.budget([39605581])
 if balances[39605581]<=0:raise RuntimeError('Deposit accepted but positive campaign balance not verified')
 w.state.update(status='verified',funding_after=balances,verified_at=w.stamp(),first_full_post_change_day=(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()+datetime.timedelta(days=1)).isoformat());w.save()
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Expected repository/main required')
 if not w.claim(w.state):print('Existing execution receipt retained; no replay');raise SystemExit(0)
 try:execute()
 except Exception as e:
  w.state.update(status='attention',error=str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError,KeyError))else type(e).__name__);w.save()
 print(json.dumps({'status':w.state['status']}))

