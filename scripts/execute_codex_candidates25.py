"""Exact human-approved advertising actions; no price, budget or Telegram sends."""
import os,json,base64,time
from datetime import datetime,timezone,timedelta
from china_loss_execute import IO as OriginalIO
from china_loss_control import digest
from china_ad_rule import execute
REQ='china_agent:codex_add_candidates:2026-10-25:v1'
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

import copy,requests
from urllib.parse import quote
from china_loss_ads import current,nmset
from china_ad_rule import minimums
EXE=REQ+':execution'
def run():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
 io=IO();p=io.get(REQ);assert p and p['status']=='approved' and p['price_changes'] is False and p['daily_limits'] is False and p['new_funding_requires_budget_review'] is True
 sha=digest(p['items']);io.validate_owner(dict(plan_sha256=sha))
 e=io.get(EXE)
 if e and e.get('status')=='completed':print(json.dumps({'status':'already_completed','wb_writes':0}));return
 if not e:
  e=dict(status='preflight',plan_sha256=sha,items={},groups={},steps={},wb_writes=0,funding_writes=0,price_writes=0,telegram_sends=0,created_at=datetime.now(timezone.utc).isoformat(),run_id=os.environ.get('GITHUB_RUN_ID'))
  assert io.create(EXE,e)
 assert e['plan_sha256']==sha
 def save():io.put(EXE,json.loads(json.dumps(e)))
 def req(path,method='GET',body=None):
  time.sleep(1.3);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50)
  if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code))
  return r.json() if r.content else {}
 def write(label,path,method,body=None):
  old=e['steps'].get(label)
  if old:
   if old['status'] in ['accepted','verified']:return old.get('response')
   raise ValueError('Previous write uncertain; no blind retry: '+label)
  if datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('Approval expired')
  e['steps'][label]=dict(status='submitting',path=path,method=method,body=body,submitted_at=datetime.now(timezone.utc).isoformat());save()
  try:r=req(path,method,body)
  except Exception as ex:e['steps'][label].update(status='uncertain',reason=type(ex).__name__);save();raise
  e['wb_writes']+=1;e['steps'][label].update(status='accepted',response=r);save();return r
 def verified(label):
  if label in e['steps']:e['steps'][label]['status']='verified';save()
 def read_campaign(cid,predicate):
  c=None
  for attempt in range(7):
   c=current(io,[cid])[cid]
   if predicate(c):return c
   if attempt<6:time.sleep(5)
  raise ValueError('WB readback not yet confirmed for '+str(cid))
 def exact(c,category):
  if c.get('currency')!='CNY' or c.get('bid_type')!='manual' or c.get('settings',{}).get('payment_type')!='cpc' or c.get('settings',{}).get('placements')!=dict(search=False,recommendations=True):raise ValueError('Campaign model/placement/currency changed')
  if any(n.get('subject',{}).get('id')!=category for n in c.get('nm_settings',[])):raise ValueError('Campaign category mismatch')
 # One fresh catalogue read and paginated MoySklad physical warehouse stock.
 goods=[] if p.get('skip_price_stock_refresh_by_owner') else io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
 if len(goods)>=1000:raise ValueError('Price pagination needs continuation')
 prices={x['nmID']:x for x in goods}
 stocks=[]
 if not p.get('skip_price_stock_refresh_by_owner'):
  mbase='https://api.moysklad.ru/api/remap/1.2';mh={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN']}
  r=requests.get(mbase+'/entity/store',headers=mh,params={'limit':1000},timeout=45);r.raise_for_status()
  stores=[s for s in r.json().get('rows',[]) if s.get('name')=='МСК' and not s.get('archived')]
  if len(stores)!=1:raise ValueError('MoySklad warehouse ambiguous')
  stocks=[];offset=0
  while True:
   r=requests.get(mbase+'/report/stock/all',headers=mh,params={'filter':'store='+stores[0]['meta']['href'],'stockMode':'all','limit':1000,'offset':offset},timeout=60);r.raise_for_status();j=r.json();part=j.get('rows',[]);stocks+=part
   if offset+len(part)>=j.get('meta',{}).get('size',len(stocks)):break
   if not part or offset>=9000:raise ValueError('MoySklad pagination incomplete')
   offset+=len(part)
 else:e['price_stock_basis']='Owner confirms unchanged; approved dated snapshot reused';save()
 allcs=current(io);eligible=[]
 for item in p['items']:
  nm=item['nm_id'];old=e['items'].get(str(nm))
  if old and old['status'] in ['verified_active','verified_draft','blocked','already_active']:continue
  price=prices.get(nm);matches=[s for s in stocks if str(s.get('article','')).casefold()==item['article'].casefold()]
  reason=None
  if not p.get('skip_price_stock_refresh_by_owner') and (not price or price.get('vendorCode')!=item['article'] or price.get('currencyIsoCode4217')!='CNY'):reason='SKU identity/currency changed'
  elif not p.get('skip_price_stock_refresh_by_owner') and abs(price['sizes'][0]['discountedPrice']-item['price_cny'])>.011:reason='Seller price changed since approved plan'
  elif not p.get('skip_price_stock_refresh_by_owner') and (len(matches)!=1 or matches[0].get('stock') is None or matches[0].get('reserve') is None or matches[0]['stock']-matches[0]['reserve']<=0):reason='No free MoySklad stock'
  present=[cid for cid,c in allcs.items() if nm in nmset(c)]
  if present:
   if present==[item.get('campaign_id')]:
    n=next(n for n in allcs[present[0]]['nm_settings'] if n['nm_id']==nm)
    if n['bids_kopecks']['recommendations']==item['bid_minor']:e['items'][str(nm)]=dict(status='already_active',article=item['article'],campaign_id=present[0]);save();continue
   reason='SKU already active in another campaign or bid changed'
  if reason:e['items'][str(nm)]=dict(status='blocked',article=item['article'],reason=reason);save();continue
  eligible.append(item)
 e['preflight_at']=datetime.now(timezone.utc).isoformat();save()
 # Pause only target campaigns briefly so no newly-added SKU spends at an unapproved default bid.
 for cid in p['old_campaign_ids']:
  selected=[s for s in eligible if s['campaign_id']==cid]
  if not selected:continue
  group=e['groups'].setdefault(str(cid),dict(kind='existing',campaign_id=cid,status='preflight',nm_ids=[s['nm_id'] for s in selected]));save()
  try:
   before=current(io,[cid])[cid];exact(before,selected[0]['category'])
   if 'before' not in group:
    if before['status']!=9:raise ValueError('Target campaign is no longer active')
    group['before']=before;save()
   base_ids=nmset(group['before']);wanted={s['nm_id'] for s in selected}
   if len(base_ids|wanted)>50:raise ValueError('Campaign capacity would exceed50 products')
   if before['status']==9:write(str(cid)+':pause','/adv/v0/pause?id='+str(cid),'GET')
   elif before['status']!=4 or str(cid)+':pause' not in e['steps']:raise ValueError('Campaign paused outside this execution')
   read_campaign(cid,lambda c:c['status']==4);verified(str(cid)+':pause')
   if not wanted<=nmset(current(io,[cid])[cid]):
    write(str(cid)+':add','/adv/v0/auction/nms','PATCH',dict(nms=[dict(advert_id=cid,nms=dict(add=sorted(wanted),delete=[]))]))
   got=read_campaign(cid,lambda c:nmset(c)==base_ids|wanted);verified(str(cid)+':add')
   mins=minimums(io,cid,wanted);valid=[s for s in selected if mins.get(s['nm_id'],10**9)<=s['bid_minor']]
   invalid=wanted-{s['nm_id'] for s in valid}
   if invalid:
    write(str(cid)+':remove_unapproved_min','/adv/v0/auction/nms','PATCH',{'nms':[{'advert_id':cid,'nms':{'add':[],'delete':sorted(invalid)}}]})
    read_campaign(cid,lambda c:nmset(c)==(base_ids|wanted)-invalid);verified(str(cid)+':remove_unapproved_min')
    for s in selected:
     if s['nm_id'] in invalid:e['items'][str(s['nm_id'])]=dict(status='blocked',article=s['article'],reason='WB minimum exceeds approved bid');save()
   if valid:
    body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=s['nm_id'],bid_kopecks=s['bid_minor'],placement='recommendations') for s in valid])])
    write(str(cid)+':bids','/api/advert/v1/bids','PATCH',body)
    targets={s['nm_id']:s['bid_minor'] for s in valid}
    read_campaign(cid,lambda c:all(next((n['bids_kopecks']['recommendations'] for n in c['nm_settings'] if n['nm_id']==nm),None)==bid for nm,bid in targets.items()));verified(str(cid)+':bids')
   write(str(cid)+':resume','/adv/v0/start?id='+str(cid),'GET')
   after=read_campaign(cid,lambda c:c['status']==9 and nmset(c)==(base_ids|wanted)-invalid);verified(str(cid)+':resume')
   # Preserve all existing product bids and campaign settings.
   oldmap={n['nm_id']:n for n in group['before']['nm_settings']};newmap={n['nm_id']:n for n in after['nm_settings']}
   assert all(newmap[nm]==n for nm,n in oldmap.items()) and after['settings']==group['before']['settings']
   group.update(status='verified_active',after=after,verified_at=datetime.now(timezone.utc).isoformat())
   for s in valid:e['items'][str(s['nm_id'])]=dict(status='verified_active',article=s['article'],campaign_id=cid,bid_minor=s['bid_minor'])
   save()
  except Exception as ex:
   group.update(status='attention',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__);save()
 # New demand-bag campaigns remain unfunded drafts pending exact larger budgets.
 new=[s for s in eligible if s['campaign_id'] is None]
 for index,start in enumerate(range(0,len(new),31),1):
  selected=new[start:start+31];label='new_demand_bags_'+str(index);group=e['groups'].setdefault(label,dict(kind='new_demand_bags',status='preflight',nm_ids=[s['nm_id'] for s in selected]));save()
  try:
   name='Китай спрос сумки 25.10 · '+str(index)
   if 'campaign_id' not in group:
    reply=write(label+':create','/adv/v2/seacat/save-ad','POST',dict(name=name,nms=[s['nm_id'] for s in selected],bid_type='manual',payment_type='cpc',placement_types=['recommendations']))
    cid=reply if type(reply) is int else reply.get('advertId') if isinstance(reply,dict) else None
    if type(cid) is not int or cid<=0:raise ValueError('No creation ID; no blind recreation')
    group['campaign_id']=cid;save()
   cid=group['campaign_id'];wanted={s['nm_id'] for s in selected}
   before=read_campaign(cid,lambda c:c['status']==4 and nmset(c)==wanted);exact(before,50);verified(label+':create')
   mins=minimums(io,cid,wanted)
   if any(mins.get(s['nm_id'],10**9)>s['bid_minor'] for s in selected):raise ValueError('New draft minimum exceeds approved bid')
   write(label+':bids','/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=s['nm_id'],bid_kopecks=s['bid_minor'],placement='recommendations') for s in selected])]))
   after=read_campaign(cid,lambda c:c['status']==4 and all(next((n['bids_kopecks']['recommendations'] for n in c['nm_settings'] if n['nm_id']==s['nm_id']),None)==s['bid_minor'] for s in selected));verified(label+':bids')
   group.update(status='verified_draft',after=after,verified_at=datetime.now(timezone.utc).isoformat(),funding_pending_budget_review=True)
   for s in selected:e['items'][str(s['nm_id'])]=dict(status='verified_draft',article=s['article'],campaign_id=cid,bid_minor=s['bid_minor'])
   save()
  except Exception as ex:group.update(status='attention',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__);save()
 e['status']='completed' if all(s.get('status') in ['verified_active','verified_draft','blocked','already_active'] for s in e['items'].values()) and len(e['items'])==len(p['items']) else 'attention'
 e['completed_at']=datetime.now(timezone.utc).isoformat();save()
 print(json.dumps(dict(status=e['status'],active=sum(x['status']=='verified_active' for x in e['items'].values()),draft=sum(x['status']=='verified_draft' for x in e['items'].values()),blocked=sum(x['status']=='blocked' for x in e['items'].values()),wb_writes=e['wb_writes'],funding_writes=0)))
if __name__=='__main__':run()
