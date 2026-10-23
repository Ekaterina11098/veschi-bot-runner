"""Frozen PNG answers for explicitly requested advertising cost trends; no WB writes."""
import base64,hashlib,io,json,re
from datetime import timedelta
from decimal import Decimal
from PIL import Image,ImageDraw,ImageFont
from china_three_day_ads import build,load,requested_days,MSK
PREFIX='CHINA_AD_COST_PNG:'
def suggestion(row,source,today):
 active=[];complete=True
 for o in source.get('observations',[]):
  if o.get('tool')!='wbbidder_campaign':continue
  if o.get('status')!='received' or o.get('scope_verified') is not True:complete=False;continue
  c=o['data'].get('campaign') or {}
  if c.get('status_id')!=9:continue
  for s in c.get('settings',[]):
   wb=s.get('wb') or {};bids=wb.get('nm_bids',[])
   if wb.get('nm_bids_total')!=len(bids):complete=False
   for b in bids:
    if str(b['nm_id'])!=row['nm']:continue
    old=(b.get('bids_kopecks') or {}).get('recommendations')
    minimum=(o['data'].get('min_bids') or {}).get('recommendation')
    if wb.get('currency')!='CNY' or wb.get('payment_type')!='cpc' or not wb.get('placements',{}).get('recommendations'):
     active.append((c['wb_id'],None,None));continue
    active.append((c['wb_id'],old/100 if old is not None else None,minimum))
 until=str(today+timedelta(days=1))[5:].replace('-','.')
 if not active:return ('Оставить вне РК; пересмотр '+until) if complete else 'Проверить актуальное участие SKU в РК'
 def fmt(x):return f'{x:g}'.replace('.',',')
 actions=[]
 for cid,old,minimum in active:
  if row['drr'] is not None and row['drr']>10:
   actions.append('Тест: пауза SKU в РК '+str(cid)+' до '+until)
  elif row['drr'] is not None and row['drr']>5 and old is not None and minimum is not None and old>minimum:
   step=source.get('identity',{}).get('info',{}).get('cpc_step')
   if step and Decimal(str(minimum))%Decimal(str(step))==0:
    actions.append('Ставка '+fmt(old)+' → '+fmt(minimum)+' ¥; РК '+str(cid))
   else:actions.append('Проверить шаг ставки SKU в РК '+str(cid))
  elif old is not None:actions.append('Оставить '+fmt(old)+' ¥; РК '+str(cid)+'; пересмотр '+until)
  else:actions.append('Проверить ставку SKU в РК '+str(cid))
 return '\n'.join(actions)
