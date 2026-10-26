"""Read-only tracked search-cohort appendix, using existing daily collection only."""
import copy,io as bio,math
from datetime import datetime,timedelta,date
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
CONFIG='china_agent:search_trials:v1'
FIELDS={'spend':'sum','clicks':'clicks','baskets':'atbs','orders':'orders','amount':'sum_price'}
def zero():return {k:0 for k in FIELDS}
def add(a,b):
 return {k:None if a.get(k)is None or b.get(k)is None else a[k]+b[k] for k in FIELDS}
def metric(n):
 out={}
 for k,f in FIELDS.items():
  v=n.get(f)
  if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:out[k]=None
  else:out[k]=v
 return out
def sku_days(cp,nm):
 if cp is None:return None
 out={}
 for d in cp.get('days',[]):
  key=d['date'][:10];v=zero()
  for app in d.get('apps',[]):
   for n in app.get('nms',[]):
    if n['nmId']==nm:v=add(v,metric(n))
  out[key]=v
 return out
def ratio(v):
 return 100*v['spend']/v['amount'] if v and v.get('spend')is not None and v.get('amount') and v['amount']>0 else None
def start_day(text):return datetime.fromisoformat(text.replace('Z','+00:00')).astimezone(MSK).date().isoformat()
def compute(source,cfg,previous_days=None):
 cs={c['id']:c for b in source.get('batches',{}).values() for c in b.get('campaigns',{}).get('adverts',[])}
 stats={c['advertId']:c for b in source.get('batches',{}).values() for c in b.get('stats',[])}
 base={c['advertId']:c for c in cfg.get('baseline_fullstats',[])}
 ledger=copy.deepcopy(previous_days or {});rows=[]
 for item in cfg['items']:
  cid=item['campaign_id'];nm=item['nm_id'];key=str(cid)+':'+str(nm);campaign=cs.get(cid)
  row=dict(item=copy.deepcopy(item),campaign_id=cid,nm_id=nm,article=item['article'],group=item.get('group'),today=None,total=None,days={},state='unknown')
  if campaign is None:row['decision']='РК отсутствует в текущем срезе';rows.append(row);continue
  current={n['nm_id']:n for n in campaign.get('nm_settings',[])}
  row['bid_minor']=current.get(nm,{}).get('bids_kopecks',{}).get('search')
  if item.get('pending_activation') and campaign['status']==4:
   row.update(state='pending_activation',decision='Черновик: ожидает пополнения и запуска');rows.append(row);continue
  at=item.get('added_at') or cfg['started_at']
  if item.get('pending_activation'):
   started=campaign.get('timestamps',{}).get('started')
   if not started:row['decision']='Время запуска WB не подтверждено';rows.append(row);continue
   if datetime.fromisoformat(started.replace('Z','+00:00'))>datetime.fromisoformat(at.replace('Z','+00:00')):at=started
  first=start_day(at);row['start_day']=first
  raw=sku_days(stats.get(cid),nm)
  if raw is None:row['decision']='WB не вернул статистику РК';rows.append(row);continue
  prior=sku_days(base.get(cid),nm) or {}
  baseline_day=start_day(cfg['baseline_observed_at'] if cfg.get('baseline_observed_at') else cfg['started_at'])
  days=ledger.setdefault(key,{})
  for d,v in raw.items():
   if d<first:continue
   v=copy.deepcopy(v)
   if d==first==baseline_day and not item.get('pending_activation'):
    old=prior.get(d,zero())
    for k in FIELDS:
     if v[k]is None or old[k]is None or v[k]<old[k]:v[k]=None
     else:v[k]-=old[k]
   days[d]=v
  row['days']=copy.deepcopy(days)
  total=zero()
  for d,v in sorted(days.items()):total=add(total,v)
  row['total']=total;row['today']=days.get(source['period_to'])
  row['full_days']=sum(d>first and d<source['report_day'] for d in days)
  row['state']='excluded' if nm not in current else 'active' if campaign['status']==9 else 'inactive'
  if row['state']=='excluded':row['decision']='Исключён из РК; история сохранена'
  elif row['state']=='inactive':row['decision']='РК не активна; проверить статус'
  elif any(v is None for v in total.values()):row['decision']='Пересчёт или неполные данные WB'
  elif row['full_days']==0:row['decision']='Первого полного дня после запуска ещё нет'
  elif total['spend']==0:row['decision']='Нет расхода: проверить доступность показов'
  elif total['orders']==0:row['decision']='Расход без заказов: оценить исключение' if total['clicks']>=30 else 'Пока мало кликов для оценки'
  elif ratio(total)is None:row['decision']='Сумма рекламных заказов не подтверждена'
  elif ratio(total)>5:row['decision']='ДРР выше5%: не повышать ставку, оценить исключение'
  else:row['decision']='ДРР в цели; продолжить наблюдение'
  rows.append(row)
 return rows,ledger
