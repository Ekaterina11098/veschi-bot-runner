"""Single owner-approved Nov6 bid test. No budget, start, membership or price writes."""
import os,time,json,hashlib,datetime,copy,base64
import ooo_owner_apply_all_20261102 as w
ROOT='ooo_agent:morning_apply:2026-11-06:v1'
MANIFEST={'cabinet':'token_1','currency':'KGS','raises':[{'cid':41516310,'nm':1124182933,'placement':'search','old':325,'new':360}],'topups':[],'starts':[],'pauses':[],'additions':[],'prices':[]}
HASH=hashlib.sha256(json.dumps(MANIFEST,sort_keys=True,separators=(',',':')).encode()).hexdigest()
w.KEY=ROOT+':execution'
w.state={'status':'starting','run_id':os.environ.get('GITHUB_RUN_ID'),'started_at':w.stamp(),'steps':{},'manifest':MANIFEST,'manifest_sha256':HASH,'telegram_calls':0}
def scope():
 a=w.get(ROOT+':authorization')
 if not a or a.get('status')!='approved' or a.get('manifest')!=MANIFEST or a.get('manifest_sha256')!=HASH:raise PermissionError('Exact Nov6 bid-only owner approval required')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Dated approval expired')
 return a
w.authorize=scope
def projection(c):
 return {k:copy.deepcopy(c.get(k))for k in ['id','status','currency','bid_type','settings','restrictions']}|{'nm_settings':sorted(copy.deepcopy(c['nm_settings']),key=lambda n:n['nm_id'])}
def run():
 scope()
 claims=json.loads(base64.urlsafe_b64decode(w.TOKEN.split('.')[1]+'==='))
 ids=w.database('GET','analytics_snapshots',params={'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})or[]
 if claims.get('exp',0)<time.time()or claims.get('t')is not False or int(claims.get('s',0))&(1<<30)or not claims.get('sid')or{r['payload'].get('sid')for r in ids}!={claims['sid']}:raise PermissionError('Seller/write capability mismatch')
 ev=w.get('ooo_agent:morning:2026-11-06:evidence')or{}
 c=ev.get('sources',{}).get('configurations',{})
 if ev.get('status')!='finished'or c.get('status')!='complete'or time.time()-datetime.datetime.fromisoformat(c['observed_at']).timestamp()>7200:raise RuntimeError('Reviewed configuration baseline stale')
 before=copy.deepcopy(c['data']['41516310'])
 if before['status']!=9 or before['currency']!='KGS'or before['bid_type']!='manual'or before['settings']['payment_type']!='cpc'or before['settings']['placements']!={'search':True,'recommendations':False}:raise RuntimeError('Expected active search-only manual KGS CPC')
 n=next(n for n in before['nm_settings']if n['nm_id']==1124182933)
 if n['bids_kopecks']['search']!=325:raise RuntimeError('Bid baseline drift')
 body={'bids':[{'advert_id':41516310,'nm_bids':[{'nm_id':1124182933,'placement':'search','bid_kopecks':360}]}]}
 orig=w.req
 def bounded(path,method='GET',bodyarg=None,step=None):
  ok=(step=='raise_674_search'and method=='PATCH'and path=='/api/advert/v1/bids'and bodyarg==body)if step else method=='GET'and path.split('?')[0]=='/api/advert/v2/adverts'
  if not ok:raise PermissionError('Outside single approved bid')
  return orig(path,method,bodyarg,step)
 w.req=bounded;w.state.update(before=before,baseline_observed_at=c['observed_at']);w.save()
 w.req('/api/advert/v1/bids','PATCH',body,'raise_674_search')
 w.state.update(status='accepted',accepted_at=w.stamp());w.save()
 after=w.configs([41516310])[41516310];expected=copy.deepcopy(before)
 for n in expected['nm_settings']:
  if n['nm_id']==1124182933:n['bids_kopecks']['search']=360
 if projection(after)!=projection(expected):raise RuntimeError('Exact permitted-difference readback mismatch')
 day=(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()+datetime.timedelta(days=1)).isoformat()
 w.state.update(status='verified',after=after,verified_at=w.stamp(),first_full_test_day=day,test_full_days=2);w.save()
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Expected main repository')
 if not w.claim(w.state):raise SystemExit('Existing execution retained; no replay')
 try:run()
 except Exception as e:w.state.update(status='attention',error=str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError,KeyError))else type(e).__name__);w.save()
 print(json.dumps({'status':w.state['status']}))
