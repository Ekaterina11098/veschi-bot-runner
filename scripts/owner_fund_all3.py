"""Bounded owner funding 3Nov. Deposits only; durable no-replay journals."""
import os,json,time,math,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,projection,stamp
ROOT='china_agent:owner_fund_all:2026-11-03:v1'
IDS=[40933588,40945502,41055480,41270309,41296363,41298169,41332083]
class FundingWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  bare=path.split('?')[0]
  if write:
   if method!='POST' or bare!='/adv/v1/budget/deposit' or int(path.split('id=')[1]) not in IDS:raise ValueError('Forbidden write')
  elif (method,bare) not in [('GET','/api/advert/v2/adverts'),('GET','/api/advert/v1/config'),('GET','/adv/v1/balance'),('POST','/api/advert/v2/budget')]:raise ValueError('Forbidden read')
  time.sleep(1.4)
  r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=55)
  if not r.ok:raise RuntimeError('WB HTTP '+str(r.status_code))
  return r.json() if r.content else {}
def budgets(w):
 rows=w.req('/api/advert/v2/budget','POST',dict(advertIds=IDS))['adverts']
 if {r['advertId'] for r in rows}!=set(IDS) or any(r.get('currency')!='CNY' for r in rows):raise ValueError('Incomplete CNY balances')
 return {str(r['advertId']):r['total'] for r in rows}
def allocate(b,spend,available,minimum):
 amounts={str(i):0 for i in IDS}
 # Raise the least covered campaign in minimum increments, up to 3-day historical spend.
 while True:
  candidates=[str(i) for i in IDS if spend[str(i)]>0 and b[str(i)]+amounts[str(i)]<spend[str(i)] and available>=minimum]
  if not candidates:break
  cid=min(candidates,key=lambda k:(b[k]+amounts[k])/(spend[k]/3))
  amounts[cid]+=minimum;available-=minimum
 return {k:v for k,v in amounts.items() if v>0}
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Wrong execution repository')
 c=Cache();a=c.get(ROOT+':approval') or {}
 if a.get('owner_user_id')!=5122667182 or a.get('source_channel')!='codex' or a.get('campaign_ids')!=IDS or a.get('execution_authorized') is not True or datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at']):raise ValueError('Owner authorization missing/expired')
 if c.get(ROOT+':execution'):print('Execution exists; no replay');return
 w=FundingWB();validate_identity(c,w)
 cs=w.campaigns(IDS);b=budgets(w);cfg=w.req('/api/advert/v1/config');wallet=w.req('/adv/v1/balance')
 if cfg.get('currency')!='CNY' or wallet.get('currency')!='CNY':raise ValueError('Currency unknown')
 if any(cs[str(i)]['status']!=9 for i in IDS):raise ValueError('Campaign stopped or state changed; no funding')
 artifact=c.get('china_agent:advertising_artifacts:2026-11-03:v2')
 spend={str(x['id']):float(x['budget_period']['spend']) for x in artifact['bundle']['campaigns'] if x['id'] in IDS}
 if set(spend)!=set(map(str,IDS)):raise ValueError('Incomplete historical budget coverage')
 minimum=max(50,math.ceil(cfg['minTopUp']/100/50)*50)
 available=math.floor((wallet.get('balance',0)+wallet.get('net',0))/minimum)*minimum
 amounts=allocate(b,spend,available,minimum)
 p=dict(status='ready' if amounts else 'blocked',observed_at=stamp(),campaigns=cs,balances=b,spend_3days=spend,wallet=wallet,config=cfg,amounts=amounts,total_cny=sum(amounts.values()),minimum_cny=minimum,available_cny=available,excluded=[41296359,41325637],mode=a['mode'])
 c.put(ROOT+':preflight',p)
 if a['mode']!='apply':print(json.dumps(dict(status=p['status'],total_cny=p['total_cny'],amounts=amounts)));return
 approved=a['amounts']
 if not amounts or amounts!=approved:raise ValueError('Fresh amounts changed; no write')
 if sum(amounts.values())>a['max_total_cny']:raise ValueError('Funding cap exceeded')
 e=dict(status='applying',created_at=stamp(),wb_writes=0,total_verified_cny=0,items=[],steps={},preflight=p)
 if not c.create(ROOT+':execution',e):return
 def save():c.put(ROOT+':execution',e)
 cash=dict(balance=wallet.get('balance',0),net=wallet.get('net',0))
 try:
  for cid,amount in sorted(amounts.items(),key=lambda kv:b[kv[0]]/(spend[kv[0]]/3)):
   cp=w.campaigns([int(cid)])[cid];before=budgets(w)[cid]
   if projection(cp)!=projection(cs[cid]) or before>b[cid]+2:raise ValueError('Concurrent funding or campaign state changed')
   source=0 if cash['balance']>=amount else 1 if cash['net']>=amount else None
   if source is None:raise ValueError('Funds split or insufficient; no partial unsafe deposit')
   key=ROOT+':'+cid+':execution'
   step=dict(status='submitting',campaign_id=int(cid),amount_cny=amount,before_budget=before,before=cp,source=source,submitted_at=stamp(),parent=ROOT+':execution')
   if not c.create(key,step):raise ValueError('Child already exists; no repeat')
   e['steps'][cid]=key;save()
   try:
    e['wb_writes']+=1;save()
    step['response']=w.req('/adv/v1/budget/deposit?id='+cid,'POST',dict(sum=amount,type=source),write=True)
    step['status']='accepted';c.put(key,step);cash['balance' if source==0 else 'net']-=amount
    for attempt in range(5):
     after=budgets(w)[cid];step['after_budget']=after
     if before+amount-3<=after<=before+amount:break
     if attempt<4:time.sleep(3)
    else:raise ValueError('Deposit readback uncertain; no retry')
    after_cp=w.campaigns([int(cid)])[cid]
    if projection(cp)!=projection(after_cp):raise ValueError('Campaign settings changed')
    step.update(status='verified',after=after_cp,verified_at=stamp());c.put(key,step)
    e['items'].append(dict(campaign_id=int(cid),amount_cny=amount,before_budget=before,after_budget=after,status='verified',receipt_key=key));e['total_verified_cny']+=amount;save()
   except Exception as ex:
    step.update(status='uncertain',reason=str(ex));c.put(key,step);raise
  e.update(status='verified',completed_at=stamp(),final_budgets=budgets(w));save()
 except Exception as ex:
  e.update(status='partial_or_uncertain' if e['steps'] else 'blocked',reason=str(ex),completed_at=stamp());save()
 print(json.dumps({k:e.get(k) for k in ['status','wb_writes','total_verified_cny','reason']}))
if __name__=='__main__':main()
