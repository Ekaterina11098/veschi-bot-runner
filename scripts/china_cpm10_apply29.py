"""Exact owner authorized CPM test; private ledger; no automatic mutation retry."""
import os,json,time,requests
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
ROOT='china_agent:owner_cpm10_apply29:2026-10-29:v1'
STAGE=os.environ.get('CPM_STAGE','create')
def save(c,k,p):c.put(k,json.loads(json.dumps(p,allow_nan=False)))
def projection(x):
 return dict(id=x['id'],status=x['status'],currency=x['currency'],bid_type=x['bid_type'],settings=x['settings'],nm_settings=sorted(x['nm_settings'],key=lambda z:z['nm_id']))
def main():
 assert os.environ.get('GITHUB_REPOSITORY')=='Ekaterina11098/veschi-bot-runner' and os.environ.get('GITHUB_REF')=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()=='2026-10-29'
 c=Cache();w=WB();validate_identity(c,w)
 a=c.get(ROOT+':approval');assert a['status']=='approved' and a['rate_policy']=='fresh_WB_minimum'
 ns=sorted(int(x['nm_id']) for x in a['items']);assert len(ns)==len(set(ns))==10 and a['budget_cny']==300 and a['autofund'] is False
 e=c.get(ROOT+':execution');assert e and e['status'] not in ['verified','done']
 if not c.create(ROOT+':'+STAGE+':guard',dict(status='claimed',at=stamp())):raise ValueError('Existing stage guard; review private ledger, never repeat mutations')
 def persist():save(c,ROOT+':execution',e)
 def mutate(label,path,method,body=None):
  step=dict(label=label,path=path,method=method,request=body,status='submitting',at=stamp())
  e.setdefault('steps',[]).append(step);persist()
  r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':w.token},json=body,timeout=65)
  step['http_status']=r.status_code
  if not r.ok:
   step['status']='failed';step['response']=r.text[:1500];persist();raise ValueError('WB mutation rejected; inspect private receipt')
  step['response']=r.json() if r.content else None;step['status']='submitted';persist();return step['response']
 try:
  if STAGE=='create':
   inv=w.req('/adv/v1/promotion/count');ids=sorted({x['advertId'] for g in inv.get('adverts',[]) for x in g.get('advert_list',[])})
   camps=w.campaigns(ids);before=c.get(ROOT+':before');assert before
   fresh=[x for cid,x in camps.items() if cid not in before['campaigns'] and x['settings']['payment_type']=='cpm']
   matching=[x for x in fresh if {int(n['nm_id']) for n in x['nm_settings']}==set(ns)]
   named=[x for x in camps.values() if x['settings']['name']==a['name']]
   if named or matching:
    assert len(named or matching)==1
    new=(named or matching)[0];assert new['settings']['name']==a['name'] and new['bid_type']=='unified'
    cid=new['id'];e['adopted_existing']=True
   else:
    assert not fresh,'Unexplained new CPM campaign; inspect instead of duplicating'
    e['phase']='creating';persist()
    cid=mutate('create','/adv/v2/seacat/save-ad','POST',dict(name=a['name'],nms=ns,bid_type='unified',payment_type='cpm'))
    assert type(cid) is int and cid>0
   e['new_campaign_id']=cid;e['phase']='created_unfunded';persist()
   # New-campaign propagation can lag; only reads are retried.
   new=None
   for _ in range(10):
    try:new=w.campaigns([cid])[str(cid)];break
    except Exception:time.sleep(8)
   assert new and new['currency']=='CNY' and new['bid_type']=='unified' and new['settings']['payment_type']=='cpm'
   assert {int(n['nm_id']) for n in new['nm_settings']}==set(ns)
   e['created_readback']=new
   j=w.req('/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=ns,payment_type='cpm',placement_types=['combined']))
   rates={}
   for row in j.get('bids',[]):
    vals=[z for z in row['bids'] if z.get('currency')=='CNY' and z.get('type')=='combined']
    assert len(vals)==1 and type(vals[0]['value']) is int and vals[0]['value']>0
    rates[str(row['nm_id'])]=vals[0]['value']
   assert set(rates)=={str(n) for n in ns}
   e['minimums']=rates;e['minimums_readback']=j;e['minimums_at']=stamp();e['phase']='minimums_ready';e['status']='prepared';persist()
   print('Created/adopted unfunded campaign; exact private minimums ready')
  elif STAGE in ['apply','resume_funded']:
   if STAGE=='apply':assert e['status']=='prepared' and e['phase']=='minimums_ready'
   else:
    assert e['status']=='needs_review' and e.get('error')=='Funding response mismatch'
    funds=[s for s in e['steps'] if s['label']=='fund_exact_owner_budget']
    assert len(funds)==1 and funds[0]['http_status']==200 and funds[0]['request']['sum']==a['budget_cny'] and funds[0]['response']==dict(total=a['budget_cny'])
    e['recovered_error']=e['error'];e['recovery_stage']='readback_existing_funding_no_repeat'
   assert e.get('autofund_ui_off_verified_at')
   cid=int(e['new_campaign_id']);assert cid>0
   before=c.get(ROOT+':before')
   inv=w.req('/adv/v1/promotion/count');allids=sorted({x['advertId'] for g in inv.get('adverts',[]) for x in g.get('advert_list',[])})
   allcurrent=w.campaigns(allids)
   matches=[x for x in allcurrent.values() if x['settings']['name']==a['name']]
   assert len(matches)==1 and matches[0]['id']==cid,'Duplicate named campaign'
   new=allcurrent[str(cid)]
   assert new['status'] in [4,11] and new['currency']=='CNY' and new['bid_type']=='unified' and new['settings']['payment_type']=='cpm'
   assert new['settings']['placements']==dict(search=True,recommendations=True)
   assert {int(n['nm_id']) for n in new['nm_settings']}==set(ns)
   old={k:v for k,v in allcurrent.items() if k!=str(cid) and v['status']==9 and any(int(n['nm_id']) in ns for n in v['nm_settings'])}
   for k,v in old.items():
    assert v['currency']=='CNY' and v['settings']['payment_type']=='cpc'
    assert k in before['campaigns'] and projection(v)==projection(before['campaigns'][k]),'Old campaign changed since baseline'
   assert a['remove_selected_skus_from_previous_cpc'] is True
   e['before']=old
   oldids=[int(k) for k in old]
   e['baseline_fullstats']=w.req('/adv/v3/fullstats?ids='+','.join(map(str,oldids))+'&beginDate=2026-10-29&endDate=2026-10-29')
   j=w.req('/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=ns,payment_type='cpm',placement_types=['combined']))
   rates={}
   for row in j.get('bids',[]):
    vals=[z for z in row['bids'] if z.get('currency')=='CNY' and z.get('type')=='combined']
    assert len(vals)==1 and type(vals[0]['value']) is int and vals[0]['value']>0
    rates[str(row['nm_id'])]=vals[0]['value']
   assert set(rates)=={str(n) for n in ns}
   e['minimums']=rates;e['minimums_at']=stamp();e['phase']='configuring';persist()
   if any(any(int(v)!=rates[str(n['nm_id'])] for v in n['bids_kopecks'].values()) for n in new['nm_settings']):
    mutate('set_current_minimums','/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=n,bid_kopecks=rates[str(n)],placement='combined') for n in ns])]))
   def checked_new(v,status=None):
    return v['id']==cid and v['currency']=='CNY' and v['bid_type']=='unified' and v['settings']['payment_type']=='cpm' and v['settings']['name']==a['name'] and v['settings']['placements']==dict(search=True,recommendations=True) and {int(n['nm_id']) for n in v['nm_settings']}==set(ns) and all(int(n['bids_kopecks']['search'])==int(n['bids_kopecks']['recommendations'])==rates[str(n['nm_id'])] for n in v['nm_settings']) and (status is None or v['status']==status)
   for _ in range(12):
    new=w.campaigns([cid])[str(cid)]
    if checked_new(new):break
    time.sleep(6)
   assert checked_new(new),'Minimum bids readback mismatch'
   bd=w.req('/api/advert/v2/budget','POST',dict(advertIds=[cid]))['adverts']
   assert len(bd)==1 and bd[0]['currency']=='CNY'
   if STAGE=='resume_funded':
    assert bd[0]['total']==a['budget_cny'],'Existing funding not confirmed; do not retry'
    e['funding_reconciled_at']=stamp();persist()
   else:
    assert bd[0]['total']==0,'Campaign already funded: no blind repeat'
    e['budget_before']=bd[0];persist()
    paid=mutate('fund_exact_owner_budget','/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=a['budget_cny'],type=1,**{'return':True}))
    assert paid and paid.get('total')==a['budget_cny'],'Funding response mismatch'
   for _ in range(12):
    bd=w.req('/api/advert/v2/budget','POST',dict(advertIds=[cid]))['adverts']
    if len(bd)==1 and bd[0].get('currency')=='CNY' and bd[0].get('total')==a['budget_cny']:break
    time.sleep(6)
   assert len(bd)==1 and bd[0]['currency']=='CNY' and bd[0]['total']==a['budget_cny'],'Funding readback mismatch'
   e['budget_funded_verified']=bd[0];e['phase']='funded_not_started';persist()
   body=dict(nms=[dict(advert_id=int(k),nms=dict(add=[],delete=sorted(int(n['nm_id']) for n in v['nm_settings'] if int(n['nm_id']) in ns))) for k,v in old.items()])
   expected={}
   for k,v in old.items():
    ex=json.loads(json.dumps(v));ex['nm_settings']=[n for n in ex['nm_settings'] if int(n['nm_id']) not in ns];assert ex['nm_settings'],'Refuse emptying/pausing old campaign'
    expected[k]=ex
   if body['nms']:mutate('remove_selected_from_old_CPC','/adv/v0/auction/nms','PATCH',body)
   for _ in range(12):
    actual=w.campaigns(oldids)
    if all(projection(actual[k])==projection(expected[k]) for k in expected):break
    time.sleep(6)
   assert all(projection(actual[k])==projection(expected[k]) for k in expected),'Old campaign removal readback mismatch'
   verified=stamp()
   for k,v in actual.items():
    child=ROOT+':'+k+':execution'
    save(c,child,dict(status='verified',verified_at=verified,before=old[k],after=v,approval_key=ROOT+':approval',parent=ROOT+':execution',baseline_fullstats=[s for s in e['baseline_fullstats'] if str(s.get('advertId'))==k]))
   e['old_after']=actual;e['phase']='old_CPC_removals_verified';persist()
   mutate('start_new_CPM','/adv/v0/start?id='+str(cid),'GET')
   for _ in range(16):
    new=w.campaigns([cid])[str(cid)]
    if checked_new(new,9):break
    time.sleep(6)
   assert checked_new(new,9),'New campaign active readback mismatch'
   final=w.campaigns(allids)
   for k,v in allcurrent.items():
    if k==str(cid):continue
    exp=expected.get(k,v)
    assert projection(final[k])==projection(exp),'Other campaign projection changed'
   e['after']={**actual,str(cid):new};e['verified_at']=stamp();e['phase']='all_WB_verified';e['status']='verified';e.pop('error',None)
   for step in e['steps']:
    if step.get('status')=='submitted':step['status']='verified_by_final_readback'
   save(c,ROOT+':'+str(cid)+':execution',dict(status='verified',verified_at=e['verified_at'],before=None,created_readback=e['created_readback'],after=new,minimums=rates,budget_before=e['budget_before'],budget_funded_verified=e['budget_funded_verified'],approval_key=ROOT+':approval',parent=ROOT+':execution'))
   persist()
   print('Exact owner campaign active, minima and membership verified; private receipts saved')

  else:raise ValueError('Unsupported stage')
 except Exception as ex:
  e['status']='needs_review';e['error']=str(ex) if isinstance(ex,(ValueError,AssertionError)) else type(ex).__name__;e['failed_at']=stamp();persist();raise RuntimeError('Owner execution stopped; inspect private receipt') from None
if __name__=='__main__':main()
