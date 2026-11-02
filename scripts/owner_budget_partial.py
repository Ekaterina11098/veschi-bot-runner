"""One-off private explicit owner funding approval. No starts, pauses, bids, prices or sends."""
import os,copy,json,time,hashlib
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_budget_partial:2026-11-02:v1'
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def project(c):
 out={k:c[k]for k in ['id','status','currency','bid_type','settings']}
 out['nm_settings']=sorted(c['nm_settings'],key=lambda n:n['nm_id']);return out
def approval(c):
 a=c.get(ROOT+':approval')or{}
 if a.get('status')!='approved'or a.get('execution_authorized')is not True or a.get('owner_user_id')!=5122667182 or a.get('cabinet')!='token_3'or a.get('source_channel')!='codex':raise ValueError('Exact owner funding approval absent')
 if datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at']):raise ValueError('Approval expired')
 if digest(a['items'])!=a['scope_sha256']or len(a['items'])!=4 or sum(i['amount_cny']for i in a['items'])!=2700:raise ValueError('Funding scope changed')
 expected={(40933588,1650),(41055480,350),(41298169,550),(41332083,150)}
 if {(x['campaign_id'],x['amount_cny']) for x in a['items']}!=expected:raise ValueError('Only exact four bounded partial amounts approved')
 return a
class ScopedWB(WB):
 def __init__(self,items):super().__init__();self.items=items
 def req(self,path,method='GET',body=None,write=False):
  import requests
  bare=path.split('?')[0]
  if write:
   if method!='POST'or not any(path=='/adv/v1/budget/deposit?id='+str(i['campaign_id'])and body in [dict(sum=i['amount_cny'],type=0),dict(sum=i['amount_cny'],type=1)]for i in self.items):raise PermissionError('Only exact approved deposits allowed')
  elif (method,bare)not in [('GET','/api/advert/v2/adverts'),('GET','/api/advert/v1/config'),('GET','/adv/v1/balance'),('POST','/api/advert/v2/budget')]:raise PermissionError('Unapproved read')
  time.sleep(1.3);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=55)
  if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code))
  return r.json()if r.content else{}
def put(c,k,p):c.put(k,json.loads(json.dumps(p)))
def budgets(w,ids):
 rows=w.req('/api/advert/v2/budget','POST',dict(advertIds=ids)).get('adverts',[])
 if {r['advertId']for r in rows}!=set(ids)or any(r.get('currency')!='CNY'for r in rows):raise ValueError('Budget currency or coverage unknown')
 return {r['advertId']:r['total']for r in rows}
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Wrong repository')
 c=Cache();a=approval(c);items=a['items'];ids=[i['campaign_id']for i in items]
 prior=c.get(ROOT+':execution')
 if prior:
  if prior.get('status')!='blocked'or prior.get('wb_writes')!=0 or prior.get('steps'):print('Existing financial execution; no replay');return
  if not c.create(ROOT+':preflight_recovery1',dict(at=stamp(),reason='Canonical membership order normalization; prior has zero deposits')):return
  c.create(ROOT+':preflight_rejected:first',prior)
 w=ScopedWB(items);validate_identity(c,w)
 e=dict(status='preflight',approval_key=ROOT+':approval',scope_sha256=a['scope_sha256'],created_at=stamp(),steps={},items=[],wb_writes=0,total_verified_cny=0,bid_writes=0,price_writes=0,status_writes=0,telegram_calls=0)
 if prior:put(c,ROOT+':execution',e)
 elif not c.create(ROOT+':execution',e):return
 def save():put(c,ROOT+':execution',e)
 try:
  cs=w.campaigns(ids);bb=budgets(w,ids);cfg=w.req('/api/advert/v1/config');wallet=w.req('/adv/v1/balance');e.update(before=cs,budgets_before=bb,config=cfg,account_before=wallet)
  if cfg.get('currency')!='CNY'or wallet.get('currency')!='CNY':raise ValueError('Funding currency not CNY')
  cash=dict(balance=wallet.get('balance',0),net=wallet.get('net',0));sources={}
  for i in items:
   cid=i['campaign_id'];cp=cs[str(cid)]
   if cp['status']!=9 or project(cp)!=project(a['expected_campaigns'][str(cid)]):raise ValueError('Campaign changed since approved budget review')
   if bb[cid]>i['balance_before']+2:raise ValueError('Campaign funded after proposal; prevent duplicate')
   if cfg['minTopUp']>i['amount_cny']*100:raise ValueError('Minimum deposit changed')
   source=0 if cash['balance']>=i['amount_cny']else 1 if cash['net']>=i['amount_cny']else None
   if source is None:raise ValueError('Insufficient available CNY funds')
   cash['balance'if source==0 else'net']-=i['amount_cny'];sources[cid]=source
  e['status']='applying';save()
  for i in items:
   approval(c);cid=i['campaign_id'];cp=w.campaigns([cid])[str(cid)];before_budget=budgets(w,[cid])[cid]
   if project(cp)!=project(cs[str(cid)])or before_budget>bb[cid]+2:raise ValueError('Concurrent funding or campaign change')
   key=ROOT+':'+str(cid)+':execution';step=dict(status='submitting',campaign_id=cid,amount_cny=i['amount_cny'],source=sources[cid],before=cp,before_budget=before_budget,parent=ROOT+':execution',submitted_at=stamp())
   if not c.create(key,step):raise ValueError('Existing deposit child; no replay')
   e['steps'][str(cid)]=key;save()
   try:
    e['wb_writes']+=1;save();step['response']=w.req('/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=i['amount_cny'],type=sources[cid]),write=True);step['status']='accepted';put(c,key,step)
    for attempt in range(5):
     after_budget=budgets(w,[cid])[cid];step['after_budget']=after_budget
     if before_budget+i['amount_cny']-3<=after_budget<=before_budget+i['amount_cny']:break
     if attempt<4:time.sleep(3)
    else:raise ValueError('Deposit readback uncertain; no repeated deposit')
    after=w.campaigns([cid])[str(cid)];step['after']=after
    if project(after)!=project(cp):raise ValueError('Settings changed during funding')
    step.update(status='verified',verified_at=stamp());put(c,key,step);e['items'].append(dict(campaign_id=cid,amount_cny=i['amount_cny'],before_budget=before_budget,after_budget=after_budget,status='verified',receipt_key=key));e['total_verified_cny']+=i['amount_cny'];save()
   except Exception as ex:
    step.update(status='uncertain',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__);put(c,key,step);raise
  e.update(status='verified',completed_at=stamp(),final_budgets=budgets(w,ids));save()
 except Exception as ex:
  e.update(status='partial_or_uncertain'if e['steps']else'blocked',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError,PermissionError))else type(ex).__name__,completed_at=stamp());save()
 print(json.dumps({k:e.get(k)for k in ['status','wb_writes','total_verified_cny','reason']}))
if __name__=='__main__':main()