def render(rows,day,midday,observed):
 from PIL import Image,ImageDraw
 from china_advertising_v2_png import font
 W=2400;H=6500;xs=[40,510,770,1060,1410,1660,2360];files=[]
 green='#196b44';navy='#173b50';ink='#111111';head=green if midday else navy
 def wrap(d,t,w,n=25):
  out=[];line=''
  for word in str(t).split():
   test=(line+' '+word).strip()
   if line and d.textlength(test,font=font(n))>w:out.append(line);line=word
   else:line=test
  if line:out.append(line)
  return out or ['']
 def val(v):return 'нет данных' if v is None else f'{v:,.2f}'.replace(',',' ').replace('.',',')
 def canvas():
  im=Image.new('RGB',(W,H),'#edf7f0' if midday else '#edf3f7');d=ImageDraw.Draw(im);d.rectangle((0,0,W,210),fill=head)
  d.text((40,25),'Китай · Поиск · Динамика новых тестов',font=font(45,True),fill='white')
  d.text((40,95),day+' · '+('дневной срез' if midday else 'утренний срез')+' · цель ДРР5%',font=font(28,True),fill='white')
  d.text((40,150),'Источник: '+observed,font=font(23),fill='white')
  labels=['Товар / РК','Расход с добавления, ¥','Клики / корзины','Рекл. заказы / сумма, ¥','ДРР','Оценка']
  for i,t in enumerate(labels):
   for j,line in enumerate(wrap(d,t,xs[i+1]-xs[i]-25)):d.text((xs[i],235+j*32),line,font=font(25,True),fill=head)
  return im,d
 def finish(im,y):
  foot='Только поисковая реклама. Данные с добавления: в первый день вычтен сохранённый срез до добавления; это не закрытая когорта. Корзина не равна заказу/выкупу. Возможна поздняя атрибуция. ДРР = расходы / сумма рекламных заказов до скидок WB; при нуле заказов ДРР не0%. Минимальная ставка не ограничивает расход. Автоматических изменений нет.'
  d=ImageDraw.Draw(im)
  for j,line in enumerate(wrap(d,foot,W-80,23)):d.text((40,y+25+j*30),line,font=font(23),fill='#536b79')
  buf=bio.BytesIO();im.crop((0,0,W,min(H,y+70+len(wrap(d,foot,W-80,23))*30))).save(buf,format='PNG');files.append(dict(family='drr',bytes=buf.getvalue(),actions=[]))
 im,d=canvas();y=350
 for row in rows:
  t=row['total'];r=ratio(t);pending=row['state']=='pending_activation'
  cells=[row['article']+' · '+str(row['campaign_id']),val(t['spend']) if t else 'Ожидает запуска' if pending else 'Нет данных',(val(t['clicks'])+' / '+val(t['baskets'])) if t else '—',(val(t['orders'])+' / '+val(t['amount'])) if t else '—',f'{r:.2f}%'.replace('.',',') if r is not None else 'Нет заказов' if t and t.get('orders')==0 else 'Нет оценки',row['decision']]
  ls=[wrap(d,t,xs[i+1]-xs[i]-25) for i,t in enumerate(cells)];h=max(map(len,ls))*33+30
  if y+h>5600:finish(im,y);im,d=canvas();y=350
  d.rounded_rectangle((20,y,W-20,y+h),15,fill='white')
  for i,lines in enumerate(ls):
   col=green if i==4 and r is not None and r<=5 else '#c42c42' if i==4 and r is not None and r>5 else ink
   for j,line in enumerate(lines):d.text((xs[i],y+12+j*33),line,font=font(25),fill=col)
  y+=h+10
 finish(im,y);return files
def append_trial_pages(io,day,files,midday=False):
 cfg=io.get(CONFIG)
 if not cfg or cfg.get('status')!='active' or not cfg.get('owner_authorized'):return files
 slot='midday' if midday else 'morning';snapshot='china_agent:search_trials_report:'+day+':'+slot+':v1'
 old=io.get(snapshot)
 if old:rows=old['rows'];observed=old['observed_at']
 else:
  source=io.get(('china_agent:advertising_midday_source:' if midday else 'china_agent:advertising_source:')+day+':v2')
  if not source or source.get('status')!='complete':raise ValueError('Search trial source missing; unknown is not zero')
  source=dict(source,report_day=day)
  history=io.get('china_agent:search_trials_days:v1') or {}
  rows,ledger=compute(source,cfg,history.get('days',{}));observed=source.get('completed_at',source['observed_at'])
  record=dict(rows=rows,observed_at=observed,day=day,slot=slot,execution_key=cfg['execution_key'])
  if not io.create(snapshot,record):record=io.get(snapshot);rows=record['rows'];observed=record['observed_at']
  daily=dict(days=ledger,observed_at=observed)
  if history:io.put('china_agent:search_trials_days:v1',daily)
  elif not io.create('china_agent:search_trials_days:v1',daily):raise ValueError('Concurrent trial history')
 extra=render(rows,day,midday,observed)
 # Preserve action objects and family identity; append read-only pages before budget family.
 files=[f for f in files if f['family']=='drr']+extra+[f for f in files if f['family']!='drr']
 for family in {f['family'] for f in files}:
  selected=[f for f in files if f['family']==family]
  for i,f in enumerate(selected,1):f.update(kind=family+':'+str(i).zfill(3),page=i,total=len(selected))
 return files
