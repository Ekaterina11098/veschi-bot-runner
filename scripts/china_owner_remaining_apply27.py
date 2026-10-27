"""Exact owner-approved24PNG tests, verified campaign diffs; no TG or funding."""
import os,json,copy,hashlib
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,projection
from china_price_apply import IO
from china_bid_proposals import fresh_stock,io_config
from china_advertising_plans import economics
ROOT='china_agent:owner_remaining_apply:2026-10-27:v1'
PLAN='china_agent:owner_remaining_review:2026-10-27:proposal:v1'
def stamp():return datetime.now(timezone.utc).isoformat()
def digest(items):return hashlib.sha256(json.dumps(items,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def expected(c,items):
 out=copy.deepcopy(c)
 for i in items:next(n for n in out['nm_settings'] if n['nm_id']==i['nm_id'])['bids_kopecks'][i['placement']]=i['target_minor']
 return projection(out)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 c=Cache();wb=WB();io=IO();p=c.get(PLAN) or {};a=c.get(ROOT+':approval') or {};items=p.get('items',[])
 if a.get('status')!='approved' or a.get('source_channel')!='codex' or a.get('owner_user_id')!=5122667182 or a.get('items')!=items or len(items)!=24 or digest(items)!=a.get('plan_sha256') or digest(items)!='f38ed58d76ff046daafc3d09473b85e21ad4039d1c8294f1a99cedae77850fd9' or a.get('png_sha256')!=p.get('png_sha256'):raise ValueError('Exact approved24PNG scope mismatch')
 if p.get('status')!='pending_owner_approval' or p.get('invalidated_at') or datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('Plan expired or revoked')
 old=c.get(ROOT+':execution')
 if old:print(json.dumps(dict(status=old['status'],existing=True)));return
 validate_identity(c,wb)
 e=dict(status='preflight',created_at=stamp(),approval_key=ROOT+':approval',plan_key=PLAN,plan_sha256=p['plan_sha256'],png_sha256=p['png_sha256'],items=items,groups=[],steps={},wb_writes=0,telegram_calls=0)
 if not c.create(ROOT+':execution',e):raise ValueError('Concurrent execution')
 def save():c.put(ROOT+':execution',copy.deepcopy(e))
 try:
  cids=sorted({i['campaign_id'] for i in items});before=wb.campaigns(cids);e['before']=before
  stock=fresh_stock({},[i['article'] for i in items]);e['stock']=stock
  goods=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
  if len(goods)>=1000:raise ValueError('Price catalogue pagination incomplete')
  model=c.get('china_agent:new_ad_source:v1:2026-10-27') or {};model['prices']=goods;model['stock']=stock
  evidence=c.get(p['source']) or {};known={r['nm_id']:r for r in evidence.get('items',[])}
  cfg=io_config(io);step=cfg.get('cpcStep')
  if cfg.get('currency')!='CNY' or type(step)is not int or step<=0:raise ValueError('CNY bid step unknown')
  minima={};need=[];checked=[]
  for cid in cids:
   camp=before[str(cid)];planned=[i for i in items if i['campaign_id']==cid]
   zones={i['placement'] for i in planned}
   if camp['status']!=9 or camp['currency']!='CNY' or camp['bid_type']!='manual' or camp['settings']['payment_type']!='cpc' or len(zones)!=1 or camp['settings']['placements']!=dict(search='search' in zones,recommendations='recommendations' in zones):raise ValueError('Campaign settings changed')
   for zone in zones:minima.update(wb.minimums(cid,[i['nm_id'] for i in planned],zone))
   for i in planned:
    nm=i['nm_id'];member=next(n for n in camp['nm_settings'] if n['nm_id']==nm);current=member['bids_kopecks'][i['placement']];target=i['target_minor']
    if current not in [i['old_minor'],target] or target<minima[nm] or target%step or target>cfg['cpcMaxBid']:raise ValueError('Exact bid or minimum changed: '+i['article'])
    ec=economics(model,nm)
    if ec['seller_price_cny']!=known[nm]['economics']['seller_price_cny'] or ec['article']!=i['article']:raise ValueError('Seller price/article changed')
    checked.append(dict(item=i,economics=ec,minimum_minor=minima[nm],already_done=current==target))
    if current!=target:need.append(i)
  e.update(preflight_verified_at=stamp(),checked=checked);save()
  if need:
   body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm_id'],bid_kopecks=i['target_minor'],placement=i['placement']) for i in need if i['campaign_id']==cid]) for cid in cids if any(i['campaign_id']==cid for i in need)])
   e['steps']['bids']=dict(status='submitting',body=body,path='/api/advert/v1/bids',submitted_at=stamp());save()
   try:result=wb.req('/api/advert/v1/bids','PATCH',body,write=True)
   except Exception:
    e['steps']['bids']['status']='uncertain';save();raise
   e['wb_writes']=1;e['steps']['bids'].update(status='accepted',response=result);save()
  after=wb.campaigns(cids);e['after']=after;at=stamp()
  for cid in cids:
   planned=[i for i in items if i['campaign_id']==cid];ok=projection(after[str(cid)])==expected(before[str(cid)],planned)
   e['groups'].append(dict(status='verified' if ok else 'uncertain',verified_at=at,before=before[str(cid)],after=after[str(cid)],items=planned,parent=ROOT+':execution',approval_key=ROOT+':approval'))
  allgood=all(g['status']=='verified' for g in e['groups'])
  e.update(status='verified' if allgood else 'partial_verified',verified_at=at,completed_at=stamp())
  if allgood and e['steps']:e['steps']['bids']['status']='verified'
  save()
  registry=c.get('china_agent:verified_campaign_state:v1') or {}
  for group in e['groups']:
   if group['status']!='verified':continue
   cid=group['after']['id'];key=ROOT+':'+str(cid)+':execution'
   if not c.create(key,group) and c.get(key)!=group:raise ValueError('Child receipt conflict')
   registry[str(cid)]=key
  c.put('china_agent:verified_campaign_state:v1',registry)
  if allgood:c.put(PLAN,dict(p,status='executed',execution_key=ROOT+':execution',completed_at=e['completed_at']))
 except Exception as error:
  e.update(status='uncertain' if e['steps'] else 'blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__,completed_at=stamp());save()
 print(json.dumps(dict(status=e['status'],verified_items=sum(len(g['items']) for g in e['groups'] if g['status']=='verified'),wb_writes=e['wb_writes'],reason=e.get('reason'))))
if __name__=='__main__':run()
