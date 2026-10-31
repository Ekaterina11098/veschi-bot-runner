"""Recover only original approval194 for eight visible PNG545 actions; never fund budgets."""
import os,copy,json
from datetime import datetime,timezone
from china_loss_execute import IO
from china_loss_control import PLAN,APPROVAL,digest,marker,is_all,CHAT,BOT
from china_daily_ad_actions import EXEC,BIND,process_and_deliver
from china_execution_notice import proven
ROOT='china_agent:job194_recovery:2026-10-31:v1'
PID='daily-2026-10-31-owner-agreed8-v1-drr-0'
def stamp():return datetime.now(timezone.utc).isoformat()
def archive(io,key,value):
 old=io.get(key)
 if old is None:
  if not io.create(key,value):raise ValueError('Archive race')
 elif old!=value:raise ValueError('Archive mismatch')
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=IO();request=io.get(ROOT+':request')or{}
 if request.get('owner_id')!=5122667182 or request.get('job_id')!=194 or request.get('plan_id')!=PID or request.get('scope')!='original_visible_eight_ad_actions_only':raise ValueError('Scoped recovery authorization missing')
 jobs=io.db('business_agent_jobs?id=eq.194&select=id,agent_id,status,request_text,sender_id,chat_id,created_at,tool_trace,update_id,answer')
 if len(jobs)!=1:raise ValueError('Original job missing')
 j=jobs[0];m=marker(j);b=io.get(BIND+'545');p=io.get(PLAN+PID)
 if j['sender_id']!=5122667182 or j['chat_id']!=CHAT or m.get('reply_message_id')!=545 or m.get('message_id')!=547 or m.get('bot_id')!=BOT or not is_all(j['request_text']):raise ValueError('Original PNG confirmation mismatch')
 if not b or b['plan_id']!=PID or b['plan_sha256']!=p['plan_sha256'] or p['plan_sha256']!=digest(p['items']) or len(p['items'])!=8 or any(i['kind']not in ['ad_set_bid','ad_exclude_sku']for i in p['items']):raise ValueError('Exact visible eight-action plan mismatch')
 if p.get('invalidated_at') or 545 not in p['report_message_ids'] or datetime.fromisoformat(j['created_at'])<datetime.fromisoformat(p['visible_from']) or datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('Approval or plan not current')
 a=dict(status='approved',plan_id=PID,plan_sha256=p['plan_sha256'],job_id=194,update_id=j['update_id'],sender_id=j['sender_id'],chat_id=CHAT,bot_id=BOT,input_message_id=547,reply_message_id=545,created_at=j['created_at'],price_changes=False,owner_recovery=ROOT)
 io.validate_owner(a);archive(io,ROOT+':before_job',j)
 old=io.get(APPROVAL+'194')
 if old:
  if old.get('plan_id')!=PID or old.get('plan_sha256')!=a['plan_sha256']:raise ValueError('Approval conflict')
  a=old
 elif not io.create(APPROVAL+'194',a):raise ValueError('Approval race')
 e=process_and_deliver(io,a,p)
 byid={i['id']:i for i in p['items']};states=e.get('items',[])
 all_verified=len(states)==8 and all(proven(byid[s['id']],s)for s in states)
 if all_verified:
  registry=io.get('china_agent:verified_campaign_state:v1')or{}
  for cid in sorted({i['campaign_id']for i in p['items']}):
   ss=[s for s in states if byid[s['id']]['campaign_id']==cid];key=ROOT+':'+str(cid)+':execution'
   receipt=dict(status='verified',verified_at=stamp(),before=ss[0]['before'],after=ss[-1]['after'],source_execution=EXEC+PID,job_id=194)
   if not io.get(key):io.create(key,receipt)
   registry[str(cid)]=key
  if io.get('china_agent:verified_campaign_state:v1')is None:io.create('china_agent:verified_campaign_state:v1',registry)
  else:io.put('china_agent:verified_campaign_state:v1',registry)
 from china_cloud_cost_control import WB
 w=WB();inv=w.req('/adv/v1/promotion/count');ids=sorted({x['advertId']for g in inv.get('adverts',[])if g['status']==9 for x in g.get('advert_list',[])})
 snapshot=dict(status='complete',observed_at=stamp(),campaigns=w.campaigns(ids),budgets=w.req('/api/advert/v2/budget','POST',{'advertIds':ids}),config=w.req('/api/advert/v1/config'),account=w.req('/adv/v1/balance'),all_eight_verified=all_verified,source_execution=EXEC+PID,wb_budget_writes=0)
 if not io.get(ROOT+':post_budget_snapshot'):io.create(ROOT+':post_budget_snapshot',snapshot)
 notice=io.get('china_agent:daily_ad_result:v2:'+PID)
 result=dict(status='verified' if all_verified else 'partial',observed_at=stamp(),job_id=194,execution_key=EXEC+PID,result_delivery=notice,states=[dict(id=s['id'],status=s['status'],reason=s.get('reason'))for s in states],wb_writes=e.get('wb_writes'),wb_budget_writes=0)
 if not io.get(ROOT+':result'):io.create(ROOT+':result',result)
 print(json.dumps({k:v for k,v in result.items()if k!='result_delivery'}))
if __name__=='__main__':run()
