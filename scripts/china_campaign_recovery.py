"""One explicitly selected recovery: lower existing bids, deposit once, then resume."""
import copy
from datetime import datetime,timezone

def execute(io,item,state,save,req,campaign,budget):
 if state.get('steps'):raise ValueError('Existing recovery journal; readback/manual review only, no replay')
 from china_morning_readiness import current_prices,published_stock
 from china_moysklad_read import read_stock
 cid=item['campaign_id'];e=item['recovery_evidence'];before=campaign(cid)
 assert item['kind']=='recover_campaign' and before['status']==11,'Recovery requires paused campaign'
 assert before['currency']=='CNY' and before['bid_type']=='manual' and before['settings']['payment_type']=='cpc'
 assert cid not in (40811856,) and not ({1473245494,1473245510}&{n['nm_id']for n in before['nm_settings']}),'Protected campaign/product'
 assert e['period_to']<datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()
 assert e['modeled_after_ads_cny']>0 and e['stress_after_ads_cny']>0 and e['preliminary']is True
 assert 0<=(datetime.now(timezone.utc)-datetime.fromisoformat(e['observed_at'].replace('Z','+00:00'))).total_seconds()<=24*3600,'Recovery economics expired'
 actual={str(n['nm_id']):n['bids_kopecks']for n in before['nm_settings']}
 assert actual==e['expected_bids'],'Recovery composition/bids changed'
 hold=(io.get('china_agent:budget_owner_policy:v1')or{}).get('do_not_fund',{}).get(str(cid))
 assert not hold or hold==item.get('supersedes_temporary_hold'),'New owner budget hold'
 zone=item['placement'];ids=sorted(map(int,actual))
 quote=req('/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=ids,payment_type='cpc',placement_types=['search'if zone=='search'else'recommendation']))
 minima={r['nm_id']:next((v['value']for v in r['bids']if v['currency']=='CNY'and v['type']==('search'if zone=='search'else'recommendation')),None)for r in quote['bids']}
 assert set(minima)==set(ids) and all(type(minima[n])is int and 0<minima[n]<=item['target_minor']<actual[str(n)][zone]for n in ids),'Recovery minimum changed'
 prices=current_prices(io,ids);pub=published_stock(io,prices,ids);stock=read_stock([r['article']for r in prices['rows']]);stocks={r['article'].casefold():r for r in stock['rows']}
 assert stock['coverage_complete']and not pub['missing_nm_ids']and {r['nm_id']for r in prices['rows']}==set(ids),'Fresh recovery coverage incomplete'
 for r in prices['rows']:
  old=e['member_inputs'][str(r['nm_id'])];s=stocks[r['article'].casefold()]
  assert r['seller_price']==old['price']and 0<s['price']/100<=old['cost']and s['stock']-s['reserve']>0 and pub['amounts'][str(r['nm_id'])]>0,'Recovery economics/stock changed'
 state.update(before=before,before_budget=budget(cid),steps=[]);save()
 assert state['before_budget']==item['balance_before'],'Campaign already funded; refresh recovery'
 cfg=req('/api/advert/v1/config');wallet=req('/adv/v1/balance');amount=item['amount_cny']
 assert cfg['currency']==wallet['currency']=='CNY'and cfg['minTopUp']<=amount*100
 source=0 if wallet.get('balance',0)>=amount else 1 if wallet.get('net',0)>=amount else None
 assert source is not None,'Insufficient CNY wallet'
 expected=copy.deepcopy(before)
 def same(got,status):
  return got['status']==status and all(got[k]==expected[k]for k in ['id','currency','bid_type','settings','nm_settings'])
 def step(label,path,method,body,verify):
  s=dict(id=label,status='submitting',request=dict(path=path,method=method,body=body));state['steps'].append(s);state['status']='submitting';save()
  try:
   s['response']=req(path,method,body);s['status']='accepted';state['wb_writes']=state.get('wb_writes',0)+1;save()
   for _ in range(20):
    if verify():
     s.update(status='verified',verified_at=datetime.now(timezone.utc).isoformat());state['status']='preflight';save();return
    __import__('time').sleep(3)
   raise ValueError('Recovery readback mismatch')
  except Exception:
   s['status']='uncertain';state['status']='uncertain';save();raise
 assert same(campaign(cid),11),'Campaign changed before lowering'
 for n in expected['nm_settings']:n['bids_kopecks'][zone]=item['target_minor']
 body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=nm,placement=zone,bid_kopecks=item['target_minor'])for nm in ids])])
 step('bids','/api/advert/v1/bids','PATCH',body,lambda:same(campaign(cid),11))
 assert budget(cid)==state['before_budget']and same(campaign(cid),11),'State changed before deposit'
 step('fund','/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=amount,type=source),lambda:same(campaign(cid),11)and budget(cid)>=state['before_budget']+amount)
 assert same(campaign(cid),11)and budget(cid)>0,'Recovery prerequisites not verified'
 step('resume','/adv/v0/start?id='+str(cid),'GET',None,lambda:same(campaign(cid),9))
 state.update(status='verified',after=campaign(cid),after_budget=budget(cid),verified_at=datetime.now(timezone.utc).isoformat(),wb_writes=3);save()
 return 3
