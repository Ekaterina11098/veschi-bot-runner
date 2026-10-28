"""Current MoySklad stock split for an all-source zero-order report."""
import math,os
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
KEY='china_agent:zero_orders:v1:stock:'
def collect_stock(w):
 import requests
 now=datetime.now(timezone.utc);key=KEY+now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat();old=w.get(key)
 if old and old.get('complete') and (now-datetime.fromisoformat(old['observed_at'])).total_seconds()<900:return old
 base='https://api.moysklad.ru/api/remap/1.2';headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN']}
 def get(path,params):
  r=requests.get(base+path,params=params,headers=headers,timeout=60)
  if not r.ok:raise ValueError('MoySklad HTTP '+str(r.status_code))
  return r.json()
 stores=get('/entity/store',{'limit':1000})
 if stores.get('meta',{}).get('size',1001)>len(stores.get('rows',[])):raise ValueError('Store pagination incomplete')
 selected=[s for s in stores.get('rows',[]) if s.get('name')=='МСК' and not s.get('archived')]
 if len(selected)!=1:raise ValueError('Warehouse identity ambiguous')
 rows=[];offset=0
 while True:
  j=get('/report/stock/all',{'filter':'store='+selected[0]['meta']['href'],'stockMode':'all','limit':1000,'offset':offset});part=j.get('rows');size=j.get('meta',{}).get('size')
  if not isinstance(part,list) or type(size) is not int:raise ValueError('Stock coverage unknown')
  rows+=part
  if len(rows)>=size:break
  if not part or offset>50000:raise ValueError('Stock pagination incomplete')
  offset+=len(part)
 result=dict(complete=True,source='МойСклад / МСК',warehouse_id=selected[0]['id'],observed_at=now.isoformat(),rows=[dict(article=r.get('article'),stock=r.get('stock'),reserve=r.get('reserve')) for r in rows],source_key=key)
 w.save(key,result);return result

def attach(report,source):
 by={}
 for row in source.get('rows',[]):by.setdefault(str(row.get('article','')).casefold(),[]).append(row)
 valid=source.get('complete') is True
 try:valid=valid and 0<=(datetime.now(timezone.utc)-datetime.fromisoformat(source['observed_at'])).total_seconds()<900
 except (KeyError,ValueError,TypeError):valid=False
 groups={k:[] for k in ['available','empty','reserved','unknown']}
 for row in report['zero']+report['unknown']:
  found=by.get(row['article'].casefold(),[]);r=found[0] if len(found)==1 else {};s=r.get('stock');v=r.get('reserve')
  numeric=lambda x:type(x) in (int,float) and math.isfinite(x)
  if not valid or len(found)!=1 or not numeric(s) or not numeric(v) or v<0:
   state=dict(group='unknown',stock=None,reserve=None,available=None,reason='Остаток не подтвержден: источник/строка/резерв неполны')
  else:
   a=s-v;group='empty' if s<=0 else ('reserved' if a<=0 else 'available');state=dict(group=group,stock=s,reserve=v,available=a)
  row['moysklad']=state
  if row.get('orders')==0:groups[state['group']].append(row)
 report['stock_groups']=groups;report['stock_source']={k:source.get(k) for k in ['source','source_key','observed_at','warehouse_id','complete']};report['stock_counts']={k:len(v) for k,v in groups.items()}
 return report

def enrich(w,report):
 try:source=collect_stock(w)
 except Exception as e:source=dict(complete=False,source='МойСклад / МСК',error=type(e).__name__)
 return attach(report,source)

def text(report):
 if 'stock_groups' not in report:return ''
 labels=dict(available='Остаток есть',empty='Нет остатка на МСК',reserved='Весь остаток в резерве',unknown='Остаток не подтвержден')
 lines=['','Текущие остатки МойСклад / МСК (это не история наличия за 14 дней):']
 for key,rows in report['stock_groups'].items():
  if not rows:continue
  lines+=['',labels[key]+': '+str(len(rows)),'| Артикул | Остаток | Резерв | Свободно |','|---|---:|---:|---:|']
  for r in rows:
   st=r['moysklad'];fmt=lambda x:'неизвестно' if x is None else f'{x:g}'
   lines.append('| '+r['article']+' | '+' | '.join(fmt(st[k]) for k in ['stock','reserve','available'])+' |')
 lines+=['Срез остатков: '+str(report['stock_source'].get('observed_at'))+'. Отсутствие строки не означает нулевой остаток.']
 return '\n'.join(lines)

def render(report):
 from PIL import Image,ImageDraw,ImageFont
 from china_zero_orders import render as old_render
 import io
 labels=dict(available='Без заказов · остаток есть',empty='Без заказов · нет остатка МСК',reserved='Без заказов · весь остаток в резерве',unknown='Без заказов · остаток неизвестен')
 def font(n,b=False):
  for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf','C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf')]:
   try:return ImageFont.truetype(p,n)
   except OSError:pass
  return ImageFont.load_default(size=n)
 files=[]
 for key,rows in report['stock_groups'].items():
  parts=[rows[i:i+22] for i in range(0,len(rows),22)]
  for page,part in enumerate(parts,1):
   im=Image.new('RGB',(1900,510+len(part)*70),'#eef3f7');d=ImageDraw.Draw(im);d.rectangle((0,0,1900,175),fill='#193e52')
   d.text((35,25),labels[key],font=font(38,True),fill='white');d.text((35,85),report['period_from']+'—'+report['period_to']+' · все заказы · '+str(page)+'/'+str(len(parts)),font=font(25),fill='white')
   for x,t in [(35,'Артикул'),(850,'Все заказы'),(1150,'Остаток'),(1400,'Резерв'),(1650,'Свободно')]:d.text((x,199),t,font=font(24,True),fill='#193e52')
   for i,r in enumerate(part):
    y=245+i*70;d.rounded_rectangle((20,y-3,1880,y+59),8,fill='white');d.text((35,y+9),r['article'],font=font(25),fill='#111111');d.text((850,y+9),'0',font=font(25),fill='#111111')
    for x,k in [(1150,'stock'),(1400,'reserve'),(1650,'available')]:
     v=r['moysklad'][k];d.text((x,y+9),'?' if v is None else f'{v:g}',font=font(25),fill='#111111')
   y=260+len(part)*70
   obs=report['stock_source'].get('observed_at');obs=datetime.fromisoformat(obs).astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y %H:%M МСК') if obs else 'не подтвержден'
   lines=[f"Без заказов: {report['zero_count']} · в этой группе: {len(rows)} · неполные заказы: {report['unknown_count']}",'МойСклад / МСК: свободно = остаток − резерв. Срез: '+obs,'Остатки текущие; наличие за 14 дней не подтверждают.','Все источники заказов WB; пропуск данных не ноль. Изменений WB нет.']
   for i,line in enumerate(lines):d.text((35,y+35*i),line,font=font(22),fill='#455568')
   b=io.BytesIO();im.save(b,format='PNG');files.append(dict(family=key,page=page,total=len(parts),bytes=b.getvalue()))
 other=dict(report,zero=[])
 files+=[dict(f,family='unknown_orders') for f in old_render(other)]
 return files

