"""All-source zero-order inventory report; unknown counts never become zero."""
import re,math
from datetime import datetime,timedelta,date,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow');PREFIX='china_agent:zero_orders:v1:'
def recognizes(text):
 return bool(re.search(r'без\s+заказ|не\s+имеют\s+заказ|нет\s+заказ|не\s+было\s+заказ',text,re.I))
def period(text,now):
 explicit=re.search(r'(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*октябр',text,re.I)
 if explicit:
  first=date(now.astimezone(MSK).year,10,int(explicit[1]));last=date(first.year,10,int(explicit[2]))
  if not 0<=(last-first).days<31 or last>=now.astimezone(MSK).date():raise ValueError('Нужен завершённый период 1–31 день')
  return str(first),str(last)
 m=re.search(r'(\d+)\s*дн',text,re.I);n=int(m[1]) if m else 14
 if not 1<=n<=31:raise ValueError('Для этого отчёта нужен период 1–31 полный день')
 last=now.astimezone(MSK).date()-timedelta(days=1);return str(last-timedelta(days=n-1)),str(last)
def compute(catalogue,source,first,last):
 if source.get('cabinet')!='token_3' or source.get('currency')!='CNY':raise ValueError('China source identity/currency missing')
 bynm={};duplicates=set()
 for r in source.get('rows',[]):
  nm=r.get('nm_id')
  if type(nm) is not int:raise ValueError('Product identity missing')
  if nm in bynm:duplicates.add(nm)
  bynm[nm]=r
 labels={int(n):a for n,a in catalogue};labels.update({n:r.get('article') or labels.get(n,'WB '+str(n)) for n,r in bynm.items()})
 zero=[];positive=[];unknown=[]
 complete=source.get('complete') is True and source.get('period_from')==first and source.get('period_to')==last
 for nm,article in sorted(labels.items(),key=lambda x:x[1].casefold()):
  r=bynm.get(nm);s=(r or {}).get('selected') or {};count=s.get('orders');reason=None
  if nm in duplicates:reason='Дубли строк источника'
  elif r is None:reason='Товар отсутствует в ответе общей воронки'
  elif s.get('scope')!='all_sources':reason='Нет подтверждения учёта всех источников заказов'
  elif s.get('period_from')!=first or s.get('period_to')!=last:reason='Период товара покрыт не полностью'
  elif type(count) is not int or count<0:reason='Счётчик всех заказов отсутствует или некорректен'
  elif not complete:reason='Сбор общего периода или пагинация не завершены'
  row=dict(nm_id=nm,article=article)
  if reason:unknown.append(dict(row,orders=None,reason=reason));continue
  row['orders']=count
  (zero if count==0 else positive).append(row)
 return dict(period_from=first,period_to=last,scope='all_sources',source='WB sales funnel',source_key=source.get('source_key'),observed_at=source.get('observed_at'),collection_complete=complete,zero=zero,positive=positive,unknown=unknown,total_products=len(labels),zero_count=len(zero),positive_count=len(positive),unknown_count=len(unknown),total_orders=sum(r['orders'] for r in positive),wb_writes=0)
def created_counts(w,first,last):
 import os,requests,time
 key=PREFIX+'created:'+first+':'+last;old=w.get(key)
 if old and old.get('complete') and (datetime.now(timezone.utc)-datetime.fromisoformat(old['observed_at'])).total_seconds()<3600:return old
 begin=datetime.combine(date.fromisoformat(first),datetime.min.time(),MSK);end=datetime.combine(date.fromisoformat(last)+timedelta(days=1),datetime.min.time(),MSK)
 cursor=0;seen={};pages=0
 while True:
  response=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',params=dict(limit=1000,next=cursor,dateFrom=int(begin.timestamp()),dateTo=int(end.timestamp())),headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=60)
  if not response.ok:raise ValueError('Created orders HTTP '+str(response.status_code))
  data=response.json();rows=data.get('orders')
  if not isinstance(rows,list):raise ValueError('Created-order page missing')
  pages+=1
  for row in rows:
   if type(row.get('nmId')) is not int or not row.get('id') or not row.get('createdAt'):raise ValueError('Created-order identity missing')
   at=datetime.fromisoformat(row['createdAt'].replace('Z','+00:00')).astimezone(MSK)
   if begin<=at<end:seen[row['id']]=row['nmId']
  nxt=data.get('next')
  if not rows or not nxt:break
  if nxt==cursor or pages>=40:raise ValueError('Created-order pagination incomplete')
  cursor=nxt;time.sleep(1)
 counts={}
 for nm in seen.values():counts[str(nm)]=counts.get(str(nm),0)+1
 result=dict(complete=True,cabinet='token_3',scope='all_created_FBS',source='WB Marketplace created orders',source_key=key,period_from=first,period_to=last,observed_at=datetime.now(timezone.utc).isoformat(),counts=counts,total_orders=len(seen),pages=pages,includes_cancelled_created_orders=True,wb_writes=0)
 w.save(key,result);return result

