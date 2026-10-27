"""Only owner-amended umbrella27; other six exact growth actions already verified."""
import os,json,copy
from datetime import datetime,timezone
from china_price_apply import IO
from china_cloud_cost_control import Cache,WB,validate_identity
from china_advertising_plans import members,economics
from china_bid_proposals import fresh_stock
APP='china_agent:owner_growth_apply27:2026-10-27:umbrella27:approval'
KEY='china_agent:owner_growth_apply27:2026-10-27:umbrella27:execution'
PARENT='china_agent:owner_growth_apply27:2026-10-27:v1:execution'
def stamp():return datetime.now(timezone.utc).isoformat()
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=IO();wb=WB();validate_identity(Cache(),wb);a=io.get(APP);prior=io.get(KEY)
 if prior:print(json.dumps(dict(status=prior['status'],existing=True)));return
 if not a or a.get('status')!='approved' or a.get('source_channel')!='codex' or a.get('owner_user_id')!=5122667182 or a.get('nm_id')!=1556488181 or a.get('campaign_id')!=41325637 or a.get('target_minor')!=27:raise ValueError('Exact owner amendment absent')
 if (datetime.now(timezone.utc)-datetime.fromisoformat(a['approved_at'])).total_seconds()>7200:raise ValueError('Amendment stale')
 e=dict(status='running',approval_key=APP,parent=PARENT,created_at=stamp(),wb_writes=0,steps={},items=[dict(kind='ad_add_sku',article='Zont01-fio',nm_id=1556488181,campaign_id=41325637,placement='search',target_minor=27)])
 if not io.create(KEY,e):raise ValueError('Concurrent umbrella execution')
 def save():io.put(KEY,json.loads(json.dumps(e)))
 def write(name,path,body):
  if name in e['steps']:raise ValueError('No blind repeat')
  if (io.get(APP) or {}).get('status')!='approved':raise ValueError('Amendment revoked')
  e['steps'][name]=dict(status='submitting',path=path,body=body);save()
  try:
   response=wb.req(path,'PATCH',body,write=True);e['wb_writes']+=1;e['steps'][name].update(status='accepted',response=response);save()
  except Exception as error:e['steps'][name].update(status='uncertain',reason=str(error));save();raise
 try:
  recovery=io.get(PARENT+':reconcile:v1')
  if not recovery or recovery.get('status')!='verified' or len(recovery.get('verified_items',[]))!=6:raise ValueError('Prior six actions not reconciled')
  inv=wb.req('/adv/v1/promotion/count')
  ids=sorted({n['advertId'] for g in inv.get('adverts',[]) if g.get('status') in [9,11] for n in g.get('advert_list',[])})
  cs=wb.campaigns(ids);before=cs['41325637'];e['before']=before;save()
  if before['status']!=9 or before['currency']!='CNY' or before['bid_type']!='manual' or before['settings']['placements']!=dict(search=True,recommendations=False) or before['settings']['payment_type']!='cpc' or {n['subject']['id'] for n in before['nm_settings']}!={61}:raise ValueError('Campaign scope changed')
  if any(c['status']==9 and c['id']!=41325637 and c['settings']['placements'].get('search') and any(n['nm_id']==1556488181 for n in c['nm_settings']) for c in cs.values()):raise ValueError('Already in another search campaign')
  goods=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0&filterNmID=1556488181').get('listGoods',[])
  if len(goods)!=1 or goods[0]['nmID']!=1556488181 or goods[0]['vendorCode']!='Zont01-fio' or goods[0]['currencyIsoCode4217']!='CNY':raise ValueError('Exact current card missing')
  original=next(i for i in io.get('china_agent:owner_growth_plan:2026-10-27:v2')['items'] if i['nm_id']==1556488181)
  if goods[0]['sizes'][0]['discountedPrice']!=original['economics']['seller_price_cny']:raise ValueError('Seller price changed')
  model=copy.deepcopy(io.get('china_agent:new_ad_source:v1:2026-10-27'));model['prices']=goods;model['stock']=fresh_stock({},['Zont01-fio'])
  e['current_economics']=economics(model,1556488181);save()
  existing=next((n for n in before['nm_settings'] if n['nm_id']==1556488181),None)
  if existing and existing['bids_kopecks']['search']!=27:raise ValueError('Pre-existing umbrella rate differs')
  if not existing:
   if len(before['nm_settings'])>=50:raise ValueError('Campaign full')
   write('add','/adv/v0/auction/nms',dict(nms=[dict(advert_id=41325637,nms=dict(add=[1556488181],delete=[]))]))
  interim=wb.campaigns([41325637])['41325637'];e['after_membership']=interim;save()
  if set(members(interim))!=set(members(before))|{'1556488181'} or any(members(interim)[k]!=v for k,v in members(before).items()) or interim['settings']!=before['settings']:raise ValueError('Unexpected membership change')
  minimum=wb.minimums(41325637,[1556488181],'search')[1556488181];e['minimum_minor']=minimum;save()
  if minimum>27:raise ValueError('New live minimum exceeds amended27')
  if next(n for n in interim['nm_settings'] if n['nm_id']==1556488181)['bids_kopecks']['search']!=27:write('bid','/api/advert/v1/bids',dict(bids=[dict(advert_id=41325637,nm_bids=[dict(nm_id=1556488181,bid_kopecks=27,placement='search')])]))
  after=wb.campaigns([41325637])['41325637'];expected=members(before);expected['1556488181']=dict(subject=61,bids=dict(search=27,recommendations=0))
  if members(after)!=expected or any(after[k]!=before[k] for k in ['status','currency','bid_type','settings']):raise ValueError('Exact umbrella state not confirmed')
  e.update(status='verified',after=after,already_done=existing is not None,verified_at=stamp(),completed_at=stamp())
  for s in e['steps'].values():s['status']='verified'
  save()
  reg=io.get('china_agent:verified_campaign_state:v1') or {};reg['41325637']=KEY;io.put('china_agent:verified_campaign_state:v1',reg)
  parent=io.get(PARENT);parent.update(resolved_by_owner_amendment=KEY,overall_completion_status='verified_with_owner_amendment',overall_verified_items=7);io.put(PARENT,parent)
 except Exception as error:e.update(status='attention' if e['steps'] else 'blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__,completed_at=stamp());save()
 print(json.dumps(dict(status=e['status'],wb_writes=e['wb_writes'],reason=e.get('reason'))))
if __name__=='__main__':run()
