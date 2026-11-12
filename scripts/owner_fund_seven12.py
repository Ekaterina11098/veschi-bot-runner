"""Exact owner-approved 7 deposits and optional resume363. No Telegram, bids, prices or composition writes."""
import os,json,time,copy
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
ROOT='china_agent:owner_fund_seven:2026-11-12:v1'
SCOPE={40933588:250,41055480:100,41155909:100,41270309:100,41298169:100,41332083:250,41296363:200}
def stamp():return datetime.now(timezone.utc).isoformat()
def project(c):
 return {k:c[k]for k in ['id','currency','bid_type','settings']}|dict(nm_settings=sorted(c['nm_settings'],key=lambda n:n['nm_id']))
def approval(c):
 a=c.get(ROOT+':approval')or{}
 if not(a.get('status')=='owner_approved'and a.get('execution_authorized')is True and a.get('owner_user_id')==5122667182 and a.get('source_channel')=='codex'and a.get('quote')=='пополни все'and a.get('cabinet')=='token_3'):raise ValueError('Exact owner authorization absent')
 if datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at']):raise ValueError('Approval expired')
 if {i['campaign_id']:i['amount_cny']for i in a['items']}!=SCOPE or len(a['items'])!=7 or a['total_cny']!=1100:raise ValueError('Scope mismatch')
 if {i['campaign_id']for i in a['items']if i['resume']}!={41296363}:raise ValueError('Resume scope mismatch')
 return a
def budgets(w,ids):
 rows=w.req('/api/advert/v2/budget','POST',dict(advertIds=ids))['adverts']
 if {r['advertId']for r in rows}!=set(ids)or any(r.get('currency')!='CNY'for r in rows):raise ValueError('Incomplete CNY budgets')
 return {r['advertId']:r['total']for r in rows}
