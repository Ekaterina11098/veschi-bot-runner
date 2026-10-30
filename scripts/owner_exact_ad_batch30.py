"""One dated owner-approved private advertising batch. No scheduler or unrelated writes."""
import copy,json,os,time,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,projection,stamp,digest
from china_bid_proposals import fresh_stock
ROOT='china_agent:owner_five_bid_actions:2026-10-30:v1'
SCOPE_SHA='f046c96f53ea54d7c1b0a591f4ac19e1550bbaaac8352aecd486086b07a7b389'
def approve(c):
 a=c.get(ROOT+':approval') or {}
 if a.get('status')!='approved' or a.get('owner_user_id')!=5122667182 or a.get('source_channel')!='codex' or a.get('quote')!='делай все' or a.get('execution_authorized')is not True or a.get('cabinet')!='token_3':raise ValueError('Exact human approval missing')
 if datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at']) or datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()!='2026-10-30':raise ValueError('Dated approval expired')
 if digest(a.get('approved_items'))!=SCOPE_SHA:raise ValueError('Frozen scope mismatch')
 return a['approved_items']
def body_for(cid,kind,items):
 if not items or any(i['campaign_id']!=cid or i['kind']!=kind for i in items):raise ValueError('Mixed mutation')
 if kind=='bid':return '/api/advert/v1/bids',{'bids':[{'advert_id':cid,'nm_bids':[{'nm_id':i['nm_id'],'bid_kopecks':i['target_minor'],'placement':i['placement']} for i in items]}]}
 if kind=='exclude':return '/adv/v0/auction/nms',{'nms':[{'advert_id':cid,'nms':{'add':[],'delete':[i['nm_id'] for i in items]}}]}
 raise ValueError('Forbidden mutation')
def validate_write(path,method,body,items):
 if method!='PATCH':raise ValueError('Only PATCH')
 if path=='/api/advert/v1/bids':
  groups=body.get('bids',[])
  if len(groups)!=1:raise ValueError('One campaign only')
  cid=groups[0]['advert_id'];nms=[n['nm_id'] for n in groups[0]['nm_bids']];kind='bid'
 elif path=='/adv/v0/auction/nms':
  groups=body.get('nms',[])
  if len(groups)!=1:raise ValueError('One campaign only')
  cid=groups[0]['advert_id'];nms=groups[0]['nms']['delete'];kind='exclude'
 else:raise ValueError('Forbidden endpoint')
 if not nms or len(set(nms))!=len(nms):raise ValueError('Empty/duplicate mutation')
 selected=[i for i in items if i['campaign_id']==cid and i['kind']==kind and i['nm_id'] in nms]
 if len(selected)!=len(nms) or body_for(cid,kind,selected)!=(path,body):raise ValueError('Mutation outside exact approval')
class ScopedWB(WB):
 def __init__(self,items):super().__init__();self.items=items
 def req(self,path,method='GET',body=None,write=False):
  if write:validate_write(path,method,body,self.items)
  return super().req(path,method,body,write)
def expected(before,items):
 out=copy.deepcopy(before)
 for i in items:
  ns=[n for n in out['nm_settings'] if n['nm_id']==i['nm_id']]
  if len(ns)!=1 or ns[0]['bids_kopecks'][i['placement']]!=i['old_minor']:raise ValueError('Current bid/membership changed')
  if i['kind']=='bid':ns[0]['bids_kopecks'][i['placement']]=i['target_minor']
  elif i['kind']=='exclude':out['nm_settings']=[n for n in out['nm_settings'] if n['nm_id']!=i['nm_id']]
  else:raise ValueError('Forbidden kind')
 if not out['nm_settings']:raise ValueError('Cannot empty campaign')
 return out
