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
def render(bundle,outdir):
 outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
 def canvas(title,subtitle):
  im=Image.new('RGB',(W,3500),BG);d=ImageDraw.Draw(im)
  d.rectangle((0,0,W,185),fill=NAVY)
  d.text((PAD,28),title,font=font(52,True),fill='white')
  d.text((PAD,105),subtitle,font=font(32),fill='#dbe8ee')
  return im,d,215
 def footer(im,d,y,text,path):
  y+=24
  for line in wrap(text,font(29),W-PAD*2):
   d.text((PAD,y),line,font=font(29),fill=MUTED);y+=39
  im.crop((0,0,W,y+38)).save(outdir/path,'PNG',optimize=True)
 # DRR: campaign totals already include associated orders once; never add them.
 im,d,y=canvas('ДРР по рекламным кампаниям','18 октября 2026 · цель — до 5%')
 xs=[PAD,310,540];headers=['РК','ДРР РК','Выше 5% по товарам']
 for x,t in zip(xs,headers):d.text((x,y),t,font=font(32,True),fill=MUTED)
 y+=55
 for c in bundle['campaigns']:
  cid=c['campaign_id'];cost=c['spend'];v=c.get('drr');above=c.get('above5') or []
  label=pct(v) if v is not None else ('Нет расхода' if cost==0 else 'Без заказов')
  notes=[a['article']+' — '+pct(a['drr']) for a in above]
  if above and c.get('within5_count'):notes.append('Остальные с ДРР — до 5%')
  if not notes:
   if cost==0:notes=['Расхода и заказов нет']
   elif c.get('direct_orders')==0:notes=['Без прямых заказов · '+rub(cost)]
   else:notes=['Превышений нет']
  if c.get('observed_campaign_status')==11:notes.append('РК приостановлена')
  lines=[]
  for note in notes:lines+=wrap(note,font(30),W-xs[2]-PAD-15)
  h=max(94,30+len(lines)*43)
  d.rounded_rectangle((PAD-14,y,W-PAD+14,y+h-8),radius=12,fill='white')
  d.text((xs[0],y+20),str(cid),font=font(36,True),fill=INK)
  d.text((xs[1],y+23),label,font=font(31,True),fill=RED if v is not None and v>5 else INK)
  for k,line in enumerate(lines):d.text((xs[2],y+18+k*43),line,font=font(30),fill=RED if above and k<len(above) else INK)
  y+=h
 footer(im,d,y,'ДРР РК — с подтверждённым посткликом, учтённым один раз. По товарам — прямой ДРР: постклик не распределён. «Превышений нет» — только среди товаров с рассчитанным ДРР. Нет заказов или данных — не норма.', 'drr-18oct.png')
 # Budgets: every balance retains its original observation timestamp.
 from datetime import datetime
 from zoneinfo import ZoneInfo
 im,d,y=canvas('Бюджеты рекламных кампаний','Наблюдения 19 октября 2026 · время МСК')
 xs=[PAD,310,555,835]
 for x,t in zip(xs,['РК','Баланс','Наблюдение','Хватит*']):d.text((x,y),t,font=font(32,True),fill=MUTED)
 y+=58
 for c in bundle['campaigns']:
  b=c['budget'];dt=datetime.fromisoformat(b['observed_at'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow'))
  cost=c['spend'];h=c.get('conditional_hours_at_18Oct_spend')
  if c.get('observed_campaign_status')==11:estimate='Приостановлена'
  elif cost==0:estimate='Нет расхода'
  elif cost==2:estimate='Малая база'
  elif not b.get('today_observation') or not b.get('valid') or h is None:estimate='Нет оценки'
  else:estimate=('≈ '+f'{h:.1f}'.replace('.',',')+' ч') if h<24 else ('≈ '+f'{h/24:.1f}'.replace('.',',')+' дн.')
  lines=wrap(estimate,font(30,True),W-xs[3]-PAD)
  rowh=max(100,28+len(lines)*42)
  d.rounded_rectangle((PAD-14,y,W-PAD+14,y+rowh-8),radius=12,fill='white')
  vals=[str(c['campaign_id']),rub(b['balance']),dt.strftime('%d.%m %H:%M')]
  for x,t in zip(xs[:3],vals):d.text((x,y+22),t,font=font(33,True) if x==PAD else font(32),fill=INK)
  for k,line in enumerate(lines):d.text((xs[3],y+20+k*42),line,font=font(30,True),fill=RED if h is not None and h<24 else INK)
  y+=rowh
 footer(im,d,y,'*Условная длительность: баланс на момент наблюдения / суточный расход 18 октября. Расход после наблюдения не вычтен; балансы не текущие на момент чтения. Это не гарантия срока. При малом расходе оценка неустойчива; для пауз срок не рассчитывается.','budgets-19oct.png')
 return [str(outdir/'drr-18oct.png'),str(outdir/'budgets-19oct.png')]
if __name__=='__main__':print(json.dumps(render(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')),sys.argv[2])))

