"""Dated read-only143 advertising cost and compatible all-source funnel counters."""
import os,json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,stamp,validate_identity
from china_hourly_sales_read import ReadOnlyWB
from owner_143_funnel31_read import Adapter
from china_wb_evidence import Reports,FUNNEL,normalize_funnel
ROOT='china_agent:price143_unit_economics:2026-10-31:v1'
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise ValueError('Public owner runner only')
 c=Cache();w=ReadOnlyWB();key=ROOT+':advertising_funnel'
 q=c.get(ROOT+':read_request')or{}
 if q.get('status')!='approved_read_only'or q.get('wb_writes_allowed')is not False or datetime.now(timezone.utc)>=datetime.fromisoformat(q['expires_at']):raise ValueError('Dated read authorization unavailable')
 if c.get(key):print('Existing immutable read retained');return
 validate_identity(c,w);e=dict(cabinet='token_3',observed_at=stamp(),wb_writes=0,telegram_calls=0)
 try:
  inv=w.req('/adv/v1/promotion/count')
  ids=sorted({a['advertId']for g in inv.get('adverts',[])if g['status']in(7,9,11)for a in g.get('advert_list',[])})
  if len(ids)>50 or not ids:raise ValueError('Unexpected campaign coverage')
  campaigns=w.campaigns(ids)
  if any(x['currency']!='CNY'for x in campaigns.values()):raise ValueError('Campaign currency mismatch')
  stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-29&endDate=2026-10-31')
  if not isinstance(stats,list):raise ValueError('Malformed advertising stats')
  missing=sorted(set(ids)-{s['advertId']for s in stats});out=[]
  for cp in stats:
   for day in cp.get('days',[]):
    found=[n for app in day.get('apps',[])for n in app.get('nms',[])if n['nmId']==1473245494]
    if found:out.append(dict(campaign_id=cp['advertId'],day=day['date'][:10],spend=sum(n['sum']for n in found),clicks=sum(n['clicks']for n in found),attributed_orders=sum(n['orders']for n in found),attributed_amount=sum(n['sum_price']for n in found)))
  e['advertising']=dict(status='complete'if not missing else'partial',missing_ids=missing,requested_ids=ids,rows=out,observed_at=stamp(),period_from='2026-10-29',period_to='2026-10-31',note='Direct SKU expense including closed campaigns; attribution orders not unique all-source orders. Daily expense not click/order cohort matched.')
 except Exception as ex:e['advertising']=dict(status='unavailable',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__)
 selected=dict(start='2026-10-31',end='2026-10-31');past=dict(start='2026-10-30',end='2026-10-30')
 body=dict(selectedPeriod=selected,pastPeriod=past,nmIds=[1473245494],brandNames=[],subjectIds=[],tagIds=[],skipDeletedNm=False,orderBy=dict(field='openCard',mode='desc'),limit=10,offset=0)
 try:
  result=Reports(Adapter(c)).request(FUNNEL,body)
  if not result['available']:e['funnel']=dict(status='unavailable',reason=result.get('status'),retry_at=result.get('retry_at'))
  else:
   data=result['data'].get('data',{});products=data.get('products')
   if data.get('currency','').upper()!='CNY'or not isinstance(products,list)or len(products)!=1 or products[0]['product']['nmId']!=1473245494:raise ValueError('Exact143 funnel unavailable')
   e['funnel']=dict(status='complete',observed_at=result['observed_at'],rows=normalize_funnel(products,selected,past,key),note='Current partial day versus full yesterday; NOT matched same-hour conversion.')
 except Exception as ex:e['funnel']=dict(status='unavailable',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__)
 e.update(status='complete'if e['advertising']['status']=='complete'and e['funnel']['status']=='complete'else'partial',completed_at=stamp())
 if not c.create(key,e)or c.get(key)!=e:raise ValueError('Private readback failed')
 print(json.dumps(dict(status=e['status'],wb_writes=0,telegram_calls=0)))
if __name__=='__main__':run()