def render(report,recommendations):
 def f(n,b=False):
  for path in [('C:/Windows/Fonts/arialbd.ttf' if b else 'C:/Windows/Fonts/arial.ttf'),('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if b else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]:
   try:return ImageFont.truetype(path,n)
   except OSError:pass
  return ImageFont.load_default(size=n)
 def num(v):return 'н/д' if v is None else f'{v:.1f}'.replace('.',',')
 rows=[r for r in report['rows'] if r['rising_all_days']]
 if not rows:
  im=Image.new('RGB',(1400,360),'#f3f6fa');d=ImageDraw.Draw(im)
  d.text((30,35),'Китай · рост стоимости рекламного заказа',font=f(32,True),fill='#20374f')
  d.text((30,110),'Последовательного роста за весь период не выявлено.',font=f(27),fill='#20374f')
  d.text((30,190),report['days'][0]+' — '+report['days'][-1]+' · '+str(report['requested_days'])+' полных дней',font=f(23),fill='#607287')
  d.text((30,245),'Только доступная рекламная атрибуция; дни без заказов не дают стоимости.',font=f(22),fill='#607287')
  buf=io.BytesIO();im.save(buf,format='PNG');return [buf.getvalue()]
 def write(d,text,x,y,w,font,color):
  for para in text.split('\n'):
   line=''
   for word in para.split():
    v=(line+' '+word).strip()
    if d.textlength(v,font=font)>w and line:
     d.text((x,y),line,font=font,fill=color);y+=font.size+5;line=word
    else:line=v
   d.text((x,y),line,font=font,fill=color);y+=font.size+5
 pages=[]
 for offset in range(0,len(report['days']),5):
  dates=report['days'][offset:offset+5]
  for begin in range(0,len(rows),10):
   group=rows[begin:begin+10];widths=[350]+[115]*len(dates)+[150,130,570]
   w=sum(widths)+40;h=260+len(group)*145+135
   im=Image.new('RGB',(w,h),'#f3f6fa');d=ImageDraw.Draw(im)
   d.rectangle((0,0,w,140),fill='#20374f')
   d.text((25,20),'Китай · стоимость рекламного заказа',font=f(32,True),fill='white')
   d.text((25,70),report['days'][0]+' — '+report['days'][-1]+' · '+str(report['requested_days'])+' полных дней · ¥ CNY',font=f(24),fill='white')
   d.text((25,163),'Только рост каждый день всего периода. Предложения не применены.',font=f(22,True),fill='#b9252b')
   heads=['Артикул']+[day[8:]+'.'+day[5:7]+', ¥' for day in dates]+['Δ периода','ДРР','Предложение']
   x=20
   for col,head in zip(widths,heads):
    d.rectangle((x,211,x+col,254),fill='#20374f');d.text((x+10,222),head,font=f(18,True),fill='white');x+=col
   for i,r in enumerate(group):
    y=260+i*145;d.rectangle((20,y,w-20,y+140),fill='white' if i%2==0 else '#e6edf6')
    delta=r['cpa_first_last_percent']
    values=[r['article']]+[num(v['cpa']) for v in r['daily'][offset:offset+len(dates)]]+[('н/д' if delta is None else f'{delta:+.1f}%'.replace('.',',')),num(r['drr'])+'%',recommendations.get(r['nm'],'Нужна проверка текущей РК')]
    x=20
    for k,(col,value) in enumerate(zip(widths,values)):
     color='#b9252b' if 1<=k<=len(dates)+1 else '#24384f'
     write(d,value,x+10,y+20,col-20,f(20,k==0),color);x+=col
    x=20+widths[0]
    for v,col in zip(r['daily'][offset:offset+len(dates)],widths[1:]):
     d.text((x+10,y+98),str(v['orders'])+' зак.',font=f(17),fill='#607287');x+=col
   y=265+len(group)*145
   for line in ['Стоимость = расход / рекламные заказы. Это рекламная атрибуция, не прибыль и не все заказы WB.',
                'ДРР периода — по суммам. Δ — последний день к первому. Малая выборка не доказывает устойчивость.',
                'Тренд проверен по всему периоду; в длинном отчёте даты разбиты на читаемые блоки.']:
    write(d,line,25,y,w-50,f(18),'#607287');y+=32
   buf=io.BytesIO();im.save(buf,format='PNG');pages.append(buf.getvalue())
 return pages
def answer(w,job,history=()):
 text=job.get('request_text','').casefold()
 related=' '.join([text]+[x.get('request_text','').casefold() for x in history[-4:]])
 if not re.search(r'реклам|дрр|ддр|стоимост.*заказ',related):return None
 if not re.search(r'стоимост.*заказ|цен.*заказ|(?:за|последни[ех])\s+(?:последние\s+)?\d+\s*(?:полных\s+)?(?:дн|сут|день)',text):return None
 key='china_agent:ad_cost_png:question:'+str(job['id'])+':v1'
 saved=w.get(key)
 if not saved:
  try:
   count=requested_days(text,history);sources=load(w,count);today=w.now.astimezone(MSK).date()
   report=build(sources,today,dict(w.catalog()),count)
   recs={r['nm']:suggestion(r,sources[-1],today) for r in report['rows'] if r['rising_all_days']}
   blobs=render(report,recs)
  except (ValueError,KeyError,TypeError) as e:return ('Расчёт ограничен: '+str(e)+'. Недостающие дни не заменяю другими.',[{'name':'ad_cost_png_blocked','reason':str(e),'wb_writes':0}])
  saved=dict(job_id=job['id'],chat_id=job['chat_id'],days=report['days'],status='frozen',files=[dict(sha256=hashlib.sha256(b).hexdigest(),data=base64.b64encode(b).decode()) for b in blobs])
  if not w.save(key,saved,insert=True):saved=w.get(key)
 if saved['job_id']!=job['id'] or saved['chat_id']!=job['chat_id']:raise ValueError('PNG scope changed')
 markers=[PREFIX+key+':'+str(i) for i in range(len(saved['files']))]
 return '\n[[ПРЕДЛОЖЕНИЯ]]\n'.join(markers),[{'name':'ad_cost_png','key':key,'days':saved['days'],'format':'approved_variant1','wb_writes':0}]
def photo(w,chat,text):
 if not text.startswith(PREFIX):return None
 key,index=text[len(PREFIX):].rsplit(':',1)
 saved=w.get(key)
 if not saved or saved.get('status')!='frozen' or saved.get('chat_id')!=chat or saved.get('job_id')!=getattr(w,'active_question_id',None):raise PermissionError('Frozen PNG question scope')
 part=saved['files'][int(index)];blob=base64.b64decode(part['data'],validate=True)
 if hashlib.sha256(blob).hexdigest()!=part['sha256']:raise ValueError('Frozen PNG hash changed')
 return blob,'Стоимость рекламного заказа · '+saved['days'][0]+' — '+saved['days'][-1]+'. Предложения не применены.'