def execute(c,w,pause=time.sleep):
 a=approval(c)
 if c.get(ROOT+':execution'):return c.get(ROOT+':execution')
 ids=list(SCOPE);before=w.campaigns(ids);cash_before=budgets(w,ids);cfg=w.req('/api/advert/v1/config');wallet=w.req('/adv/v1/balance')
 if cfg.get('currency')!='CNY'or wallet.get('currency')!='CNY':raise ValueError('CNY currency not verified')
 cash={k:wallet.get(k,0)for k in ['balance','net']};sources={}
 for item in a['items']:
  cid=item['campaign_id'];cp=before[str(cid)]
  if cp['status']!=(11 if cid==41296363 else 9)or project(cp)!=project(a['expected_campaigns'][str(cid)]):raise ValueError('Campaign changed before deposit: '+str(cid))
  if cash_before[cid]>item['balance_at_proposal']+2:raise ValueError('Funding after proposal; prevent duplicate: '+str(cid))
  if cfg['minTopUp']>SCOPE[cid]*100:raise ValueError('Minimum topup changed')
  source=0 if cash['balance']>=SCOPE[cid]else 1 if cash['net']>=SCOPE[cid]else None
  if source is None:raise ValueError('Insufficient wallet; no partial batch')
  sources[cid]=source;cash['balance'if source==0 else'net']-=SCOPE[cid]
 e=dict(status='applying',created_at=stamp(),approval_key=ROOT+':approval',before=before,budgets_before=cash_before,account_before=wallet,children=[],items=[],wb_write_attempts=0,total_verified_cny=0,telegram_calls=0,bid_writes=0,price_writes=0)
 if not c.create(ROOT+':execution',e):return c.get(ROOT+':execution')
 def put(k,p):c.put(k,json.loads(json.dumps(p)))
 def save():put(ROOT+':execution',e)
 try:
  for item in a['items']:
   approval(c);cid=item['campaign_id'];amount=SCOPE[cid]
   cp=w.campaigns([cid])[str(cid)];bal=budgets(w,[cid])[cid]
   if project(cp)!=project(before[str(cid)])or cp['status']!=before[str(cid)]['status']or bal>cash_before[cid]+2:raise ValueError('Concurrent change before deposit: '+str(cid))
   key=ROOT+':fund:'+str(cid)
   step=dict(status='submitting',campaign_id=cid,amount_cny=amount,before_budget=bal,before=cp,source=sources[cid],submitted_at=stamp(),parent=ROOT+':execution')
   if not c.create(key,step):raise ValueError('Existing deposit child; no replay')
   e['children'].append(key);e['wb_write_attempts']+=1;save()
   try:
    step['response']=w.req('/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=amount,type=sources[cid]),True);step['status']='accepted';put(key,step)
    for attempt in range(6):
     after_balance=budgets(w,[cid])[cid]
     if bal+amount-3<=after_balance<=bal+amount:break
     if attempt<5:pause(3)
    else:raise ValueError('Deposit result uncertain; no repeat')
    after=w.campaigns([cid])[str(cid)]
    if project(after)!=project(cp)or after['status']not in ([9,11]if cid==41296363 else[9]):raise ValueError('Settings changed during deposit')
    step.update(status='verified',after_budget=after_balance,after=after,verified_at=stamp());put(key,step)
    e['total_verified_cny']+=amount;e['items'].append(dict(campaign_id=cid,amount_cny=amount,before_budget=bal,after_budget=after_balance,status='verified',receipt_key=key));save()
   except Exception:
    step.update(status='uncertain',reason='Deposit response/readback uncertain; no retry');put(key,step);raise
  cp=w.campaigns([41296363])['41296363']
  if project(cp)!=project(before['41296363']):raise ValueError('Resume composition changed')
  if cp['status']==11:
   key=ROOT+':start:41296363';step=dict(status='submitting',before=cp,submitted_at=stamp(),parent=ROOT+':execution')
   if not c.create(key,step):raise ValueError('Existing start child; no replay')
   e['children'].append(key);e['wb_write_attempts']+=1;save()
   try:
    step['response']=w.req('/adv/v0/start?id=41296363','GET',None,True);step['status']='accepted';put(key,step)
    for attempt in range(8):
     cp=w.campaigns([41296363])['41296363']
     if cp['status']==9 and project(cp)==project(before['41296363']):break
     if attempt<7:pause(3)
    else:raise ValueError('Start readback uncertain')
    step.update(status='verified',after=cp,verified_at=stamp());put(key,step)
   except Exception:
    step.update(status='uncertain',reason='Start result uncertain; no retry');put(key,step);raise
  if cp['status']!=9:raise ValueError('Resume not verified')
  after=w.campaigns(ids);final_cash=budgets(w,ids)
  for cid in ids:
   if after[str(cid)]['status']!=9 or project(after[str(cid)])!=project(before[str(cid)]):raise ValueError('Final campaign readback mismatch')
   k=ROOT+':campaign:'+str(cid)
   if not c.create(k,dict(status='verified',before=before[str(cid)],after=after[str(cid)],amount_cny=SCOPE[cid],after_budget=final_cash[cid],verified_at=stamp(),parent=ROOT+':execution')):raise ValueError('Campaign receipt already exists')
   registry=c.get('china_agent:verified_campaign_state:v1')or{};registry[str(cid)]=k;put('china_agent:verified_campaign_state:v1',registry)
  e.update(status='verified',completed_at=stamp(),after=after,final_budgets=final_cash);save()
 except Exception as ex:
  e.update(status='uncertain'if any((c.get(k)or{}).get('status')=='uncertain'for k in e['children'])else'partial_verified'if e['total_verified_cny']else'blocked',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__,completed_at=stamp());save()
 return e
class ScopedWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  import requests
  bare=path.split('?')[0]
  if write:
   valid=method=='POST'and any(path=='/adv/v1/budget/deposit?id='+str(cid)and body in [dict(sum=amount,type=0),dict(sum=amount,type=1)]for cid,amount in SCOPE.items())
   valid=valid or(method=='GET'and path=='/adv/v0/start?id=41296363'and body is None)
   if not valid:raise ValueError('Write out of exact owner scope')
  elif (method,bare)not in [('GET','/api/advert/v2/adverts'),('GET','/api/advert/v1/config'),('GET','/adv/v1/balance'),('POST','/api/advert/v2/budget')]:raise ValueError('Read not allowed')
  time.sleep(1.3)
  r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=55,allow_redirects=False)
  if not r.ok:raise RuntimeError('WB HTTP '+str(r.status_code))
  return r.json()if r.content else{}
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Execution repository mismatch')
 c=Cache();w=ScopedWB();validate_identity(c,w);r=execute(c,w)
 print(json.dumps({k:r.get(k)for k in ['status','total_verified_cny','wb_write_attempts','reason']}))
if __name__=='__main__':main()
