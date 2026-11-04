"""Exact owner-approved OOO urgent three-action test. No unrelated writes."""
import os,time,json,copy,hashlib,base64,datetime,requests
import ooo_owner_apply_all_20261102 as w
ROOT='ooo_agent:urgent_actions:2026-11-04:v1'
MANIFEST={'cabinet':'token_1','add':{'cid':41516310,'nm':1124312584,'article':'594-NoelBag-green','placement':'search','bid_minor':325,'currency':'KGS'},'raise':{'cid':40385586,'nm':1124312594,'article':'59-NoelBag-grey','placement':'recommendations','from_minor':325,'to_minor':360,'currency':'KGS'},'price':{'nm':851316021,'article':'143-ReginaBag-black','currency':'RUB','base':13000,'discount_from':45,'discount_to':46,'target':7020,'club_discount':0},'topups':[],'pauses':[]}
HASH=hashlib.sha256(json.dumps(MANIFEST,sort_keys=True,separators=(',',':')).encode()).hexdigest()
w.KEY=ROOT+':execution';w.state={'status':'starting','run_id':os.environ.get('GITHUB_RUN_ID'),'started_at':w.stamp(),'steps':{},'manifest_sha256':HASH,'telegram_calls':0}
def scope():
 a=w.get(ROOT+':authorization')
 if not a or a.get('status')!='approved'or a.get('manifest')!=MANIFEST or a.get('manifest_sha256')!=HASH:raise PermissionError('Exact urgent owner approval required')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Dated approval expired')
 return a
w.authorize=scope
def price_req(path,body=None,step=None):
 host='discounts-prices-api.wildberries.ru';bare=path.split('?')[0];method='POST'if body is not None else'GET'
 if step:
  if step!='price_143'or bare!='/api/v2/upload/task'or body!={'data':[{'nmID':851316021,'price':13000,'discount':46}]}:raise PermissionError('Price write outside scope')
  if step in w.state['steps']:raise RuntimeError('Price replay refused')
 elif bare not in['/api/v2/history/tasks','/api/v2/history/goods/task','/api/v2/list/goods/filter']:raise PermissionError('Price read outside scope')
 pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+bare).encode()).hexdigest()
 for attempt in range(3):
  w.wait_until(float((w.get(pk)or{}).get('until',0)),bare);scope()
  if step:w.state['steps'][step]={'status':'submitting','path':path,'body':body,'submitted_at':w.stamp()};w.save()
  try:r=requests.request(method,'https://'+host+path,headers={'Authorization':w.TOKEN},json=body,timeout=(10,60),allow_redirects=False)
  except requests.RequestException:
   if step:w.state['steps'][step].update(status='uncertain');w.save()
   raise RuntimeError('Unknown price transport result; no replay')from None
  raw=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
  try:delay=float(raw or 0)
  except ValueError:delay=0
  if delay>time.time()-86400:delay=max(0,delay-time.time())
  if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and delay>0):w.put(pk,{'until':time.time()+max(delay,60)+3,'basis':'provider_header'})
  if r.status_code==429:
   if step:w.state['steps'][step].update(status='rejected_429');w.save();raise RuntimeError('Price upload explicitly rejected429; no replay')
   continue
  if not r.ok:
   if step:w.state['steps'][step].update(status='rejected',http_status=r.status_code);w.save()
   raise RuntimeError('Price API HTTP '+str(r.status_code))
  data=r.json()
  if data.get('error'):raise RuntimeError('Price API rejected task')
  value=data.get('data',data)
  if step:w.state['steps'][step].update(status='accepted',response=value,accepted_at=w.stamp());w.save()
  return value
 raise RuntimeError('Price read quota pending')