def read(url,token,params=None,body=None):
 r=requests.request('POST' if body is not None else 'GET',url,params=params,json=body,headers={'Authorization':token},timeout=55)
 if not r.ok:raise ValueError('Preflight read HTTP '+str(r.status_code))
 return r.json()
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache();items=approve(c);old=c.get(ROOT+':execution')
 if old:print(json.dumps({'existing':True,'status':old['status']}));return
 w=ScopedWB(items);validate_identity(c,w)
 e={'status':'preflight','created_at':stamp(),'approval_key':ROOT+':approval','scope_sha256':SCOPE_SHA,'items':items,'steps':{},'wb_writes':0,'price_writes':0,'budget_writes':0,'telegram_calls':0}
 if not c.create(ROOT+':execution',e):raise ValueError('Concurrent execution')
 def save():c.put(ROOT+':execution',copy.deepcopy(e))
 try:
  ids=sorted({i['campaign_id'] for i in items});e['stage']='campaigns';save();campaigns=w.campaigns(ids);e['before']=copy.deepcopy(campaigns)
  for cp in campaigns.values():
   if cp['status']!=9 or cp['currency']!='CNY' or cp['bid_type']!='manual' or cp['settings']['payment_type']!='cpc' or cp['settings']['placements']!={'search':False,'recommendations':True}:raise ValueError('Campaign scope changed')
  e['budgets']=w.req('/api/advert/v2/budget','POST',{'advertIds':ids});e['budget_observed_at']=stamp();save()
  e['stage']='fresh MSK stock-reserve and COGS';save();stock=fresh_stock({},[i['article'] for i in items]);e.update(stock=stock,stock_observed_at=stamp());save()
  e['stage']='prices and published stock';save()
  goods=read('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',w.token,{'limit':1000,'offset':0}).get('data',{}).get('listGoods')
  if not isinstance(goods,list) or len(goods)>=1000:raise ValueError('Incomplete price page')
  wanted={i['nm_id'] for i in items};goods=[g for g in goods if g['nmID'] in wanted]
  if {g['nmID'] for g in goods}!=wanted or len(goods)!=len(wanted):raise ValueError('Exact price cards incomplete')
  e.update(prices=goods,prices_observed_at=stamp());sm={s['sizeID']:g['nmID'] for g in goods for s in g['sizes']}
  ss=read('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',w.token,body={'chrtIds':list(sm)}).get('stocks',[]);published={}
  for s in ss:
   if s['chrtId'] not in sm or type(s.get('amount'))is not int:raise ValueError('Invalid stock response')
   nm=sm[s['chrtId']];published[nm]=published.get(nm,0)+s['amount']
  e['published_stock']={str(k):v for k,v in published.items()};save()
  e['stage']='CBR and bid limits';save()
  rr=requests.get('https://www.cbr.ru/scripts/XML_daily.asp',params={'date_req':'30/10/2026'},timeout=45);rr.raise_for_status();xml=ET.fromstring(rr.content)
  if xml.attrib.get('Date')!='30.10.2026':raise ValueError('CBR effective date mismatch')
  fxrows=[v for v in xml.findall('Valute') if v.findtext('CharCode')=='CNY']
  if len(fxrows)!=1:raise ValueError('CBR CNY missing')
  fx=float(fxrows[0].findtext('Value').replace(',','.'))/int(fxrows[0].findtext('Nominal'))
  if not 1<fx<100:raise ValueError('CBR rate invalid')
  cfg=read('https://advert-api.wildberries.ru/api/advert/v1/config',w.token)
  if cfg.get('currency')!='CNY' or type(cfg.get('cpcStep'))is not int or cfg['cpcStep']<=0:raise ValueError('Bid limits unknown')
  mins={}
  for cid in ids:
   bids=[i for i in items if i['campaign_id']==cid and i['kind']=='bid']
   if bids:mins.update(w.minimums(cid,[i['nm_id'] for i in bids],'recommendations'))
  e.update(cbr={'date':'2026-10-30','rub_per_cny':fx},minimums={str(k):v for k,v in mins.items()},config=cfg,preflight=[]);eligible=[]
  for i in items:
   row={'nm_id':i['nm_id'],'campaign_id':i['campaign_id'],'kind':i['kind'],'status':'ready'}
   try:
    expected(campaigns[str(i['campaign_id'])],[i]);st=[s for s in stock if (s.get('article') or '').casefold()==i['article'].casefold()]
    if len(st)!=1 or any(not isinstance(st[0].get(k),(int,float)) for k in ['stock','reserve','price']):raise ValueError('MSK stock/COGS missing')
    st=st[0];row.update(available_msk=st['stock']-st['reserve'],cogs_rub=st['price']/100,published_stock=published.get(i['nm_id']))
    g=next(g for g in goods if g['nmID']==i['nm_id']);ps={s['discountedPrice'] for s in g['sizes']}
    if g.get('vendorCode')!=i['article'] or g.get('currencyIsoCode4217')!='CNY' or len(ps)!=1 or next(iter(ps))<=0:raise ValueError('Exact current CNY price unclear')
    row['seller_price_cny']=next(iter(ps))
    if i['kind']=='bid':
     t=i['target_minor']
     if mins[i['nm_id']]>t or t%cfg['cpcStep'] or t>cfg.get('cpcMaxBid',0):raise ValueError('Target outside fresh WB limits')
     if t>i['old_minor']:
      if row['available_msk']<=0 or row['cogs_rub']<=0 or row['published_stock'] is None or row['published_stock']<=0:raise ValueError('Raise lacks positive stock/COGS')
      q=i['own_paid']/i['own_completed'];price=row['seller_price_cny'];ad=t/100/i['baseline_cr'];margin=q*(price*.75-row['cogs_rub']/fx)-i['logistics_cny']-10/fx-ad
      row['preliminary_scenario']={'own_paid':i['own_paid'],'own_completed':i['own_completed'],'history_end':'2026-10-27','commission_assumption':.20,'tax_assumption':.05,'logistics_dated_through':'2026-10-18','logistics_cny':i['logistics_cny'],'unknown_reverse_common_costs':True,'ad_at_29Oct_CR':ad,'contribution_cny_before_unknown_costs':margin,'not_actual_profit_or_measured_forecast':True}
      if margin<=0:raise ValueError('Preliminary contribution not positive')
    eligible.append(i)
   except (ValueError,KeyError,TypeError,StopIteration) as ex:row.update(status='blocked',reason=str(ex) if isinstance(ex,ValueError) else type(ex).__name__)
   e['preflight'].append(row)
  e['baseline_fullstats']=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-30&endDate=2026-10-30');e['baseline_observed_at']=stamp()
  e.update(preflight_verified_at=stamp(),stage='authorized writes',status='applying');save();stop=set()
  for cid in ids:
   for kind in ['bid','exclude']:
    batch=[i for i in eligible if i['campaign_id']==cid and i['kind']==kind]
    if not batch or cid in stop:continue
    approve(c);before=w.campaigns([cid])[str(cid)]
    if projection(before)!=projection(campaigns[str(cid)]):raise ValueError('Campaign changed since preflight')
    target=expected(before,batch);path,body=body_for(cid,kind,batch);validate_write(path,'PATCH',body,items);key=ROOT+':'+str(cid)+':'+kind+':execution'
    step={'status':'submitting','before':before,'expected':target,'items':batch,'body':body,'approval_key':ROOT+':approval','submitted_at':stamp(),'parent':ROOT+':execution'}
    if not c.create(key,step):raise ValueError('Existing child: no repeat')
    e['steps'][str(cid)+':'+kind]=key;save()
    try:
     e['wb_writes']+=1;save();response=w.req(path,'PATCH',body,write=True);step.update(status='accepted',response=response);c.put(key,step)
     for n in range(4):
      after=w.campaigns([cid])[str(cid)];step['after']=after
      if projection(after)==projection(target):break
      if n<3:time.sleep(5)
     else:raise ValueError('Full campaign WB readback mismatch; no repeat')
     step.update(status='verified',verified_at=stamp());c.put(key,step);campaigns[str(cid)]=after
     reg=c.get('china_agent:verified_campaign_state:v1') or {};reg[str(cid)]=key;c.put('china_agent:verified_campaign_state:v1',reg)
    except Exception as ex:
     step.update(status='uncertain',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__,completed_at=stamp());c.put(key,step);stop.add(cid)
    save()
  children=[c.get(k) or {} for k in e['steps'].values()]
  e.update(status='verified' if len(eligible)==len(items) and children and all(s.get('status')=='verified' for s in children) else 'partial_or_blocked',completed_at=stamp())
 except Exception as ex:e.update(status='partial_or_uncertain' if e['steps'] else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__,completed_at=stamp())
 save();print(json.dumps({k:e.get(k) for k in ['status','stage','wb_writes','price_writes','budget_writes','telegram_calls','reason']}))
if __name__=='__main__':run()