def reconcile_created(report,created):
 if not created.get('complete') or created.get('period_from')!=report['period_from'] or created.get('period_to')!=report['period_to'] or created.get('cabinet')!='token_3':raise ValueError('Created-order coverage incomplete')
 kept=[]
 for row in report['zero']:
  n=created['counts'].get(str(row['nm_id']),0)
  if n>0:report['unknown'].append(dict(nm_id=row['nm_id'],article=row['article'],orders=None,reason='В воронке 0, но созданных FBS-заказов '+str(n)))
  else:kept.append(row)
 report['zero']=kept;report.update(zero_count=len(kept),unknown_count=len(report['unknown']),created_orders_crosscheck=dict(source_key=created['source_key'],observed_at=created['observed_at'],total_created_orders=created['total_orders'],pages=created['pages']))
 return report

def collect(w,first,last):
 from china_wb_evidence import Reports
 source=Reports(w).funnel(first,last)
 report=reconcile_created(compute(w.catalog(),source,first,last),created_counts(w,first,last));w.save(PREFIX+first+':'+last,report);return report

def text_report(report):
 a,b=report['period_from'],report['period_to'];lines=[f'Все заказы за {a}—{b}, 14 полных дней МСК.' if (date.fromisoformat(b)-date.fromisoformat(a)).days==13 else f'Все заказы за {a}—{b}, полные дни МСК.',f"Товаров без заказов: {report['zero_count']}. С заказами: {report['positive_count']}. Неполные данные: {report['unknown_count']}.",'Общая воронка WB и сверка созданных FBS-заказов: реклама и органика; источники не складываются, заказы не заменяются выкупами.']
 if report['zero']:
  lines+=['','Подтверждено 0 заказов за весь период:','| Артикул | Все заказы |','|---|---|']+[f"| {r['article']} | 0 |" for r in report['zero']]
 else:lines+=['','Подтверждённых товаров с нулём заказов нет.']
 if report['unknown']:
  lines+=['','Неполные данные — это не ноль заказов:','| Артикул | Причина |','|---|---|']+[f"| {r['article']} | {r['reason']} |" for r in report['unknown']]
 lines+=['', 'Срез: '+str(report['observed_at'])+'. Список не является рекомендацией выключать рекламу или менять товар.']
 return '\n'.join(lines)
def answer(w,job,history):
 if not recognizes(job.get('request_text','')):return None
 first,last=period(job['request_text'],w.now)
 try:
  report=collect(w,first,last)
 except (ValueError,KeyError,TypeError) as error:
  return ('Список без заказов не подтверждён: '+str(error)+'. Отсутствие данных не считаю нулём. Экономика для этого отчёта не требуется.',[dict(name='all_source_zero_orders',available=False,period_from=first,period_to=last)])
 return text_report(report),[dict(name='all_source_zero_orders',period_from=first,period_to=last,zero_count=report['zero_count'],unknown_count=report['unknown_count'],scope='all_sources',wb_writes=0)]

def render(report):
 from PIL import Image,ImageDraw,ImageFont
 import io
 def font(n,b=False):
  for path in ['/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf','C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf')]:
   try:return ImageFont.truetype(path,n)
   except OSError:pass
  return ImageFont.load_default(size=n)
 files=[]
 for family,rows in [('zero',report['zero']),('unknown',report['unknown'])]:
  if not rows:continue
  groups=[rows[i:i+22] for i in range(0,len(rows),22)]
  for page,group in enumerate(groups,1):
   im=Image.new('RGB',(1900,470+len(group)*70),'#eef3f7');d=ImageDraw.Draw(im)
   d.rectangle((0,0,1900,175),fill='#193e52')
   title='Товары без заказов' if family=='zero' else 'Неполные данные — не ноль заказов'
   d.text((35,25),title,font=font(38,True),fill='white');d.text((35,85),report['period_from']+'—'+report['period_to']+' · все источники заказов · '+str(page)+'/'+str(len(groups)),font=font(25),fill='white')
   d.text((35,199),'Артикул',font=font(25,True),fill='#193e52');d.text((950,199),'Все заказы' if family=='zero' else 'Пробел данных',font=font(25,True),fill='#193e52')
   for i,r in enumerate(group):
    y=245+i*70;d.rounded_rectangle((20,y-3,1880,y+59),8,fill='white');d.text((35,y+9),r['article'],font=font(25),fill='#111111');d.text((950,y+9),'0' if family=='zero' else r['reason'],font=font(23),fill='#111111')
   y=260+len(group)*70
   for i,line in enumerate([f"Без заказов: {report['zero_count']} · С заказами: {report['positive_count']} · Неполные данные: {report['unknown_count']}",'Все источники WB + сверка созданных FBS-заказов; не выкупы.', 'Отсутствующий товар/счётчик/день не считается нулём. Изменений WB нет.', 'Срез: '+str(report['observed_at'])]):d.text((35,y+35*i),line,font=font(22),fill='#455568')
   b=io.BytesIO();im.save(b,format='PNG');files.append(dict(family=family,page=page,total=len(groups),bytes=b.getvalue()))
 return files

