"""Read-only full China advertising history and current candidate preflight."""
import os,json,time,copy
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_moysklad_read import read_stock
import xml.etree.ElementTree as ET
ROOT='china_agent:raise_candidates:2026-10-31:v1'
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:raise ValueError('This worker cannot write WB')
  return super().req(path,method,body,False)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache();q=c.get(ROOT+':read_request')or{}
 if q.get('status')!='approved_read_only' or q.get('owner_user_id')!=5122667182 or q.get('cabinet')!='token_3' or q.get('wb_writes_allowed')is not False or datetime.now(timezone.utc)>=datetime.fromisoformat(q['expires_at']):raise ValueError('Dated read request missing')
 if c.get(ROOT+':snapshot'):print('Existing read result preserved');return
 e={'status':'reading','started_at':stamp(),'wb_writes':0,'moysklad_writes':0,'telegram_calls':0,'stage':'identity'}
 if not c.create(ROOT+':snapshot',e):raise ValueError('Concurrent read')
 def save():c.put(ROOT+':snapshot',copy.deepcopy(e))
 w=ReadWB()
 try:
  validate_identity(c,w);e['stage']='current campaigns';save()
  inv=w.req('/adv/v1/promotion/count');active=sorted({x['advertId'] for g in inv.get('adverts',[]) if g['status']==9 for x in g.get('advert_list',[])})
  ids=sorted(set(active+q.get('archived_campaign_ids',[])))
  if not active or len(ids)>50:raise ValueError('Unexpected campaign coverage')
  campaigns=w.campaigns(ids)
  if any(cp['currency']!='CNY' for cp in campaigns.values()):raise ValueError('Not exact CNY cabinet')
  e.update(campaigns=campaigns,active_ids=active,campaigns_observed_at=stamp(),budgets=w.req('/api/advert/v2/budget','POST',{'advertIds':active}),stage='prices');save()
  rr=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params={'limit':1000,'offset':0},headers={'Authorization':w.token},timeout=55)
  if not rr.ok:raise ValueError('Price read HTTP '+str(rr.status_code))
  goods=rr.json().get('data',{}).get('listGoods')
  if not isinstance(goods,list) or len(goods)>=1000:raise ValueError('Price coverage incomplete')
  e.update(prices=goods,prices_observed_at=stamp(),stage='current WB limits')
  rr=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':w.token},timeout=45)
  if not rr.ok:raise ValueError('Config HTTP '+str(rr.status_code))
  e['config']=rr.json();e['minimums']={};e['minimum_errors']=[]
  groups={}
  for i in q['items']:groups.setdefault((i['campaign_id'],i['placement']),[]).append(i['nm_id'])
  for (cid,placement),nms in groups.items():
   cp=campaigns.get(str(cid))or{};current={n['nm_id'] for n in cp.get('nm_settings',[])}
   known=sorted(set(nms)&current)
   if not known:continue
   try:
    mins=w.minimums(cid,known,placement)
    for nm,v in mins.items():e['minimums'][str(cid)+':'+str(nm)+':'+placement]=v
   except Exception as ex:e['minimum_errors'].append({'cid':cid,'placement':placement,'reason':type(ex).__name__})
  e.update(minimums_observed_at=stamp(),stage='full completed-day statistics');save()
  stats=(c.get('china_agent:high_drr_economics:2026-10-31:v1:fullstats')or{})['stats']
  if not isinstance(stats,list):raise ValueError('Historical statistics malformed')
  stkey=ROOT+':fullstats'
  if not c.create(stkey,{'status':'complete' if {s['advertId'] for s in stats}==set(ids) else 'partial','observed_at':stamp(),'period_from':'2026-10-23','period_to':'2026-10-30','cabinet':'token_3','campaign_ids_requested':ids,'stats':stats,'wb_writes':0}):raise ValueError('Stats result collision')
  e.update(fullstats_key=stkey,stats_campaign_ids=[s['advertId'] for s in stats],stage='targeted MSK stock and COGS');save()
  articles=list(dict.fromkeys(i['article'] for i in q['items']));e['stock']=read_stock(articles)
  size_map={s['sizeID']:g['nmID'] for g in goods if g['nmID'] in {i['nm_id'] for i in q['items']} for s in g['sizes']}
  rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',json={'chrtIds':list(size_map)},headers={'Authorization':w.token},timeout=50)
  if not rr.ok:raise ValueError('Published stock read HTTP '+str(rr.status_code))
  pub={}
  for s in rr.json().get('stocks',[]):
   if s['chrtId'] not in size_map or type(s.get('amount'))is not int:raise ValueError('Published stock response unclear')
   nm=str(size_map[s['chrtId']]);pub[nm]=pub.get(nm,0)+s['amount']
  fx=requests.get('https://www.cbr.ru/scripts/XML_daily.asp?date_req=31/10/2026',timeout=40)
  fx.raise_for_status();tree=ET.fromstring(fx.content);row=next(v for v in tree.findall('Valute') if v.findtext('CharCode')=='CNY')
  e['cbr_fx']={'rub_per_cny':float(row.findtext('Value').replace(',','.'))/float(row.findtext('Nominal')),'effective_date':tree.attrib['Date'],'source':'https://www.cbr.ru/scripts/XML_daily.asp?date_req=31/10/2026','observed_at':stamp()}
  e.update(published_stock=pub,stock_observed_at=stamp(),statistics_source='china_agent:high_drr_economics:2026-10-31:v1:fullstats',status='complete' if e['stock']['coverage_complete'] and not e['minimum_errors'] and len(stats)==len(ids) else 'partial',completed_at=stamp())
 except Exception as ex:e.update(status='partial' if e.get('fullstats_key') else 'failed',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__,completed_at=stamp())
 save();print(json.dumps({k:e.get(k)for k in['status','stage','wb_writes','moysklad_writes','telegram_calls','reason']}))


