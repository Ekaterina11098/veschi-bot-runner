"""Exact new Codex owner order: keep all bids, deposit100 once, resume only41325637."""
import os,json,copy,time
from datetime import datetime,timezone
from urllib.parse import urlparse,parse_qs
from china_advertising_state import AdvertisingIO
from china_cloud_cost_control import Cache,WB,validate_identity
from china_campaign_recovery import execute
from china_loss_control import digest
ROOT='china_agent:owner_umbrella_keep27:2026-11-14:v1'
CID=41325637
def main():
 io=AdvertisingIO();auth=io.get(ROOT+':authorization');assert auth['status']=='approved'and auth['owner_id']==5122667182 and auth['source_channel']=='codex'
 assert auth['scope']==dict(campaign_id=CID,target_minor=27,keep_bids=True,amount_cny=100,resume=True,other_actions=False)
 assert datetime.now(timezone.utc)<datetime.fromisoformat(auth['expires_at'])
 if io.get(ROOT+':execution'):return # Existing/uncertain writes are never repeated.
 c=Cache();w=WB();validate_identity(c,w)
 old=io.get('china_agent:loss_plan:v1:daily-2026-11-14-risk-unified-v1-budgets-1')
 item=copy.deepcopy(next(i for i in old['items']if i['id']=='recover:41325637'))
 item.update(target_minor=27,keep_existing_bids=True)
 assert len(item['nm_ids'])==15 and item['balance_before']==0 and item['amount_cny']==100
 p=dict(plan_id='owner-umbrella-keep27-20261114-v1',items=[item],chat_id=-1004342917488,bot_id=8780468043,plan_sha256=digest([item]))
 assert auth['plan_sha256']==p['plan_sha256']
 approval=dict(status='approved',source_channel='codex',job_id=326,input_message_id=1037,sender_id=5122667182,chat_id=-1004342917488,bot_id=8780468043,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'])
 auth.update(execution_key=ROOT+':execution',job_id=326,input_message_id=1037);io.put(ROOT+':authorization',auth)
 root=dict(status='preflight',items=[],wb_writes=0,source_channel='codex',authorization_key=ROOT+':authorization',completion_notice=dict(authorization_key=ROOT+':authorization',plan=p,approval=approval))
 assert io.create(ROOT+':execution',root)
 state=dict(id=item['id'],status='preflight');root['items']=[state]
 def save():
  root.update(status=state['status'],wb_writes=state.get('wb_writes',0));io.put(ROOT+':execution',json.loads(json.dumps(root)))
 import requests
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  u=urlparse(url);m=method.upper();body=kw.get('json')
  if u.hostname=='advert-api.wildberries.ru':
   allowed=(m=='GET'and u.path in('/api/advert/v2/adverts','/api/advert/v1/config','/adv/v1/balance'))or(m=='POST'and u.path in('/api/advert/v2/budget','/api/advert/v1/bids/min'))
   if u.path=='/adv/v1/budget/deposit':allowed=m=='POST'and parse_qs(u.query)=={'id':[str(CID)]}and body['sum']==100
   if u.path=='/adv/v0/start':allowed=m=='GET'and parse_qs(u.query)=={'id':[str(CID)]}
   assert allowed,'Only deposit100 and resume41325637 permitted; no bid writes'
  elif u.hostname and(u.hostname.endswith('wildberries.ru')or u.hostname.endswith('moysklad.ru')):assert m=='GET'or m=='POST'and u.path.startswith('/api/v3/stocks/')
  elif u.hostname=='api.telegram.org':assert u.path.rsplit('/',1)[-1]in('getMe','getChatMember','sendMessage','editMessageText')
  elif not url.startswith(io.url+'/rest/v1/'):raise ValueError('Unrelated service/model request prohibited')
  return original(session,method,url,**kw)
 requests.sessions.Session.request=guard
 def req(path,method='GET',body=None):
  time.sleep(1.5);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50)
  if not r.ok:raise ValueError('WB HTTP '+str(r.status_code))
  return r.json()if r.content else{}
 def campaign(cid):
  assert cid==CID;rows=req('/api/advert/v2/adverts?ids='+str(cid))['adverts'];assert len(rows)==1 and rows[0]['id']==CID;return rows[0]
 def budget(cid):
  assert cid==CID;rows=req('/api/advert/v2/budget','POST',dict(advertIds=[cid]))['adverts'];assert len(rows)==1 and rows[0]['advertId']==CID and rows[0]['currency']=='CNY';return rows[0]['total']
 try:
  execute(io,item,state,save,req,campaign,budget)
  assert state['status']=='verified'and state['wb_writes']==2
  # Register only the actual, matching WB-verified result.
  reg=io.get('china_agent:verified_campaign_state:v1')or{};child=ROOT+':campaign:'+str(CID)
  if not io.get(child):assert io.create(child,dict(state,parent=ROOT+':execution',campaign_id=CID))
  reg[str(CID)]=child;io.put('china_agent:verified_campaign_state:v1',reg)
  notice=io.get('china_agent:daily_ad_result:v2:'+p['plan_id'])or{}
  assert notice.get('status')=='sent','Verified WB result retained; delivery needs receipt review, never replay writes'
  print(json.dumps(dict(status='verified',after_budget=state['after_budget'],wb_writes=2,bid_writes=0,telegram_message_id=notice['message_id'])))
 except Exception as error:
  if state.get('status')not in('verified','uncertain','submitting','accepted'):state.update(status='blocked',reason=str(error)if isinstance(error,(ValueError,AssertionError))else type(error).__name__);save()
  raise
if __name__=='__main__':main()
