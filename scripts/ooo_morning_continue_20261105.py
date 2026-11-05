"""Exact owner-approved Nov5 OOO report actions, with no-replay money receipts."""
import os,time,json,hashlib,datetime,copy,base64
import ooo_owner_apply_all_20261102 as w
ROOT='ooo_agent:morning_apply:2026-11-05:v2'
MANIFEST={'cabinet':'token_1','currency':'KGS','raises':[{'cid':41515989,'nm':863207382,'placement':'search','old':325,'new':360},{'cid':40385586,'nm':1124182927,'placement':'recommendations','old':325,'new':360}],'topups':[{'cid':41515989,'amount':2000},{'cid':41517533,'amount':1500}],'starts':[],'pauses':[],'prices':[]}
HASH=hashlib.sha256(json.dumps(MANIFEST,sort_keys=True,separators=(',',':')).encode()).hexdigest()
w.KEY=ROOT+':execution';w.state={'status':'starting','run_id':os.environ.get('GITHUB_RUN_ID'),'started_at':w.stamp(),'steps':{},'manifest_sha256':HASH,'telegram_calls':0}
def scope():
 a=w.get(ROOT+':authorization')
 if not a or a.get('status')!='approved'or a.get('manifest')!=MANIFEST or a.get('manifest_sha256')!=HASH:raise PermissionError('Exact Nov5 owner approval required')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Dated approval expired')
 return a
