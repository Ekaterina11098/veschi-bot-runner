"""All-source zero-order inventory report; unknown counts never become zero."""
import re,math
from datetime import datetime,timedelta,date,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow');PREFIX='china_agent:zero_orders:v1:'
def recognizes(text):
 return bool(re.search(r'без\s+заказ|не\s+имеют\s+заказ|нет\s+заказ|не\s+было\s+заказ',text,re.I))
def period(text,now):
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
def collect(w,first,last):
 from china_wb_evidence import Reports
 source=Reports(w).funnel(first,last)
 report=compute(w.catalog(),source,first,last);w.save(PREFIX+first+':'+last,report);return report

def text_report(report):
 a,b=report['period_from'],report['period_to'];lines=[f'Все заказы за {a}—{b}, 14 полных дней МСК.' if (date.fromisoformat(b)-date.fromisoformat(a)).days==13 else f'Все заказы за {a}—{b}, полные дни МСК.',f"Товаров без заказов: {report['zero_count']}. С заказами: {report['positive_count']}. Неполные данные: {report['unknown_count']}.",'Счётчик общей воронки WB: все источники, включая рекламу и органику; не только рекламные заказы и не выкупы.']
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
   for i,line in enumerate([f"Без заказов: {report['zero_count']} · С заказами: {report['positive_count']} · Неполные данные: {report['unknown_count']}",'Общая воронка WB: реклама + органика; заказы не заменены выкупами.', 'Отсутствующий товар/счётчик/день не считается нулём. Изменений WB нет.', 'Срез: '+str(report['observed_at'])]):d.text((35,y+35*i),line,font=font(22),fill='#455568')
   b=io.BytesIO();im.save(b,format='PNG');files.append(dict(family=family,page=page,total=len(groups),bytes=b.getvalue()))
 return files

