"""One-time exact Codex-confirmed category split. Private plans and receipts only."""
import copy,json,time
from datetime import timedelta
from china_loss_execute import IO
from china_new_ads import Transport,check_campaign,check_limit,now
from china_loss_control import digest

PID='china-new-ad-test-20261023-8sku-v4-three'
KEY='china_agent:new_ad_execution:v1:'+PID
def run():
 io=IO();p=io.get('china_agent:loss_plan:v1:'+PID);a=io.get('china_agent:codex_approval:v1:'+PID)
 assert p and a and a['source']=='explicit_human_codex_message' and a['status']=='approved'
 assert a['quote']=='Да, запускай 3 РК по 100 юаней, всего 300. Проверь, чтобы всё прошло правильно.'
 assert a['plan_sha256']==p['plan_sha256']==digest(p['items'])
 assert now().isoformat()<p['expires_at'] and p['price_changes'] is False
 specs=p['items'];assert len(specs)==3 and len({s['group'] for s in specs})==3
 assert [len(s['skus']) for s in specs]==[2,3,3]
 assert len({n['nm_id'] for s in specs for n in s['skus']})==8
 for s in specs:
  assert s['budget_cny']==100 and s['daily_limit_minor']==10000 and s['auto_topup'] is False and s['carry_over_enabled'] is False
  assert s['payment_type']=='cpc' and s['bid_type']=='manual' and s['placements']==['recommendations']
  assert all(n['bid_minor']==(28 if s['group']=='orders_bags' else 23) for n in s['skus'])
 # Original Telegram membership/token checks remain intact; the increased budget
 # is authorized separately by the explicit Codex approval above, never forged as TG.
 io.validate_owner(io.get('china_agent:loss_plan_approval:v1:86'))
 waiver=io.get('china_agent:codex_limit_waiver:v1:'+PID)
 assert waiver and waiver['source']=='explicit_human_codex_message' and waiver['daily_limit_required'] is False
 e=io.get(KEY)
 if e and e['status']=='done':return
 if e and e['status']=='uncertain':
  unresolved=[(s,k,v) for s in e['campaigns'] for k,v in s['steps'].items() if v['status'] in ['submitting','uncertain']]
  if not unresolved:return
  for s,k,v in unresolved:
   if k=='limit':v.update(status='waived',waiver_source=waiver['source']);continue
   if k!='deposit' or e.get('reason')!='WB advertising HTTP 400':return
   rec=io.get('china_agent:new_ad_funding_reconcile:v1:'+PID)
   assert rec and (now()-__import__('datetime').datetime.fromisoformat(rec['at'])).total_seconds()<1200
   balances=next(r['data'] for r in rec['responses'] if r['path']=='/api/advert/v2/budget')['adverts']
   assert next(b['total'] for b in balances if b['advertId']==s['campaign_id'])==0
   account=next(r['data'] for r in rec['responses'] if r['path']=='/adv/v1/balance')
   assert account['currency']=='CNY' and account['net']>=100
   s.setdefault('rejected_attempts',[]).append(dict(**v,reconciled_campaign_budget=0,reconciled_at=rec['at']))
   del s['steps']['deposit'];s['deposit_source']=1
  e['recovery_reason']=e.pop('reason',None);e['status']='running';e['daily_limit_required']=False
 if not e:
  e=dict(status='running',plan_id=PID,plan_sha256=p['plan_sha256'],campaigns=[],wb_writes=0,approval_source=a['source'],created_at=now().isoformat())
  assert io.create(KEY,e)
 t=Transport(io)
 def save():io.put(KEY,json.loads(json.dumps(e)))
 def read(path,method='GET',body=None):return t.request(path,method,body)
 def write(st,name,path,method,body=None):
  old=st['steps'].get(name)
  if old:
   if old['status']=='verified':return old['response']
   raise ValueError('Uncertain prior '+name+'; no repeated write')
  assert now().isoformat()<p['expires_at']
  st['steps'][name]=dict(status='submitting',path=path,method=method,body=body,at=now().isoformat());save()
  try:r=read(path,method,body)
  except Exception:
   st['steps'][name]['status']='uncertain';e['status']='uncertain';save();raise
  e['wb_writes']+=1;st['steps'][name].update(status='verified',response=r);save();return r
 def wait(check,label):
  for i in range(14):
   try:return check()
   except (ValueError,RuntimeError,AssertionError):
    if i==13:raise ValueError('Readback pending: '+label)
    time.sleep(15)
 def checked(cid,s,ready=True,bids=False):
  c=t.campaign(cid);check_campaign(c,s,ready,bids);return c
 def limited(cid,s):
  r=t.limit(cid);check_limit(r,s);return r
 try:
  cfg=t.config();assert cfg['currency']=='CNY' and cfg['minTopUp']<=10000 and cfg['cpcStep']==1
  listing=read('/adv/v1/promotion/count');ids=sorted({r['advertId'] for g in listing.get('adverts',[]) for r in g.get('advert_list',[])})
  assert len(ids)<=500
  allc=[]
  for start in range(0,len(ids),50):allc+=read('/api/advert/v2/adverts?ids='+','.join(map(str,ids[start:start+50]))).get('adverts',[])
  owned={x.get('campaign_id') for x in e['campaigns']}
  for s in specs:
   assert not any(c['id'] not in owned and c.get('settings',{}).get('name')==s['name'] for c in allc),'Unjournalled matching campaign; reconcile first'
  t.preflight(specs,owned)
  for s in specs:
   st=next((x for x in e['campaigns'] if x['group']==s['group']),None)
   if not st:st=dict(group=s['group'],status='preflight',steps={});e['campaigns'].append(st);save()
   if 'campaign_id' not in st:
    r=write(st,'create','/adv/v2/seacat/save-ad','POST',dict(name=s['name'],nms=[x['nm_id'] for x in s['skus']],bid_type='manual',payment_type='cpc',placement_types=['recommendations']))
    assert type(r) is int and r>0;st['campaign_id']=r;save()
   cid=st['campaign_id']
   if st.get('status')=='launched':continue
   wait(lambda:checked(cid,s),'draft')
   mins=t.minima(cid,[x['nm_id'] for x in s['skus']]);st['minima']=mins;save()
   assert all(mins[x['nm_id']]<=x['bid_minor'] for x in s['skus'])
   write(st,'bids','/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=x['nm_id'],bid_kopecks=x['bid_minor'],placement='recommendations') for x in s['skus']])]))
   wait(lambda:checked(cid,s,bids=True),'bids')
   st['daily_limit_required']=False;st['status']='draft_verified';save()
  for s in specs:
   st=next(x for x in e['campaigns'] if x['group']==s['group']);cid=st['campaign_id']
   if st.get('status')=='launched':continue
   if not st['steps'].get('deposit'):
    assert t.budget(cid)==0,'Draft already funded; reconcile first'
    write(st,'deposit','/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=100,type=st.get('deposit_source',0)))
   def budget_check():
    b=t.budget(cid);assert b==100;return b
   st['budget_readback']=wait(budget_check,'budget');st['status']='funded_verified';save()
  for s in specs:
   st=next(x for x in e['campaigns'] if x['group']==s['group']);cid=st['campaign_id']
   if st.get('status')=='launched':continue
   if not st['steps'].get('start'):
    checked(cid,s,bids=True);assert t.budget(cid)==100
    write(st,'start','/adv/v0/start?id='+str(cid),'GET')
   def active():
    c=checked(cid,s,ready=False,bids=True);assert c['status']==9;return c
   st['after']=wait(active,'active status');st['status']='launched';st['verified_at']=now().isoformat();save()
  e.update(status='done',completed_at=now().isoformat());save()
  track=io.get('china_agent:new_ad_tests:tracking:v1') or dict(plans={})
  track['plans'][PID]=dict(campaign_ids=[x['campaign_id'] for x in e['campaigns']],items=specs,started_at=e['completed_at'],budget_cny=300,status='active',existing_reports=True)
  io.put('china_agent:new_ad_tests:tracking:v1',track) if io.get('china_agent:new_ad_tests:tracking:v1') else io.create('china_agent:new_ad_tests:tracking:v1',track)
 except Exception as ex:
  e.update(status='uncertain' if e['status']=='uncertain' else 'blocked',reason=str(ex)[:500] if isinstance(ex,(ValueError,RuntimeError,AssertionError)) else type(ex).__name__);save()
 print(json.dumps(dict(status=e['status'],campaign_count=len(e['campaigns']),wb_writes=e['wb_writes'])))
if __name__=='__main__':run()