"""One bounded read of own completed China history; no WB/TG calls."""
import os,json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,stamp
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
ROOT='china_agent:raise_candidates:2026-10-31:v1'
def read_buyout():
 c=Cache();q=c.get(ROOT+':read_request')or{};key=ROOT+':buyout30'
 if q.get('status')!='approved_read_only' or q.get('cabinet')!='token_3' or datetime.now(timezone.utc)>=datetime.fromisoformat(q['expires_at']):raise ValueError('Read authorization expired')
 if c.get(key):return
 found=[]
 tasks=[dict(cabinet='token_3',tool='lk_wb_products',key='owner-full-economics31-completed',priority=80,arguments=dict(date_from='2026-10-01',date_to='2026-10-30',start_row=0,end_row=1000))]
 def persist(cabinet,obs):
  if cabinet=='token_3' and obs.get('scope_verified')is True and obs.get('status')=='received':found.append(obs)
 def extra(call,checks,known):return execute_reads(call,checks,known,tasks,{},persist,max_requests=1)
 try:
  discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
  if len(found)!=1:raise ValueError('No one complete scoped observation')
  body=found[0].get('data',{}).get('data',{});rows=body.get('data',[])
  if body.get('need_update')!=0 or body.get('total')!=len(rows):raise ValueError('Products source not ready or incomplete')
  wanted={i['nm_id']for i in q['items']};fields=['nm_id','sa_name','finished_orders','is_payed','finish_as_return','not_finished_orders','average_delivery_cost','forwardlogisticsum','backwardlogisticsum','total_commission_without_spp_in_sales','is_payed_percent_after_returns','logistic_all','orders_count','orders_sum','sales_sum','returns_sum']
  selected=[{k:r.get(k)for k in fields}for r in rows if int(r['nm_id'])in wanted]
  value=dict(status='complete',period_from='2026-10-01',period_to='2026-10-30',observed_at=stamp(),source='MPStats verified own China products',currency='RUB',all_product_records=len(rows),rows=selected,missing_ids=sorted(wanted-{int(r['nm_id'])for r in selected}),wb_writes=0,telegram_calls=0)
 except Exception as ex:value=dict(status='unavailable',reason=str(ex)if isinstance(ex,ValueError)else type(ex).__name__,observed_at=stamp(),wb_writes=0,telegram_calls=0)
 if not c.create(key,value):raise ValueError('Duplicate result')
 print(json.dumps({k:v for k,v in value.items()if k not in ['rows']}))
if __name__=='__main__':
 run()
 read_buyout()
