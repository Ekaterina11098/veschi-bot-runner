"""Prepare only the existing owner-requested four-SKU18MSK report; no Telegram."""
import json,requests
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from conversion_watches import runtime,RECEIPTS
ROOT='china_agent:owner_report205:2026-11-01:v1'
WATCH='china_agent:conversion_watch:v1:-1004342917488:5122667182:task_once_205'
REPORT='report:b85939ba:2026-11-01'
MSK=ZoneInfo('Europe/Moscow')
IDS=[1473243911,1473245494,1473245495,1473245508]
def main():
 c=Cache();watch=c.get(WATCH)
 if not watch or watch['id']!='b85939ba' or watch['revision']!=1 or watch['chat_id']!=-1004342917488 or watch['owner_user_id']!=5122667182 or watch['nm_ids']!=IDS:raise ValueError('Exact watch changed')
 if watch['status']=='completed' or c.get(RECEIPTS+REPORT):print('Existing report; never regenerate or duplicate');return
 if watch['status']!='active' or datetime.now(timezone.utc)<datetime.fromisoformat(watch['next_at']) or datetime.now(MSK).date()!=date(2026,11,1):raise ValueError('Not the due dated watch')
 if not c.create(ROOT+':lease',dict(started_at=stamp(),wb_writes=0,telegram_calls=0)):return
 w=WB();validate_identity(c,w);worker=runtime();worker.config()
 original=requests.sessions.Session.request
 from china_analytic_dialog import reading,allowed_read
 def guard(session,method,url,**kw):
  if url.startswith(c.url) and method.upper()in['GET','POST','PATCH']:return original(session,method,url,**kw)
  if allowed_read(method,url,kw.get('json')):return original(session,method,url,**kw)
  raise ValueError('Preparation permits no external write or Telegram send')
 requests.sessions.Session.request=guard
 state=dict(cabinet='token_3',watch_key=WATCH,watch_id='b85939ba',status='collecting',started_at=stamp(),wb_writes=0,telegram_sends=0,errors={})
 def save():c.put(ROOT+':checkpoint',json.loads(json.dumps(state)))
 try:
  with reading():
   inventory=w.req('/adv/v1/promotion/count')
   ids=sorted({a['advertId']for g in inventory.get('adverts',[])if g['status']in[4,7,9,11]for a in g.get('advert_list',[])})
   if not ids or len(ids)>50:raise ValueError('Advertising scope requires pagination')
   cps=w.campaigns(ids);state['campaigns']=cps
   stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-31&endDate=2026-11-01')
   if not isinstance(stats,list):raise ValueError('Advertising shape invalid')
   missing=set(ids)-{x['advertId']for x in stats};state['advertising_missing']=[cid for cid in missing if not(cps[str(cid)]['status']==4 and cps[str(cid)].get('timestamps',{}).get('started')is None)]
   state['advertising']=dict(rows=stats,observed_at=stamp(),currency='CNY');save()
   if any(cp['currency']!='CNY'for cp in cps.values()):raise ValueError('Campaign currency mismatch')
   orders={};cursor=0;seen=set();start=datetime(2026,10,31,tzinfo=MSK);end=datetime(2026,11,1,18,tzinfo=MSK)
   for page in range(30):
    response=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',headers={'Authorization':w.token},params=dict(limit=1000,next=cursor,dateFrom=int(start.timestamp()),dateTo=int(end.timestamp())),timeout=60);response.raise_for_status();j=response.json();part=j.get('orders')
    if not isinstance(part,list):raise ValueError('FBS rows unavailable, not zero')
    for r in part:
     if r['nmId']not in IDS:continue
     at=datetime.fromisoformat(r['createdAt'].replace('Z','+00:00')).astimezone(MSK)
     if start<=at<end:orders[r['id']]=dict(id=r['id'],nm_id=r['nmId'],created_at=at.isoformat())
    nxt=j.get('next')
    if not part or not nxt:break
    if nxt==cursor or nxt in seen:raise ValueError('FBS pagination incomplete')
    seen.add(cursor);cursor=nxt
   else:raise ValueError('FBS pagination bound exceeded')
   state['fbs']=dict(orders=list(orders.values()),complete=True,from_msk=start.isoformat(),to_msk=end.isoformat(),observed_at=stamp());save()
   try:
    from china_wb_evidence import Reports,FUNNEL,normalize_funnel
    selected=dict(start='2026-11-01',end='2026-11-01');past=dict(start='2026-10-31',end='2026-10-31')
    body=dict(selectedPeriod=selected,pastPeriod=past,nmIds=IDS,brandNames=[],subjectIds=[],tagIds=[],skipDeletedNm=False,orderBy=dict(field='openCard',mode='desc'),limit=1000,offset=0)
    response=Reports(worker).request(FUNNEL,body)
    if not response.get('available'):raise ValueError('General funnel '+str(response.get('status')))
    data=response['data']['data'];products=data['products']
    if data.get('currency')!='CNY' or len(products)>=1000:raise ValueError('General funnel currency/coverage')
    rows=normalize_funnel(products,selected,past,ROOT+':inputs')
    if {r['nm_id']for r in rows}!=set(IDS):raise ValueError('General funnel exact SKU coverage incomplete')
    state['funnel']=dict(rows=rows,observed_at=response['observed_at'],request=body,update_delay_hours=2);save()
   except Exception as ex:state['errors']['general_funnel']=str(ex)if isinstance(ex,ValueError)else type(ex).__name__
  state.update(status='complete'if not state['errors']and not state['advertising_missing']else'partial',completed_at=stamp());state=json.loads(json.dumps(state))
  if not c.create(ROOT+':inputs',state)or c.get(ROOT+':inputs')!=state:raise ValueError('Private input readback mismatch')
  rows=[];ads={}
  for cp in state['advertising']['rows']:
   for day in cp.get('days',[]):
    d=day['date'][:10]
    if d not in ['2026-10-31','2026-11-01']:continue
    for app in day.get('apps',[]):
     for n in app.get('nms',[]):
      if n['nmId']not in IDS:continue
      a=ads.setdefault((n['nmId'],d),dict(spend=0,amount=0,orders=0))
      for k,f in [('spend','sum'),('amount','sum_price'),('orders','orders')]:a[k]+=n[f]
  funnel={r['nm_id']:r for r in state.get('funnel',{}).get('rows',[])}
  at=datetime.fromisoformat(state['advertising']['observed_at']).astimezone(MSK).strftime('%H:%M')
  text='Китай · разовый отчёт Павлу · b85939ba\n31 октября — полный день. 1 ноября — неполный день.\nРеклама: фактический срез '+at+' МСК; точного рекламного среза на18:00 нет. FBS — строго до18:00 МСК.\n'
  for nm,article in zip(IDS,watch['articles']):
   text+='\n'+article+'\n'
   for d,label,key in [('2026-10-31','31.10 полный','past'),('2026-11-01','01.11 неполный','selected')]:
    a=ads.get((nm,d));f=funnel.get(nm,{}).get(key);count=sum(o['nm_id']==nm and o['created_at'][:10]==d for o in state['fbs']['orders'])
    text+=label+': WB-воронка '+(str(f['orders'])if f else'нет данных')+' заказанных товаров; FBS '+str(count)+' созданных. '
    if a is None:text+='Реклама: строки SKU нет, расход и ДРР не подтверждены.\n'
    else:text+='Реклама '+f'{a["spend"]:.2f}'+' ¥; атрибутировано '+str(a['orders'])+' на '+f'{a["amount"]:.2f}'+' ¥; ДРР '+(f'{100*a["spend"]/a["amount"]:.2f}%'if a['amount']>0 else'не определена')+'.\n'
    rows.append(dict(nm_id=nm,day=d,fbs_created=count,general_funnel=f,advertising=a))
  text+='\nWB-воронка: все источники, возможна задержка до2часов; сегодняшняя строка не является точным срезом на18:00. FBS — только сборочные задания, не весь кабинет и не выкупы. Рекламные атрибуции разных РК могут пересекаться: не складывать с общими заказами как уникальные. Разные окна не сравниваю как одинаковые. Рекомендаций и изменений WB нет. Разовый отчёт; ежедневного повтора нет.'
  if state['errors']:text+='\nПробел источника: '+json.dumps(state['errors'],ensure_ascii=False)
  if state['advertising_missing']:text+='\nНеполное покрытие рекламы: РК '+','.join(map(str,state['advertising_missing']))+'. Цифры — только полученная часть.'
  record=dict(status='prepared',text=text,chat_id=watch['chat_id'],source_key=ROOT+':inputs',rows=rows,prepared_at=stamp(),wb_writes=0)
  if not c.create(RECEIPTS+REPORT,record):raise ValueError('Another report preparation won; do not overwrite')
  if c.get(RECEIPTS+REPORT)!=record:raise ValueError('Prepared report readback mismatch')
  print(json.dumps(dict(status='prepared',input_status=state['status'],characters=len(text),errors=state['errors'],telegram_sends=0,wb_writes=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()

