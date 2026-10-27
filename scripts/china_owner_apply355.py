"""Apply exactly thirteen CPC rates explicitly approved by owner in Codex, then verify WB."""
import os,json,copy
from datetime import datetime,timezone
from urllib.parse import urlencode
from china_price_apply import IO
from china_cloud_cost_control import Cache,WB,validate_identity
from conversion_watches import Worker
import china_advertising_plans as p
import china_bid_proposals as q
APPROVAL='china_agent:owner_apply_png355:2026-10-27:v1:approval'
EXEC=p.E+'dialog-ads-140-raise'
def save(io,key,value):
 if io.get(key) is None:
  if not io.create(key,value):raise ValueError('Concurrent journal identity')
 else:io.put(key,value)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise PermissionError('Dated public main only')
 io=IO();wb=WB();validate_identity(Cache(),wb)
 a=io.get(APPROVAL);plan=io.get(p.P+'dialog-ads-140-raise');binding=io.get(p.B+'355')
 if not a or a.get('source_channel')!='codex' or a.get('owner_user_id')!=5122667182 or a.get('status')!='approved' or a.get('png_message_id')!=355:raise PermissionError('Exact owner command absent')
 if not plan or not binding or len(plan.get('items',[]))!=13 or plan.get('invalidated_at') or plan.get('status') in ['revoked','invalidated'] or p.digest(plan['items'])!=plan['plan_sha256'] or a['plan_sha256']!=plan['plan_sha256'] or binding['plan_sha256']!=plan['plan_sha256'] or 355 not in plan.get('report_message_ids',[]):raise ValueError('Exact PNG plan binding changed')
 if datetime.now(timezone.utc)>datetime.fromisoformat(plan['expires_at']):raise ValueError('Plan expired; no stale execution')
 projection=lambda xs:[{k:i[k] for k in ['article','campaign_id','nm_id','placement','old_minor','target_minor']} for i in xs]
 if projection(plan['items'])!=a['items'] or any(i['kind']!='ad_raise_bid' for i in plan['items']):raise ValueError('Approved exact items differ')
 prior=io.get(EXEC)
 if prior:print(json.dumps(dict(status=prior['status'],existing_execution=True,wb_writes=prior.get('wb_writes'))));return
 if io.get(p.A+plan['plan_id']):raise ValueError('Telegram approval already owns execution; do not duplicate')
 e=dict(status='running',approval_source='codex',approval_key=APPROVAL,png_message_id=355,plan_sha256=plan['plan_sha256'],created_at=p.iso(),wb_writes=0,items=[],steps={},checks=[])
 if not io.create(EXEC,e):raise ValueError('Execution claimed concurrently')
 def persist():io.put(EXEC,json.loads(json.dumps(e)))
 try:
  def db(method,table,params=None,body=None,prefer=None):
   if method!='GET':raise PermissionError('History is read-only')
   return io.db(table+('?' +urlencode(params) if params else ''))
  view=q.sources(Worker(db,lambda *args:None))
  for i in plan['items']:
   newer=[x for x in view['changes'] if x.get('nm')==i['nm_id'] and x.get('cid') in (None,i['campaign_id']) and q.timestamp(x.get('at')) and q.timestamp(x['at'])>q.timestamp(plan['created_at'])]
   if newer:raise ValueError('New verified change after proposal: '+i['article'])
  ids=sorted({i['campaign_id'] for i in plan['items']});before=wb.campaigns(ids);e['before']=before;persist()
  goods=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
  if len(goods)>=1000:raise ValueError('Price catalogue truncated')
  prices={v['nmID']:v for v in goods}
  stock=q.fresh_stock({},[i['article'] for i in plan['items']])
  model=copy.deepcopy(io.get('china_agent:new_ad_source:v1:2026-10-27') or {})
  at=q.timestamp(model.get('observed_at'))
  if not at or (datetime.now(timezone.utc)-at).total_seconds()>86400:raise ValueError('Own completed buyout/economics stale')
  model['prices']=goods;model['stock']=stock
  need=[]
  for index,i in enumerate(plan['items']):
   c=before[str(i['campaign_id'])];ns={n['nm_id']:n for n in c['nm_settings']}
   if c['status']!=9 or c.get('currency')!='CNY' or c.get('bid_type')!='manual' or c['settings']['payment_type']!='cpc' or c['settings']['placements']!=dict(search=i['placement']=='search',recommendations=i['placement']=='recommendations') or i['nm_id'] not in ns:raise ValueError('Current campaign/member/placement changed: '+i['article'])
   current=ns[i['nm_id']]['bids_kopecks'][i['placement']]
   if current not in [i['old_minor'],i['target_minor']]:raise ValueError('Current rate differs from exact plan: '+i['article'])
   price=prices.get(i['nm_id'],{})
   if price.get('vendorCode')!=i['article'] or price.get('currencyIsoCode4217')!='CNY' or price.get('sizes',[{}])[0].get('discountedPrice')!=i['economics']['seller_price_cny']:raise ValueError('Seller price/card changed: '+i['article'])
   ec=p.economics(model,i['nm_id'])
   state=dict(index=index,item=copy.deepcopy(i),status='preflight',before=c,already_done=current==i['target_minor'])
   e['items'].append(state);e['checks'].append(dict(article=i['article'],current_minor=current,target_minor=i['target_minor'],current_economics=ec,prior_cogs_kopecks=i['economics']['cogs_kopecks']))
   if current!=i['target_minor']:need.append(i)
  persist()
  for cid in ids:
   for zone in ['search','recommendations']:
    selected=[i for i in need if i['campaign_id']==cid and i['placement']==zone]
    if not selected:continue
    minima=wb.minimums(cid,[i['nm_id'] for i in selected],zone)
    for i in selected:
     if minima[i['nm_id']]>i['target_minor']:raise ValueError('Current minimum exceeds approved rate: '+i['article'])
    e.setdefault('minimums',{})[str(cid)+':'+zone]={str(k):v for k,v in minima.items()};persist()
  current=io.get(p.P+plan['plan_id'])
  if current.get('invalidated_at') or current['plan_sha256']!=plan['plan_sha256'] or datetime.now(timezone.utc)>datetime.fromisoformat(plan['expires_at']):raise ValueError('Exact plan revoked/expired before write')
  if io.get(p.A+plan['plan_id']):raise ValueError('Concurrent Telegram confirmation; stop duplicate path')
  body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm_id'],bid_kopecks=i['target_minor'],placement=i['placement']) for i in need if i['campaign_id']==cid]) for cid in ids if any(i['campaign_id']==cid for i in need)])
  if need:
   e['steps']['bids']=dict(status='submitting',path='/api/advert/v1/bids',method='PATCH',body=body);persist()
   try:
    response=wb.req('/api/advert/v1/bids','PATCH',body,write=True)
    e['steps']['bids'].update(status='accepted',response=response);e['wb_writes']=1;persist()
   except Exception as error:
    e['steps']['bids'].update(status='uncertain',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__);persist()
  after=wb.campaigns(ids);e['after']=after
  all_exact=True
  for cid in ids:
   old=before[str(cid)];new=after[str(cid)];expected=p.members(old)
   for i in plan['items']:
    if i['campaign_id']==cid:expected[str(i['nm_id'])]['bids'][i['placement']]=i['target_minor']
   exact=p.members(new)==expected and new['settings']==old['settings'] and new['status']==old['status']
   if not exact:all_exact=False
   for state in e['items']:
    if state['item']['campaign_id']==cid:state.update(status='verified' if exact else 'uncertain',after=new)
  e.update(status='verified' if all_exact else 'attention',verified_at=p.iso(),completed_at=p.iso())
  if all_exact and need:e['steps']['bids']['status']='verified';e['wb_writes']=1
  persist()
  registry=io.get('china_agent:verified_campaign_state:v1') or {}
  for cid in ids:
   states=[s for s in e['items'] if s['item']['campaign_id']==cid]
   if not all(s['status']=='verified' for s in states):continue
   key='china_agent:owner_apply_png355:2026-10-27:v1:'+str(cid)+':execution'
   child=dict(status='verified',before=before[str(cid)],after=after[str(cid)],items=[s['item'] for s in states],verified_at=e['verified_at'],parent=EXEC,approval_source='codex',approval_key=APPROVAL)
   save(io,key,child);registry[str(cid)]=key
  save(io,'china_agent:verified_campaign_state:v1',registry)
  if all_exact:
   save(io,p.P+plan['plan_id'],dict(current,status='executed',execution_key=EXEC,completed_at=e['completed_at'],executed_from='codex_owner_command'))
 except Exception as error:
  submitted=e.get('steps',{}).get('bids',{}).get('status') in ['submitting','accepted','uncertain']
  e.update(status='uncertain' if submitted else 'blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__,completed_at=p.iso());persist()
 print(json.dumps(dict(status=e['status'],wb_writes=e.get('wb_writes',0),verified=sum(s['status']=='verified' for s in e['items']),items=len(e['items']),reason=e.get('reason'))))
if __name__=='__main__':run()
