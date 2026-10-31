"""Answer expense/DRR questions directly; descriptive data never invokes bid selection."""
import math,re
from datetime import datetime,timezone
from china_article_diagnostic import MSK,fresh

def requested(text,history=()):
 if re.search(r'сделай|пополни|выключи|поставь|измени|подними',text,re.I):return False
 context=' '.join(h.get('request_text','') for h in history[-4:])
 own=bool(re.search(r'дрр|ддр',text,re.I) and re.search(r'расход|трат|таблиц|лидер|артикул|отсорт',text,re.I))
 follow=bool(re.search(r'хочу сам посмотреть|это не то что я просил|без заказов.*расход|перед высоким',text,re.I) and re.search(r'дрр|ддр',context,re.I))
 return own or follow

def table(stats,labels,threshold=0):
 rows={};missing=[]
 def num(v):
  if type(v) not in (int,float) or not math.isfinite(v) or v<0:raise ValueError('Unknown advertising counter')
  return v
 for c in stats:
  for d in c.get('days',[]):
   for app in d.get('apps',[]):
    for n in app.get('nms',[]):
     nm=n['nmId']
     if nm not in labels:missing.append(nm);continue
     r=rows.setdefault(nm,dict(nm_id=nm,article=labels[nm],spend=0,amount=0,orders=0))
     for k,f in [('spend','sum'),('amount','sum_price'),('orders','orders')]:r[k]+=num(n.get(f))
 result=[]
 for r in rows.values():
  if r['spend']<=0:continue
  r['drr']=r['spend']/r['amount']*100 if r['amount']>0 else None
  r['zero_orders']=r['orders']==0
  if r['zero_orders'] or r['drr'] is None or r['drr']>=threshold:result.append(r)
 result.sort(key=lambda r:(0 if r['zero_orders'] else 1 if r['drr'] is None else 2,-(r['spend'] if r['drr'] is None else r['drr']),-r['spend'],r['article']))
 return result,sorted(set(missing))

def read(w):
 from china_price_apply import IO
 from china_advertising_v2 import http
 from china_analytic_dialog import reading
 today=w.now.astimezone(MSK).date().isoformat();key='china_agent:ad_expense_table:v1:'+today
 saved=w.get(key)
 if saved and fresh(saved,w.now,900):return saved
 io=IO()
 with reading():
  cfg=http(io,'/api/advert/v1/config')
  if cfg.get('currency')!='CNY':raise ValueError('Cabinet advertising currency not CNY')
  inv=http(io,'/adv/v1/promotion/count')
  ids=sorted({x['advertId'] for g in inv.get('adverts',[]) if g.get('status') in [4,7,9,11] for x in g.get('advert_list',[])})
  if not ids or len(ids)>1000:raise ValueError('Advertising catalogue missing/too large')
  stats=[]
  for offset in range(0,len(ids),50):
   part=http(io,'/adv/v3/fullstats?ids='+','.join(map(str,ids[offset:offset+50]))+'&beginDate='+today+'&endDate='+today)
   if not isinstance(part,list):raise ValueError('Advertising response missing')
   stats+=part
  # A campaign omitted by WB remains unknown; never synthesize its zero spend.
  missing=sorted(set(ids)-{s['advertId'] for s in stats})
  for s in stats:s['days']=[d for d in s.get('days',[]) if d.get('date','')[:10]==today]
 value=dict(observed_at=datetime.now(timezone.utc).isoformat(),date_msk=today,cabinet='token_3',currency='CNY',stats=stats,missing_campaign_ids=missing,wb_writes=0,telegram_sends=0)
 w.save(key,value);return value

def handle(w,job,history):
 if job.get('chat_id')!=-1004342917488 or not requested(job.get('request_text',''),history):return None
 source=read(w);labels={int(n):a for n,a in w.catalog()}
 # Explicit today request is diagnostic, not a completed-day action recommendation.
 text=job['request_text'];match=re.search(r'(?:выше|больше|>)\s*(\d+(?:[.,]\d+)?)\s*%',text,re.I)
 rows,unknown=table(source['stats'],labels,float(match[1].replace(',','.')) if match else 0)
 cutoff=datetime.fromisoformat(source['observed_at'].replace('Z','+00:00')).astimezone(MSK).strftime('%d.%m %H:%M МСК')
 note='Сначала расходы без рекламных заказов; затем ДРР по убыванию. Срез '+cutoff+'. Сегодня неполный день. ДРР=сумма расходов/атрибутированная сумма заказов; не выкупы. Заказы разных РК могут пересекаться. Это данные для просмотра, не рекомендации менять рекламу.'
 if source.get('missing_campaign_ids'):note+=' Нет данных по '+str(len(source['missing_campaign_ids']))+' РК; итог неполный, пропуск не0.'
 if unknown:note+=' Не сопоставлено артикулов: '+str(len(unknown))+'.'
 data=[[r['article'],f"{r['spend']:.2f} CNY",'Не определена: 0 рекламных заказов' if r['zero_orders'] else 'Не определена: нет суммы заказов' if r['drr'] is None else f"{r['drr']:.2f}%"] for r in rows]
 if not data:return 'По полученным строкам нет артикулов с расходами под выбранное условие. '+note,[dict(name='ad_expense_table',read_only=True,wb_writes=0)]
 # Existing durable table delivery renders this as PNG with the actual message receipt.
 answer=note+'\n\n| Артикул | Траты сегодня | ДРР |\n|---|---:|---:|\n'+'\n'.join('| '+' | '.join(r)+' |' for r in data)
 return answer,[dict(name='ad_expense_table',source_key='china_agent:ad_expense_table:v1:'+source['date_msk'],row_count=len(rows),read_only=True,wb_writes=0)]
