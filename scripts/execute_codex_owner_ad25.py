"""Exact human-approved advertising actions; no price, budget or Telegram sends."""
import os,json,base64,time
from datetime import datetime,timezone,timedelta
from china_loss_execute import IO as OriginalIO
from china_loss_control import digest
from china_ad_rule import execute
REQ='china_agent:codex_existing_ad_changes:2026-10-25:v1'
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
def run():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
 io=IO();saved=io.get(REQ);assert saved and saved['status']=='approved' and saved['price_changes'] is False and saved['funding_writes'] is False
 p=dict(plan_id=PLAN_ID,items=saved['items'],plan_sha256=digest(saved['items']),created_at=saved['created_at'],expires_at=saved['expires_at'],chat_id=-1004342917488,bot_id=8780468043,execution_kind='ad_drr_rule',price_changes=False)
 key='china_agent:loss_plan:v1:'+PLAN_ID
 if not io.create(key,p):assert io.get(key)==p
 a=dict(job_id='codex-owner-20261025',sender_id=5122667182,chat_id=-1004342917488,bot_id=8780468043,source='explicit_human_codex_message',plan_sha256=p['plan_sha256'])
 e=execute(io,a,p)
 # Only GET reconciliation for accepted responses; no repeated writes.
 for _ in range(3):
  if not any(x.get('status') in ['accepted','uncertain','submitting'] for x in e['items']):break
  time.sleep(15);e=execute(io,a,p)
 audit=dict(status=e['status'],plan_id=PLAN_ID,items=[{k:x.get(k) for k in ['id','article','status','already_done','reason','submitted_at']} for x in e['items']],wb_writes=e['wb_writes'],funding_writes=0,price_writes=0,telegram_sends=0,observed_at=datetime.now(timezone.utc).isoformat(),run_id=os.environ.get('GITHUB_RUN_ID'))
 result=REQ+':execution'
 io.put(result,audit) if io.get(result) else io.create(result,audit)
 print(json.dumps(dict(status=e['status'],verified=sum(x['status']=='verified' for x in e['items']),blocked=sum(x['status']=='blocked' for x in e['items']),wb_writes=e['wb_writes'],funding_writes=0)))
if __name__=='__main__':run()
