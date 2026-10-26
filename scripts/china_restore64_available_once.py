"""Exact owner-approved two SKU restorations after fresh stock reads."""
import os,json,copy,time
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_restore64:2026-10-26:v1'
PLAN=[{"cid":41298169,"nm":1473243916,"article":"64-NoelBag-zchocolate","placement":"search","target":28,"barcode":"2052007102391"}]
def stable(c):return {k:c[k] for k in ['id','status','currency','bid_type','settings']}
def members(c):return {str(n['nm_id']):dict(subject=n['subject']['id'],bids=n['bids_kopecks']) for n in c['nm_settings']}
def get_json(url,headers,params=None,body=None):
 r=requests.request('POST' if body is not None else 'GET',url,headers=headers,params=params,json=body,timeout=55,allow_redirects=False)
 if not r.ok:raise RuntimeError('Stock read HTTP '+str(r.status_code)+' '+url.split('.ru')[-1])
 return r.json()
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 assert datetime.now(timezone.utc)<datetime.fromisoformat('2026-10-27T00:00:00+00:00')
 c=Cache();w=WB();validate_identity(c,w);auth=c.get(ROOT+':approval') or {}
 assert auth.get('status')=='approved' and auth.get('owner_id')==5122667182 and auth.get('plan')==PLAN and auth.get('require_fresh_stock') is True
 e=dict(status='preflight',created_at=stamp(),steps={},groups=[],wb_writes=0,budget_writes=0,stock_writes=0,price_writes=0,telegram_sends=0)
 key=ROOT+':execution'
 if not c.create(key,e):print('Existing execution; no replay');return
 def save():c.put(key,json.loads(json.dumps(e)))
 def write(step,path,body):
  assert step not in e['steps']
  e['steps'][step]=dict(status='sending',path=path,body=body,submitted_at=stamp());save()
  try:result=w.req(path,'PATCH',body,write=True)
  except Exception as ex:
   e['steps'][step].update(status='uncertain',error=str(ex));save();raise
  e['steps'][step].update(status='accepted',response=result);e['wb_writes']+=1;save()
 try:
  mh={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN']}
  base='https://api.moysklad.ru/api/remap/1.2'
  stores=get_json(base+'/entity/store',mh,dict(limit=1000))['rows']
  stores=[s for s in stores if s.get('name')=='МСК' and not s.get('archived')]
  assert len(stores)==1
  rows=get_json(base+'/report/stock/all',mh,dict(filter='store='+stores[0]['meta']['href'],stockMode='all',limit=1000))['rows']
  available={}
  for p in PLAN:
   found=[r for r in rows if r.get('article')==p['article']]
   assert len(found)==1
   r=found[0];available[p['article']]=dict(stock=r['stock'],reserve=r.get('reserve',0),available=r['stock']-r.get('reserve',0))
  e['moysklad_stock']=dict(observed_at=stamp(),store='МСК',items=available);save()
  wh=get_json('https://marketplace-api.wildberries.ru/api/v3/warehouses',{'Authorization':w.token})
  assert isinstance(wh,list) and 0<len(wh)<=30
  wb_by={p['barcode']:0 for p in PLAN};warehouse_stocks=[]
  for warehouse in wh:
   z=get_json('https://marketplace-api.wildberries.ru/api/v3/stocks/'+str(warehouse['id']),{'Authorization':w.token},body=dict(skus=list(wb_by)))
   warehouse_stocks.append(dict(warehouse_id=warehouse['id'],stocks=z.get('stocks',[])))
   for r in z.get('stocks',[]):
    if r['sku'] in wb_by:wb_by[r['sku']]+=r['amount']
  e['wb_stock']=dict(observed_at=stamp(),by_barcode=wb_by,warehouses=warehouse_stocks);save()
  for p in PLAN:
   if available[p['article']]['available']<=0 or wb_by[p['barcode']]<=0:raise RuntimeError('No confirmed available stock '+p['article'])
  cs=w.campaigns([p['cid'] for p in PLAN])
  for p in PLAN:
   b=cs[str(p['cid'])]
   assert b['currency']=='CNY' and b['bid_type']=='manual' and b['status']==9 and b['settings']['payment_type']=='cpc'
   assert b['settings']['placements']==dict(search=p['placement']=='search',recommendations=p['placement']=='recommendations')
   assert {n['subject']['id'] for n in b['nm_settings']}=={50}
   assert len(set(members(b))|{str(p['nm'])})<=50
  for p in PLAN:
   cid=p['cid'];before=cs[str(cid)];old=members(before)
   group=dict(campaign_id=cid,item=p,before=before,status='preflight');e['groups'].append(group);save()
   if str(p['nm']) not in old:
    write(str(cid)+':add','/adv/v0/auction/nms',dict(nms=[dict(advert_id=cid,nms=dict(add=[p['nm']],delete=[]))]))
    mid=w.campaigns([cid])[str(cid)]
    assert set(members(mid))==set(old)|{str(p['nm'])} and stable(mid)==stable(before) and all(members(mid)[k]==v for k,v in old.items())
    e['steps'][str(cid)+':add']['status']='verified';save()
   else:mid=before
   if members(mid)[str(p['nm'])]['bids'][p['placement']]!=p['target']:
    write(str(cid)+':bid','/api/advert/v1/bids',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=p['nm'],bid_kopecks=p['target'],placement=p['placement'])])]))
   after=w.campaigns([cid])[str(cid)];expected=copy.deepcopy(members(mid));expected[str(p['nm'])]['bids'][p['placement']]=p['target']
   assert stable(after)==stable(before) and members(after)==expected
   group.update(after=after,status='verified',verified_at=stamp())
   if str(cid)+':bid' in e['steps']:e['steps'][str(cid)+':bid']['status']='verified'
   save()
   child=ROOT+':'+str(cid)+':execution'
   c.put(child,dict(status='verified',before=before,after=after,items=[p],stock_checks=dict(moysklad=e['moysklad_stock'],wb=e['wb_stock']),verified_at=group['verified_at'],parent=key))
   reg=c.get('china_agent:verified_campaign_state:v1') or {};reg[str(cid)]=child;c.put('china_agent:verified_campaign_state:v1',reg)
  e.update(status='verified',completed_at=stamp());save()
 except Exception as ex:
  e.update(status='uncertain' if any(s['status'] in ['sending','accepted','uncertain'] for s in e['steps'].values()) else 'blocked',error=str(ex),completed_at=stamp());save();raise
 print('64 restored to search at exact0.28CNY after fresh positive stock')
if __name__=='__main__':main()
