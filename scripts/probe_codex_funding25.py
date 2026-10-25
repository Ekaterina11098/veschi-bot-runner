"""Exact human-approved advertising actions; no price, budget or Telegram sends."""
import os,json,base64,time
from datetime import datetime,timezone,timedelta
from china_loss_execute import IO as OriginalIO
from china_loss_control import digest
from china_ad_rule import execute
REQ='china_agent:codex_candidate_funding:2026-10-25:v1'
PLAN_ID='codex-owner-adchanges-20261025-v1'
class IO(OriginalIO):
 def validate_owner(self,a):
  saved=self.get(REQ)
  if not saved or saved.get('status')!='approved' or saved.get('source')!='explicit_human_codex_message':raise ValueError('Exact human approval missing')
  if datetime.now(timezone.utc)>datetime.fromisoformat(saved['expires_at']):raise ValueError('Approval expired')
  if digest(saved['items'])!=a['plan_sha256']:raise ValueError('Approved items changed')
  cfg=self.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id,owner_user_id')
  if cfg!=[dict(active=True,chat_id=-1004342917488,bot_id=8780468043,owner_user_id=5122667182)]:raise ValueError('Registration changed')
  me=self.tg('getMe',{});assert me['id']==8780468043
  member=self.tg('getChatMember',dict(chat_id=-1004342917488,user_id=5122667182))
  assert member.get('user',{}).get('id')==5122667182 and member['user'].get('is_bot') is False
  assert member.get('status') in ['creator','administrator','member'] or member.get('status')=='restricted' and member.get('is_member') is True
  claims=json.loads(base64.urlsafe_b64decode(self.token.split('.')[1]+'='*(-len(self.token.split('.')[1])%4)))
  assert claims.get('t') is False and claims.get('exp',0)>time.time() and not int(claims.get('s',0))&(1<<30)
  ids=self.db('analytics_snapshots?cabinet=eq.token_3&source=eq.seller_identity&status=eq.complete&select=payload&limit=100')
  assert {r['payload'].get('sid') for r in ids}=={claims.get('sid')}

import requests
from china_loss_ads import current
io=IO();p=io.get(REQ);io.validate_owner(dict(plan_sha256=digest(p['items'])))
def read(path,method='GET',body=None):
 r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=45);r.raise_for_status();return r.json()
j=dict(observed_at=datetime.now(timezone.utc).isoformat(),balance=read('/adv/v1/balance'),budgets=read('/api/advert/v2/budget','POST',dict(advertIds=[41270309,41296359,41296363])))
io.put(REQ+':funding_probe',j)
print('Private funding balance/readback saved; no WB writes')