w.authorize=scope
def projection(c):return {k:copy.deepcopy(c.get(k))for k in['id','status','currency','bid_type','settings','restrictions']}|{'nm_settings':sorted(copy.deepcopy(c['nm_settings']),key=lambda n:n['nm_id'])}
def run():
 scope();claims=json.loads(base64.urlsafe_b64decode(w.TOKEN.split('.')[1]+'==='))
 identities=w.database('GET','analytics_snapshots',params={'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})or[]
 if claims.get('exp',0)<time.time()or claims.get('t')is not False or int(claims.get('s',0))&(1<<30)or not claims.get('sid')or{r['payload'].get('sid')for r in identities}!={claims['sid']}:raise PermissionError('Seller/write capability mismatch')
 source=w.get('ooo_agent:morning:2026-11-05:evidence')['sources'];c=source['configurations'];b=source['budgets'];ids=[39605581,41515989,40385586,41517533]
 if any(s['status']!='complete'or time.time()-datetime.datetime.fromisoformat(s['observed_at']).timestamp()>7200 for s in[c,b]):raise RuntimeError('Reviewed Nov5 baseline stale')
 before={cid:copy.deepcopy(c['data'][str(cid)])for cid in ids}
 if before[39605581]['status']!=11 or b['data']['39605581']!=0 or any(before[cid]['status']!=9 for cid in ids if cid!=39605581):raise RuntimeError('Reviewed campaign status/budget drift')
 if any(v['currency']!='KGS'or v['bid_type']!='manual'or v['settings']['payment_type']!='cpc'for v in before.values()):raise RuntimeError('Expected KGS CPC campaigns')
 for a in MANIFEST['raises']:
  n=next(n for n in before[a['cid']]['nm_settings']if n['nm_id']==a['nm'])
  if n['bids_kopecks'][a['placement']]!=a['old']:raise RuntimeError('Current bid drift')
 body={'bids':[{'advert_id':a['cid'],'nm_bids':[{'nm_id':a['nm'],'placement':a['placement'],'bid_kopecks':a['new']}]}for a in MANIFEST['raises']]}
 funding={a['cid']:a['amount']for a in MANIFEST['topups']};orig=w.req
 def bounded(path,method='GET',bodyarg=None,step=None):
  if step=='raise_209_668':ok=method=='PATCH'and path=='/api/advert/v1/bids'and bodyarg==body
  elif step and step.startswith('deposit_'):
   cid=int(step.split('_')[1]);ok=cid in funding and path=='/adv/v1/budget/deposit?id='+str(cid)and method=='POST'and bodyarg=={'sum':funding[cid],'type':w.state.get('funding_source')}and bodyarg['type']in[0,1]
  elif step=='start_39605581':ok=False
  elif step:ok=False
  else:ok=(method,path.split('?')[0])in{('GET','/adv/v1/balance'),('GET','/api/advert/v2/adverts'),('POST','/api/advert/v2/budget')}
  if not ok:raise PermissionError('Request outside approved Nov5 package')
  return orig(path,method,bodyarg,step)
 w.req=bounded
 w.state.update(before=before,funding_before=b['data'],manifest=MANIFEST);w.save()
 parent=w.get('ooo_agent:morning_apply:2026-11-05:v1:execution')or{}
 owner=w.get('ooo_agent:morning_apply:2026-11-05:owner_manual_start')or{}
 if not owner.get('owner_reported')or owner.get('cid')!=39605581 or parent.get('status')!='attention':raise RuntimeError('Original actor must be stopped after owner manual start')
 steps=parent.get('steps',{})
 if steps.get('deposit_39605581',{}).get('status')!='accepted'or steps['deposit_39605581']['body']['sum']!=4500:raise RuntimeError('Accepted4500receipt required')
 if any(steps.get('deposit_'+str(cid),{}).get('status')not in[None,'rejected_429']for cid in funding):raise RuntimeError('Remaining deposit outcome not safe to continue')
 if 'start_39605581'in steps or 'raise_209_668'in steps:raise RuntimeError('Original actor advanced unexpectedly')
 wallet=parent['wallet_before'];funding_source=parent['funding_source']
 if wallet.get('currency')!='KGS'or funding_source not in[0,1]or wallet.get('balance'if funding_source==0 else'net',0)<8000:raise RuntimeError('Original funding source proof invalid')
 w.state.update(owner_manual_start=owner,prior_4500_receipt=steps['deposit_39605581'],prior_execution='ooo_agent:morning_apply:2026-11-05:v1:execution');w.save()
 w.state.update(wallet_before=wallet,funding_source=funding_source);w.save()
 # Explicit429 is a known rejection, so only that exact rejected step may continue after Retry-After.
 for cid,amount in funding.items():
  step='deposit_'+str(cid)
  for attempt in range(3):
   try:w.req('/adv/v1/budget/deposit?id='+str(cid),'POST',{'sum':amount,'type':funding_source},step);break
   except RuntimeError:
    if w.state['steps'].get(step,{}).get('status')!='rejected_429'or attempt==2:raise
  else:raise RuntimeError('Funding rejected after allowed reviewed continuations')
 w.state.update(status='funding_accepted',funding_accepted_at=w.stamp());w.save()
 w.req('/api/advert/v1/bids','PATCH',body,'raise_209_668')
 w.state.update(status='all_writes_accepted',accepted_at=w.stamp());w.save()
 after=w.configs(ids);expected=copy.deepcopy(before);expected[39605581]['status']=9
 for a in MANIFEST['raises']:
  for n in expected[a['cid']]['nm_settings']:
   if n['nm_id']==a['nm']:n['bids_kopecks'][a['placement']]=a['new']
 if any(projection(after[cid])!=projection(expected[cid])for cid in ids):raise RuntimeError('Exact permitted-difference readback mismatch')
 w.state.update(status='advertising_verified',after=after,advertising_verified_at=w.stamp());w.save()
 balances=w.budget([39605581]+list(funding))
 if any(v<=0 for v in balances.values()):raise RuntimeError('Accepted funding but positive balances not verified')
 day=(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()+datetime.timedelta(days=1)).isoformat()
 w.state.update(status='verified',funding_after=balances,verified_at=w.stamp(),first_full_bid_test_day=day,bid_test_full_days=2);w.save()
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Expected main repository')
 if not w.claim(w.state):raise SystemExit('Existing dated execution retained; no replay')
 try:run()
 except Exception as e:w.state.update(status='attention',error=str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError,KeyError))else type(e).__name__);w.save()
 print(json.dumps({'status':w.state['status']}))



