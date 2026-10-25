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
from china_loss_ads import current,nmset
EXE=REQ+':execution'
def run():
 io=IO();p=io.get(REQ);io.validate_owner(dict(plan_sha256=digest(p['items'])))
 assert p['total_cny']==950 and p['items']==[dict(campaign_id=41270309,amount_cny=250,start=False),dict(campaign_id=41296359,amount_cny=350,start=True),dict(campaign_id=41296363,amount_cny=350,start=True)]
 cp=io.get('china_agent:codex_add_candidates:2026-10-25:v1');ce=io.get('china_agent:codex_add_candidates:2026-10-25:v1:execution')
 assert ce and ce['status']=='completed'
 e=io.get(EXE)
 if e and e.get('status')=='verified':print(json.dumps(dict(status='already_verified',wb_writes=0)));return
 if not e:
  e=dict(status='running',items={},steps={},wb_writes=0,total_cny=950,created_at=datetime.now(timezone.utc).isoformat(),run_id=os.environ.get('GITHUB_RUN_ID'));assert io.create(EXE,e)
 def save():io.put(EXE,json.loads(json.dumps(e)))
 def req(path,method='GET',body=None):
  time.sleep(1.5);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50)
  if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code))
  return r.json() if r.content else {}
 def write(label,path,method,body=None):
  old=e['steps'].get(label)
  if old:
   if old['status'] in ['accepted','verified']:return old.get('response')
   raise ValueError('Uncertain write; no duplicate '+label)
  assert datetime.now(timezone.utc)<datetime.fromisoformat(p['expires_at'])
  e['steps'][label]=dict(status='submitting',path=path,body=body,submitted_at=datetime.now(timezone.utc).isoformat());save()
  try:r=req(path,method,body)
  except Exception as ex:e['steps'][label].update(status='uncertain',reason=type(ex).__name__);save();raise
  e['wb_writes']+=1;e['steps'][label].update(status='accepted',response=r);save();return r
 def budgets(ids):
  rows=req('/api/advert/v2/budget','POST',dict(advertIds=ids)).get('adverts',[])
  assert {r['advertId'] for r in rows}==set(ids) and all(r['currency']=='CNY' for r in rows)
  return {r['advertId']:r['total'] for r in rows}
 ids=[41270309,41270471,41270474,41296359,41296363];cs=current(io,ids);bb=budgets(ids)
 e['preflight_campaigns']=cs;e['preflight_budgets']=bb;e['balance_readback']=req('/adv/v1/balance');save()
 # Verify all approved additions and existing product settings before money moves.
 for cid,c in cs.items():
  old=ce['groups'].get(str(cid))
  intended=[x for x in cp['items'] if x['campaign_id']==cid] if cid in ids[:3] else [x for x in cp['items'] if x['nm_id'] in set(ce['groups']['new_demand_bags_'+str(1 if cid==41296359 else 2)]['nm_ids'])]
  wanted={x['nm_id']:x['bid_minor'] for x in intended}
  assert wanted.keys()<=nmset(c) and all(next(n['bids_kopecks']['recommendations'] for n in c['nm_settings'] if n['nm_id']==nm)==bid for nm,bid in wanted.items())
  assert c['currency']=='CNY' and c['bid_type']=='manual' and c['settings']['payment_type']=='cpc' and c['settings']['placements']==dict(search=False,recommendations=True)
  assert c['status']==9 if cid in ids[:3] else c['status'] in [4,9]
  if old and c['status']==9:
   old.update(status='verified_active',after=c,verified_at=datetime.now(timezone.utc).isoformat());old.pop('reason',None)
 io.put('china_agent:codex_add_candidates:2026-10-25:v1:execution',ce)
 cfg=req('/api/advert/v1/config');assert cfg['currency']=='CNY' and cfg['minTopUp']<=25000
 bal=e['balance_readback'];assert bal['currency']=='CNY'
 source=0 if bal.get('balance',0)>=950 else 1 if bal.get('net',0)>=950 else None
 if source is None:raise ValueError('Insufficient available account funds for approved950')
 # Prior400 is rejected, not accepted: confirm unchanged budget before corrected source request.
 rejected=e['steps'].get('41270309:deposit')
 if rejected and rejected['status']=='uncertain':
  assert rejected.get('reason')=='RuntimeError' and bb[41270309]<=e['items']['41270309']['before_budget']
  rejected.update(status='rejected_http400_budget_unchanged',verified_at=datetime.now(timezone.utc).isoformat());save()
 for x in p['items']:
  cid=x['campaign_id'];label=str(cid)+':deposit_source'+str(source);st=e['items'].setdefault(str(cid),dict(campaign_id=cid,amount_cny=x['amount_cny'],before_budget=bb[cid]));save()
  if label not in e['steps']:
   if x['start'] and bb[cid]!=0:raise ValueError('New campaign already funded; no duplicate deposit')
   write(label,'/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=x['amount_cny'],type=source))
  after=None
  for _ in range(8):
   after=budgets([cid])[cid]
   if after>=st['before_budget']+x['amount_cny']-2:break
   time.sleep(5)
  if after<st['before_budget']+x['amount_cny']-2:raise ValueError('Deposit readback pending for '+str(cid))
  st.update(status='funded_verified',after_budget=after);e['steps'][label]['status']='verified';save()
 for x in p['items']:
  if not x['start']:continue
  cid=x['campaign_id'];label=str(cid)+':start';c=current(io,[cid])[cid]
  if label not in e['steps']:
   if c['status']!=4:raise ValueError('Draft status changed before start')
   write(label,'/adv/v0/start?id='+str(cid),'GET')
  for _ in range(10):
   c=current(io,[cid])[cid];e['items'][str(cid)]['after_campaign']=c;save()
   if c['status']==9:break
   time.sleep(5)
  if c['status']!=9:raise ValueError('Accepted launch readback pending for '+str(cid))
  e['steps'][label]['status']='verified';e['items'][str(cid)]['status']='active_verified';save()
 final=current(io,ids);assert all(c['status']==9 for c in final.values())
 e.update(status='verified',final_campaigns=final,completed_at=datetime.now(timezone.utc).isoformat());save()
 tracking=dict(status='active',campaign_ids=ids,source_execution=EXE,baseline_at=e['completed_at'],baseline_budgets=budgets(ids),baseline_campaigns=final,approved_funding_cny=950,auto_topup=False,auto_changes=False,notify_chat_only=True)
 try:tracking['baseline_fullstats']=req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-25&endDate=2026-10-25')
 except Exception as ex:tracking['baseline_stats_error']=type(ex).__name__
 key='china_agent:expanded_tests:2026-10-25:tracking:v1'
 io.put(key,tracking) if io.get(key) else io.create(key,tracking)
 print(json.dumps(dict(status=e['status'],funded_cny=950,active_campaigns=5,wb_writes=e['wb_writes'])))
if __name__=='__main__':run()