def run():
 scope();claims=json.loads(base64.urlsafe_b64decode(w.TOKEN.split('.')[1]+'==='))
 identities=w.database('GET','analytics_snapshots',params={'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})or[]
 if claims.get('exp',0)<time.time()or claims.get('t')is not False or int(claims.get('s',0))&(1<<30)or{r['payload'].get('sid')for r in identities}!={claims.get('sid')}:raise PermissionError('Seller/write capability mismatch')
 source=w.get('ooo_agent:sales_decline:2026-11-04:1606:evidence')['sources'];c=source['configurations'];p=source['prices']
 if any(x.get('status')!='complete'or time.time()-datetime.datetime.fromisoformat(x['observed_at']).timestamp()>7200 for x in[c,p]):raise RuntimeError('Reviewed baseline stale')
 before={cid:copy.deepcopy(c['data'][str(cid)])for cid in[41516310,40385586]}
 if any(v['status']!=9 or v['currency']!='KGS'or v['settings']['payment_type']!='cpc'for v in before.values()):raise RuntimeError('Expected active KGS CPC required')
 if before[41516310]['settings']['placements']!={'search':True,'recommendations':False}or before[40385586]['settings']['placements']!={'search':False,'recommendations':True}:raise RuntimeError('Placement drift')
 if any(n['nm_id']==1124312584 for v in c['data'].values()for n in v['nm_settings']):raise RuntimeError('594 already advertised; no duplicate')
 n=next(n for n in before[40385586]['nm_settings']if n['nm_id']==1124312594)
 if n['bids_kopecks']['recommendations']!=325:raise RuntimeError('59 bid drift')
 goods=next(g for g in p['data']['data']['listGoods']if g['nmID']==851316021)
 if goods.get('vendorCode')!='143-ReginaBag-black'or goods['currencyIsoCode4217']!='RUB'or goods['discount']!=45 or goods['clubDiscount']!=0 or any(z['price']!=13000 or z['discountedPrice']!=7150 for z in goods['sizes']):raise RuntimeError('143 price baseline drift')
 w.state.update(before=before,price_before=goods,manifest=MANIFEST);w.save()
 add={'nms':[{'advert_id':41516310,'nms':{'add':[1124312584],'delete':[]}}]}
 bids={'bids':[{'advert_id':41516310,'nm_bids':[{'nm_id':1124312584,'placement':'search','bid_kopecks':325}]},{'advert_id':40385586,'nm_bids':[{'nm_id':1124312594,'placement':'recommendations','bid_kopecks':360}]}]}
 orig=w.req
 def bounded(path,method='GET',body=None,step=None):
  if step:
   ok=(step=='add_594'and path=='/adv/v0/auction/nms'and method=='PATCH'and body==add)or(step=='bids_594_59'and path=='/api/advert/v1/bids'and method=='PATCH'and body==bids)
  else:ok=method=='GET'and path.split('?')[0]=='/api/advert/v2/adverts'
  if not ok:raise PermissionError('Advertising request outside exact approval')
  return orig(path,method,body,step)
 w.req=bounded
 w.req('/adv/v0/auction/nms','PATCH',add,'add_594')
 w.req('/api/advert/v1/bids','PATCH',bids,'bids_594_59')
 upload=price_req('/api/v2/upload/task',{'data':[{'nmID':851316021,'price':13000,'discount':46}]},'price_143')
 if type(upload.get('id'))is not int or upload['id']<=0:raise RuntimeError('Price task ID missing; no repeat')
 w.state.update(status='all_writes_accepted',upload_id=upload['id'],all_writes_accepted_at=w.stamp());w.save()
 for _ in range(45):
  task=price_req('/api/v2/history/tasks?uploadID='+str(upload['id']))
  if task.get('uploadID')!=upload['id']:raise RuntimeError('Price task identity mismatch')
  w.state['price_task']=task;w.save()
  if task.get('status')in[3,4,5,6]:break
  time.sleep(15)
 else:raise RuntimeError('Price processing pending; do not repeat upload')
 if task['status']not in[3,5]:raise RuntimeError('Price task completed with failure')
 details=price_req('/api/v2/history/goods/task?uploadID='+str(upload['id'])+'&limit=1000&offset=0')
 items=[g for g in details.get('historyGoods',[])if g.get('nmID')==851316021]
 if details.get('uploadID')!=upload['id']or len(items)!=1 or items[0].get('errorText'):raise RuntimeError('Price details not verified')
 w.state.update(price_details=details,status='price_task_processed');w.save()
 after=w.configs([41516310,40385586])
 for cid in before:
  for k in['id','status','currency','bid_type','settings','restrictions']:
   if after[cid].get(k)!=before[cid].get(k):raise RuntimeError('Unapproved configuration difference')
  expected=w.member_ids(before[cid])|({1124312584}if cid==41516310 else set())
  if w.member_ids(after[cid])!=expected:raise RuntimeError('Membership readback mismatch')
  for b in before[cid]['nm_settings']:
   n=next(n for n in after[cid]['nm_settings']if n['nm_id']==b['nm_id']);expected=copy.deepcopy(b)
   if cid==40385586 and b['nm_id']==1124312594:expected['bids_kopecks']['recommendations']=360
   if n!=expected:raise RuntimeError('Unapproved SKU difference')
 if next(n for n in after[41516310]['nm_settings']if n['nm_id']==1124312584)['bids_kopecks']['search']!=325:raise RuntimeError('594 bid readback mismatch')
 w.state.update(status='advertising_verified',after=after,advertising_verified_at=w.stamp());w.save()
 fresh=price_req('/api/v2/list/goods/filter?limit=1000&offset=0&filterNmID=851316021').get('listGoods',[])
 if len(fresh)!=1:raise RuntimeError('143 exact price row missing')
 g=fresh[0]
 if g['nmID']!=851316021 or g['vendorCode']!='143-ReginaBag-black'or g['currencyIsoCode4217']!='RUB'or g['discount']!=46 or g['clubDiscount']!=0 or any(z['price']!=13000 or z['discountedPrice']!=7020 for z in g['sizes']):raise RuntimeError('Final price readback mismatch')
 w.state.update(status='verified',price_after=g,verified_at=w.stamp(),first_full_test_day='2026-11-05',advertising_test_full_days=2,price_test_full_days=3);w.save()
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Expected main repository')
 if not w.claim(w.state):raise SystemExit('Existing execution retained; no replay')
 try:run()
 except Exception as e:w.state.update(status='attention',error=str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError,KeyError))else type(e).__name__);w.save()
 print(json.dumps({'status':w.state['status']}))

