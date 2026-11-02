"""One-time owner-authorized additional OOO funding, capped at 8000 KGS."""
import os,time,json,datetime,base64
import ooo_owner_apply_all_20261102 as w
ROOT='ooo_agent:topup_8000:2026-11-02'
w.KEY=ROOT+':execution'
AMOUNTS={40385586:3200,41515989:1200,41516310:1200,41516903:1200,41517233:1200}
w.state={'status':'starting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'max_total_kgs':8000}
def scope():
 a=w.get(ROOT+':authorization')
 if not a or a.get('status')!='approved' or a.get('cabinet')!='token_1' or a.get('quote')!='пополни все, что нужно':raise PermissionError('Exact owner additional-funding approval required')
 if {int(k):v for k,v in a.get('amounts_kgs',{}).items()}!=AMOUNTS or a.get('max_total_kgs')!=8000 or sum(AMOUNTS.values())!=8000:raise PermissionError('Funding scope mismatch')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Funding authorization expired')
 return a
w.authorize=scope
if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Public main only')
if not w.claim(w.state):print('Prior additional-funding receipt preserved; no replay');raise SystemExit(0)
try:
 scope()
 claims=json.loads(base64.urlsafe_b64decode(w.TOKEN.split('.')[1]+'==='))
 identities=w.database('GET','analytics_snapshots',params={'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100}) or []
 if claims.get('exp',0)<time.time() or claims.get('t') is not False or int(claims.get('s',0))&(1<<30) or not claims.get('sid') or {r['payload'].get('sid') for r in identities}!={claims['sid']}:raise PermissionError('OOO identity/write capability mismatch')
 cached=w.get(w.ROOT+':evening_budget_check') or {}
 observed=datetime.datetime.fromisoformat(cached.get('observed_at','2000-01-01T00:00:00+00:00')).timestamp()
 if cached.get('status')=='verified' and time.time()-observed<300:
  before={cid:cached['budgets_kgs'][str(cid)] for cid in AMOUNTS};basis='native_batched_cache_under_five_minutes'
 else:before=w.budget(list(AMOUNTS));basis='native_fresh_batch'
 # A rise over the explicitly reviewed baseline indicates a possible manual topup.
 reviewed={40385586:1796,41515989:1590,41516310:1996,41516903:1870,41517233:1693}
 if any(before[cid]>reviewed[cid]+1 for cid in AMOUNTS):raise RuntimeError('Balance increased since owner review; avoid duplicating possible manual topups')
 w.state.update(budgets_before={str(k):v for k,v in before.items()},baseline_basis=basis);w.save()
 wallet=w.req('/adv/v1/balance')
 if wallet.get('currency')!='KGS':raise RuntimeError('Wallet currency mismatch')
 source=0 if wallet.get('balance',0)>=8000 else 1 if wallet.get('net',0)>=8000 else None
 if source is None:raise RuntimeError('Wallet lacks 8000 KGS in a single funding source')
 w.state['funding_source']=source;w.save()
 for cid,amount in AMOUNTS.items():
  name='deposit_'+str(cid)
  for attempt in range(4):
   scope()
   accepted=sum(AMOUNTS[int(k.split('_')[1])] for k,v in w.state['steps'].items() if k.startswith('deposit_') and v.get('status')=='accepted')
   if accepted+amount>8000:raise PermissionError('Total one-time cap exceeded')
   try:
    w.req('/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=amount,type=source),name)
    break
   except RuntimeError:
    step=w.state['steps'].get(name,{})
    if step.get('status')!='rejected_429' or attempt==3:raise
    # Only an explicit HTTP 429 rejection may be retried, after the shared wait.
  w.state['accepted_total_kgs']=sum(AMOUNTS[int(k.split('_')[1])] for k,v in w.state['steps'].items() if k.startswith('deposit_') and v.get('status')=='accepted');w.save()
 w.state.update(status='all_deposits_accepted',accepted_at=w.stamp());w.save()
 after=w.budget(list(AMOUNTS))
 w.state.update(status='complete',budgets_after={str(k):v for k,v in after.items()},observed_at=w.stamp(),completed_at=w.stamp());w.save()
except Exception as e:
 w.state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);w.save()
print(json.dumps({'status':w.state['status'],'accepted_total_kgs':w.state.get('accepted_total_kgs',0)}))
