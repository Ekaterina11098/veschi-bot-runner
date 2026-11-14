"""Finish only preflight-blocked confirmed budget items. Never replay verified/uncertain writes."""
import os,json,copy
from datetime import datetime,timezone
from urllib.parse import urlparse,parse_qs
from china_loss_execute import IO
from china_daily_ad_actions import execute,EXEC
from china_loss_control import PLAN,APPROVAL
ROOT='china_agent:owner_finish326:2026-11-14:v1'
def main():
 io=IO();a=io.get(APPROVAL+'326');p=io.get(PLAN+a['plan_id']);key=EXEC+p['plan_id'];prior=io.get(key)
 assert p['plan_id']=='daily-2026-11-14-risk-unified-v1-budgets-1-buttons-fc04533b79fab3783cbad4a4-5122667182'
 assert a['sender_id']==5122667182 and a['job_id']==326 and a['result_message_id']==1040
 assert prior['status']=='done'and not io.get(ROOT),'Running/previous recovery: no blind replay'
 want={'topup:40933588','topup:41270309','topup:41298169','recover:41325637'}
 bad=[s for s in prior['items']if s['id']in want]
 assert {s['id']for s in bad}==want
 assert all(s['status']=='blocked'and not s.get('request')and not s.get('steps')and not s.get('submitted_at')and not s.get('before_budget')for s in bad),'A write might have been submitted; refuse replay'
 assert all(s['status']=='verified'for s in prior['items']if s['id']not in want)
 scope={i['campaign_id']:i['amount_cny']for i in p['items']if i['id']in want};assert scope=={40933588:500,41270309:150,41298169:600,41325637:100}
 import requests
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  u=urlparse(url);body=kw.get('json');m=method.upper()
  if u.hostname=='advert-api.wildberries.ru'and (m not in('GET',)or u.path in('/adv/v0/start','/adv/v0/pause','/adv/v0/stop')):
   if m=='POST'and u.path in('/api/advert/v2/budget','/api/advert/v1/bids/min'):pass
   elif m=='POST'and u.path=='/adv/v1/budget/deposit':
    cid=int(parse_qs(u.query)['id'][0]);assert cid in scope and body['sum']==scope[cid]
   elif m=='PATCH'and u.path=='/api/advert/v1/bids':
    rows=body['bids'];assert len(rows)==1 and rows[0]['advert_id']==41325637 and len(rows[0]['nm_bids'])==15 and all(b['bid_kopecks']==23 and b['placement']=='search'for b in rows[0]['nm_bids'])
   elif m=='GET'and u.path=='/adv/v0/start':assert parse_qs(u.query)=={'id':['41325637']}
   else:raise ValueError('Outside four remaining approved actions')
  elif u.hostname and (u.hostname.endswith('wildberries.ru')or u.hostname.endswith('moysklad.ru')):
   assert m=='GET'or m=='POST'and u.path.startswith('/api/v3/stocks/'),'Read-only source restriction'
  elif u.hostname=='api.telegram.org':assert u.path.rsplit('/',1)[-1]in('getMe','getChatMember','editMessageText','sendMessage')
  elif not url.startswith(io.url+'/rest/v1/'):raise ValueError('No model or unrelated service calls')
  return original(session,method,url,**kw)
 requests.sessions.Session.request=guard
 audit=dict(status='running',created_at=datetime.now(timezone.utc).isoformat(),approval_key=APPROVAL+'326',execution_key=key,prior=prior,remaining_ids=sorted(want),scope=scope,repeat_verified=False)
 assert io.create(ROOT,audit)
 updated=copy.deepcopy(prior);updated['items']=[s for s in updated['items']if s['id']not in want];updated['status']='running';io.put(key,updated)
 try:
  result=execute(io,a,p);audit.update(status='verified'if all(s['status']=='verified'for s in result['items'])else'attention_required',completed_at=datetime.now(timezone.utc).isoformat(),result=result);io.put(ROOT,audit)
  print(json.dumps(dict(status=audit['status'],items=[dict(id=s['id'],status=s['status'],reason=s.get('reason'))for s in result['items']])))
 except Exception as error:
  audit.update(status='attention_required',error=type(error).__name__);io.put(ROOT,audit);raise
if __name__=='__main__':main()
