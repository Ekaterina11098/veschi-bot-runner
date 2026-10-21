"""Render the owner's retained two-table preview; no network or collection."""
import json,sys,os
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
W=1200; PAD=42
BG='#f2f5f8'; INK='#172b3a'; MUTED='#536878'; RED='#ba253a'; GREEN='#176848'; NAVY='#183c54'
fontdir=Path('C:/Windows/Fonts') if os.name=='nt' else Path('/usr/share/fonts/truetype/dejavu')
def font(size,bold=False):
 name=('arialbd.ttf' if bold else 'arial.ttf') if os.name=='nt' else ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')
 return ImageFont.truetype(str(fontdir/name),size)
def wrap(text,f,width):
 d=ImageDraw.Draw(Image.new('RGB',(1,1)));out=[];line=''
 for word in text.split():
  candidate=(line+' '+word).strip()
  if line and d.textlength(candidate,font=f)>width:out.append(line);line=word
  else:line=candidate
 if line:out.append(line)
 return out
def pct(v):return f'{v:.2f}'.replace('.',',')+'%'
def rub(v):return f'{v:,.0f}'.replace(',',' ')+' ₽'
def _render_page(bundle,outdir):
 from datetime import date
 period=date.fromisoformat(bundle['period']).strftime('%d.%m.%Y')
 observed=date.fromisoformat(bundle['observed_day']).strftime('%d.%m.%Y')
 outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
 def canvas(title,subtitle):
  im=Image.new('RGB',(W,max(3500,1200+len(bundle['campaigns'])*420)),BG);d=ImageDraw.Draw(im)
  d.rectangle((0,0,W,185),fill=NAVY)
  d.text((PAD,28),title,font=font(52,True),fill='white')
  d.text((PAD,105),subtitle,font=font(32),fill='#dbe8ee')
  return im,d,215
 def footer(im,d,y,text,path):
  y+=24
  for line in wrap(text,font(29),W-PAD*2):
   d.text((PAD,y),line,font=font(29),fill=MUTED);y+=39
  im.crop((0,0,W,y+38)).save(outdir/path,'PNG',optimize=True)
 _render_weekly_drr(bundle,outdir)
 # Budgets: every balance retains its original observation timestamp.
 from datetime import datetime
 from zoneinfo import ZoneInfo
 im,d,y=canvas('Бюджеты рекламных кампаний','Отчёт на '+observed+' · время МСК')
 xs=[PAD,310,555,835]
 for x,t in zip(xs,['РК','Баланс','Наблюдение','Хватит*']):d.text((x,y),t,font=font(32,True),fill=MUTED)
 y+=58
 for c in bundle['campaigns']:
  b=c.get('budget') or {};dt=None
  try:dt=datetime.fromisoformat(b['observed_at'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow'))
  except (KeyError,TypeError,ValueError):pass
  cost=c['spend'];h=c.get('conditional_hours')
  if c.get('observed_campaign_status')==11:estimate='Приостановлена'
  elif not b.get('valid') or dt is None or b.get('balance') is None:estimate='Неизвестен'
  elif not b.get('today_observation'):estimate='Исторический баланс'
  elif not c.get('metrics_complete'):estimate='Расход неизвестен'
  elif cost==0:estimate='Нет расхода'
  elif cost==2:estimate='Малая база'
  elif not b.get('today_observation') or not b.get('valid') or h is None:estimate='Нет оценки'
  else:estimate=('≈ '+f'{h:.1f}'.replace('.',',')+' ч') if h<24 else ('≈ '+f'{h/24:.1f}'.replace('.',',')+' дн.')
  lines=wrap(estimate,font(30,True),W-xs[3]-PAD)
  rowh=max(100,28+len(lines)*42)
  d.rounded_rectangle((PAD-14,y,W-PAD+14,y+rowh-8),radius=12,fill='white')
  vals=[str(c['campaign_id']),rub(b['balance']) if b.get('balance') is not None and b.get('valid') else 'Неизвестен',dt.strftime('%d.%m %H:%M') if dt else 'Нет даты']
  for x,t in zip(xs[:3],vals):d.text((x,y+22),t,font=font(33,True) if x==PAD else font(32),fill=INK)
  for k,line in enumerate(lines):d.text((xs[3],y+20+k*42),line,font=font(30,True),fill=RED if h is not None and h<24 else INK)
  y+=rowh
 footer(im,d,y,'*Условная длительность: баланс на момент наблюдения / суточный расход '+period+'. Расход после наблюдения не вычтен; балансы не текущие на момент чтения. Это не гарантия срока. При малом расходе оценка неустойчива; для пауз срок не рассчитывается.','budgets.png')
 return [str(outdir/'drr.png'),str(outdir/'budgets.png')]


def _render_weekly_drr(bundle,outdir):
 """Approved phone-readable design: daily and seven-day spend in one column."""
 from datetime import date,timedelta
 period=date.fromisoformat(bundle['period']);day=period.strftime('%d.%m.%Y')
 start=bundle.get('weekly_period_from') or str(period-timedelta(days=6))
 end=bundle.get('weekly_period_to') or str(period)
 week=date.fromisoformat(start).strftime('%d.%m')+'–'+date.fromisoformat(end).strftime('%d.%m.%Y')
 rows=bundle['campaigns'];im=Image.new('RGB',(W,max(3500,1200+len(rows)*420)),BG);d=ImageDraw.Draw(im)
 d.rectangle((0,0,W,185),fill=NAVY)
 d.text((PAD,28),'ДРР и рекламные расходы',font=font(52,True),fill='white')
 d.text((PAD,105),'ДРР — за '+day+' · цель — до 5%',font=font(32),fill='#dbe8ee')
 y=215
 total=bundle.get('total_spend');label=bundle.get('total_spend_label','Расход всех РК')
 d.text((PAD,y),(label+': '+rub(total)) if total is not None else 'Расход за день неизвестен',font=font(35,True),fill=INK);y+=51
 wt=bundle.get('weekly_total_spend');prefix='За 7 полных дней' if bundle.get('weekly_total_complete') else 'Известный расход за 7 дней'
 d.text((PAD,y),prefix+' ('+week+'): '+(rub(wt) if wt is not None else 'нет данных'),font=font(33,True),fill=INK);y+=66
 xs=[PAD,260,500,700]
 for x,t in zip(xs,['РК','Расход','ДРР за день','Товары · результат']):d.text((x,y),t,font=font(29,True),fill=MUTED)
 y+=55
 for c in rows:
  spend=c.get('spend');ratio=c.get('drr');above=c.get('above5') or []
  notes=[a['article']+' — '+pct(a['drr']) for a in above]
  if above and c.get('within5_count'):notes.append('Остальные с заказами — до 5%')
  if not notes:
   if not c.get('metrics_complete'):notes=['Нет полного среза за день']
   elif spend==0:notes=['За день не откручивалась']
   elif c.get('direct_orders')==0:notes=[]
   elif c.get('sku_basis')!='direct_only':notes=['Прямой ДРР товаров неизвестен']
   else:notes=['У товаров с заказами ДРР до 5%']
  if c.get('metrics_complete') and spend is not None and spend>0:
   n=c.get('no_order_count');amount=c.get('no_order_spend')
   if n is None or amount is None:notes.append('Без заказов: разбивка неизвестна')
   else:notes.append('Без заказов: '+str(n)+' '+('товар' if n%10==1 and n%100!=11 else 'товара' if n%10 in (2,3,4) and n%100 not in (12,13,14) else 'товаров')+' · '+rub(amount))
  if c.get('observed_campaign_status')==11:notes.append('РК приостановлена')
  lines=[]
  for note in notes:lines.extend(wrap(note,font(29),W-xs[3]-PAD-12))
  h=max(124,32+len(lines)*43)
  d.rounded_rectangle((PAD-14,y,W-PAD+14,y+h-8),radius=12,fill='white')
  d.text((xs[0],y+22),str(c['campaign_id']),font=font(35,True),fill=INK)
  d.text((xs[1],y+17),'День: '+(rub(spend) if c.get('metrics_complete') and spend is not None else '?'),font=font(29,True),fill=INK)
  weekly=c.get('weekly_spend')
  d.text((xs[1],y+61),'7 дн.: '+(rub(weekly) if weekly is not None else '?'),font=font(28),fill=MUTED)
  label='Нет данных' if not c.get('metrics_complete') else pct(ratio) if ratio is not None else 'Нет расхода' if spend==0 else 'Без заказов'
  d.text((xs[2],y+23),label,font=font(28,True),fill=RED if ratio is not None and ratio>5 else INK)
  for k,line in enumerate(lines):d.text((xs[3],y+18+k*43),line,font=font(29),fill=RED if above and k<len(above) else INK)
  y+=h
 y+=25
 foot='ДРР РК — с подтверждённым посткликом один раз. По товарам — прямые заказы за день. «Без заказов» — товары с расходом, но без прямых заказов; поздние и связанные заказы могут изменить оценку. Суммы строк товаров могут немного отличаться от итога РК. Неделя: '+week+'.'
 for line in wrap(foot,font(28),W-PAD*2):d.text((PAD,y),line,font=font(28),fill=MUTED);y+=38
 im.crop((0,0,W,y+36)).save(Path(outdir)/'drr.png','PNG',optimize=True)

def render_daily_png(view,outdir):
 """Same approved design, dynamic dates, up to 12 campaigns per image."""
 import copy,math
 from datetime import datetime
 from zoneinfo import ZoneInfo
 rows=[]
 for raw in sorted(view['campaigns'],key=lambda x:x['campaign_id']):
  c=copy.deepcopy(raw);cost=c.get('spend');revenue=c.get('revenue');b=c.get('budget') or {}
  c['drr']=100*cost/revenue if c.get('metrics_complete') and isinstance(cost,(int,float)) and isinstance(revenue,(int,float)) and revenue>0 else None
  c['sku_basis']=c.get('sku_order_basis')
  c['observed_campaign_status']=c.get('status_id')
  c['conditional_hours']=24*b['balance']/cost if c.get('metrics_complete') and isinstance(cost,(int,float)) and cost>0 and b.get('today_observation') and b.get('valid') and isinstance(b.get('balance'),(int,float)) and c.get('status_id')!=11 else None
  rows.append(c)
 if not rows:raise ValueError('No approved campaign scope')
 root=Path(outdir);artifacts={'drr':[],'budgets':[]}
 for i in range(0,len(rows),12):
  known=[c['spend'] for c in rows if c.get('metrics_complete') and isinstance(c.get('spend'),(int,float))]
  label='Расход всех РК' if len(known)==len(rows) else 'Известный расход (данные неполные)'
  paths=_render_page(dict(period=view['period'],observed_day=view['observed_day'],campaigns=rows[i:i+12],total_spend=sum(known) if known else None,total_spend_label=label,weekly_period_from=view.get('weekly_period_from'),weekly_period_to=view.get('weekly_period_to'),weekly_total_spend=sum(c['weekly_spend'] for c in rows if c.get('weekly_spend') is not None) if any(c.get('weekly_spend') is not None for c in rows) else None,weekly_total_complete=all(c.get('weekly_spend') is not None for c in rows)),root/str(i//12+1))
  for kind,path in zip(('drr','budgets'),paths):artifacts[kind].append(dict(kind=kind,path=path))
 return artifacts['drr']+artifacts['budgets']
if __name__=='__main__':print(json.dumps(render_daily_png(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')),sys.argv[2])))




