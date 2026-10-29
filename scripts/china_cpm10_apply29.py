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
  else:raise ValueError('Unsupported stage')
 except Exception as ex:
  e['status']='needs_review';e['error']=str(ex) if isinstance(ex,(ValueError,AssertionError)) else type(ex).__name__;e['failed_at']=stamp();persist();raise RuntimeError('Owner execution stopped; inspect private receipt') from None
if __name__=='__main__':main()
