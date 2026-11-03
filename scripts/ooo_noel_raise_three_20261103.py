"""Exact owner-approved search bid increase for three existing Noel SKUs."""
import os,time,json,copy,datetime,base64
import ooo_owner_apply_all_20261102 as w
ROOT='ooo_agent:noel_raise_360:2026-11-03'
CID=41516310
IDS={1124312602,850572765,1124312585}
w.KEY=ROOT+':execution'
w.state={'status':'starting','run_id':os.environ['GITHUB_RUN_ID'],'steps':{},'started_at':w.stamp()}
def scope():
 a=w.get(ROOT+':authorization')
 if not a or a.get('status')!='approved' or a.get('cabinet')!='token_1' or a.get('campaign_id')!=CID or set(a.get('nm_ids',[]))!=IDS or a.get('placement')!='search' or a.get('from_minor')!=325 or a.get('to_minor')!=360 or a.get('currency')!='KGS':raise PermissionError('Exact three-SKU owner approval required')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Dated bid approval expired')
 return a
w.authorize=scope
def projection(c):
 return {k:copy.deepcopy(c.get(k)) for k in ('id','status','currency','bid_type','settings','restrictions')}|{'nm_settings':sorted(copy.deepcopy(c['nm_settings']),key=lambda n:n['nm_id'])}
if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Public main only')
if not w.claim(w.state):print('Existing exact bid receipt preserved; no replay');raise SystemExit(0)
try:
 scope()
 claims=json.loads(base64.urlsafe_b64decode(w.TOKEN.split('.')[1]+'==='))
 identities=w.database('GET','analytics_snapshots',params={'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100}) or []
 if claims.get('exp',0)<time.time() or claims.get('t') is not False or int(claims.get('s',0))&(1<<30) or not claims.get('sid') or {r['payload'].get('sid') for r in identities}!={claims['sid']}:raise PermissionError('Seller/write capability mismatch')
 cached=(w.get('ooo_agent:sales_decline:2026-11-03:evidence') or {}).get('sources',{}).get('configurations',{})
 if cached.get('status')=='complete' and time.time()-datetime.datetime.fromisoformat(cached['observed_at']).timestamp()<1800:
  before=cached['data'][str(CID)];basis='verified_native_cache_under_30_minutes'
 else:before=w.configs([CID])[CID];basis='fresh_native'
 if before.get('id')!=CID or before.get('status')!=9 or before.get('currency')!='KGS' or before.get('bid_type')!='manual' or before.get('settings',{}).get('payment_type')!='cpc' or before['settings'].get('placements')!={'search':True,'recommendations':False}:raise PermissionError('Expected active search-only KGS CPC campaign required')
 ns={n['nm_id']:n for n in before['nm_settings']}
 if not IDS<=set(ns) or any(ns[n]['bids_kopecks'].get('search')!=325 for n in IDS):raise RuntimeError('Membership or current bid drift; no blind overwrite')
 w.state.update(before=before,baseline_basis=basis);w.save()
 minimum=w.minima(CID,IDS,['search'])
 if any(v['search']>360 for v in minimum.values()):raise RuntimeError('Native minimum exceeds approved 360; no raise')
 body={'bids':[{'advert_id':CID,'nm_bids':[{'nm_id':nm,'bid_kopecks':360,'placement':'search'} for nm in sorted(IDS)]}]}
 w.req('/api/advert/v1/bids','PATCH',body,'raise_three_search_bids')
 w.state.update(status='bid_update_accepted',accepted_at=w.stamp());w.save()
 after=w.configs([CID])[CID]
 expected=copy.deepcopy(before)
 for n in expected['nm_settings']:
  if n['nm_id'] in IDS:n['bids_kopecks']['search']=360
 if projection(after)!=projection(expected):raise RuntimeError('Exact permitted-difference readback mismatch; no further changes')
 w.state.update(status='verified',after=after,verified_at=w.stamp());w.save()
except Exception as e:
 w.state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);w.save()
print(json.dumps({'status':w.state['status']}))
