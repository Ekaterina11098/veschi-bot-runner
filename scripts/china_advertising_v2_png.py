"""Approved three-day-first table, page-bound new actions, durable delivery families."""
import io
from PIL import Image,ImageDraw,ImageFont
from china_advertising_v2 import ratio
NAVY='#193e52';BG='#edf3f7';INK='#111111';GREEN='#168447';RED='#bd303e'
def font(n,b=False):
 for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf','C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf')]:
  try:return ImageFont.truetype(p,n)
  except OSError:pass
 return ImageFont.load_default(size=n)
def money(x):return 'Нет данных' if x is None else f'{x:,.2f}'.replace(',',' ').replace('.',',')
def pct(v):
 if v is None:return 'Нет данных'
 if v['amount']>0:return money(ratio(v))+'%'
 return 'Нет заказов' if v['spend']>0 else 'Нет расхода'
def color(v):
 r=ratio(v)
 return INK if r is None else GREEN if r<=5 else RED
def summary(c):
 day=c.get('last');p=c.get('period')
 if c.get('never_started'):return '3 товара; кампания не запускалась.' if c.get('member_count')==3 else 'Кампания не запускалась.'
 if p is None:return 'Статистика отсутствует; числовой результат не подтверждён.'
 return ('День: '+str(int(day['orders']))+' рекламных заказов; сумма '+money(day['amount'])+' ¥.\n' if day else 'День: нет данных.\n')+'3 дня: '+str(int(p['orders']))+' рекламных заказов; сумма '+money(p['amount'])+' ¥; '+str(int(p['clicks']))+' кликов.'
def recommendations(c):
 if c.get('never_started'):return ['Черновик, ещё не запускалась. Бюджет '+money(c.get('balance'))+' ¥; ДРР не применима.']
 if c.get('missing_stats'):return ['Статистика отсутствует; рекомендации по эффективности не подтверждены.']
 rows=c.get('attention',[])
 if rows:return [r['article']+': '+r['decision']+' '+r.get('reason','') for r in rows]
 notes=[n for n in c.get('notes',[]) if not n.startswith('Уже исключены:')]
 if c.get('period') and c['period']['spend']>0 and c['period']['amount']==0:
  return ['Расход без рекламных заказов: '+money(c['period']['spend'])+' ¥; '+str(int(c['period']['clicks']))+' кликов. '+('Новый тест; полного дня после запуска ещё нет.' if c.get('new_composition') else 'Нужен контроль безрезультатного расхода; ДРР не вычисляется.')]
 return notes or ['Изменений не нужно.']
def render(bundle):
 W=2400;H=6500;xs=[44,355,650,870,1090,1700,2356];files=[]
 def canvas(title):
  im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
  d.rectangle((0,0,W,205),fill=NAVY)
  d.text((44,28),title,font=font(48,True),fill='white')
  d.text((44,100),'День: '+bundle['days'][-1]+' · 3 дня: '+bundle['days'][0]+'—'+bundle['days'][-1]+' · цель ДРР 5%',font=font(29,True),fill='white')
  d.text((44,150),'Срез: '+str(bundle['source_observed_at']),font=font(24),fill='#dce9f0')
  return im,d
 def wrap(d,s,w,n=27):
  out=[]
  for p in str(s).split('\n'):
   line=''
   for word in p.split():
    test=(line+' '+word).strip()
    if line and d.textlength(test,font=font(n))>w:out.append(line);line=word
    else:line=test
   out.append(line)
  return out
 def finish(im,y,family,actions):
  b=io.BytesIO();im.crop((0,0,W,min(H,y+30))).save(b,format='PNG')
  files.append(dict(family=family,bytes=b.getvalue(),actions=actions))
 def table():
  im,d=canvas('Китай · ДРР и рекламные расходы')
  d.text((44,216),'Зелёный: ДРР ≤ 5% · чёрный: нейтрально / нет оценки · красный: ДРР > 5%',font=font(24),fill=INK)
  for i,label in enumerate(['Кампания WB','Расход, CNY','ДРР 3 дня','ДРР день','Товары: данные за 3 дня','Рекомендации по 3 дням']):
   for j,line in enumerate(wrap(d,label,xs[i+1]-xs[i]-28,29)):d.text((xs[i],267+j*35),line,font=font(29,True),fill=NAVY)
  return im,d
 im,d=table();y=365;actions=[]
 for c in bundle['campaigns']:
  p=c.get('period');day=c.get('last');draft=c.get('never_started')
  cells=[str(c['id'])+'\n'+c['name'],'День: '+(money(day['spend'])+' ¥' if day else 'не запускалась' if draft else 'нет данных')+'\n3 дня: '+(money(p['spend'])+' ¥' if p else 'не запускалась' if draft else 'нет данных'),'Не применима' if draft else pct(p),'Не применима' if draft else pct(day),summary(c),'\n'.join(recommendations(c))]
  ls=[wrap(d,s,xs[i+1]-xs[i]-34) for i,s in enumerate(cells)]
  h=max(140,max(map(len,ls))*35+36)
  if h>4800:raise ValueError('Campaign row too long; refuse clipped report')
  if y+h>5500:
   finish(im,y,'drr',actions);im,d=table();y=365;actions=[]
  d.rounded_rectangle((24,y,W-24,y+h),18,fill='white')
  for i,lines in enumerate(ls):
   col=color(p) if i==2 else color(day) if i==3 else INK
   for j,line in enumerate(lines):d.text((xs[i],y+18+j*35),line,font=font(27),fill=col)
  actions.extend(r['action'] for r in c.get('attention',[]) if r.get('action'))
  y+=h+12
 # Never sum daily percentages or double-count SKU/app totals.
 totals=[]
 for key in ['period','last']:
  known=[c for c in bundle['campaigns'] if c.get(key) is not None]
  missing=[c for c in bundle['campaigns'] if c.get(key) is None and not c.get('never_started')]
  totals.append(None if missing else dict(spend=sum(c[key]['spend'] for c in known),amount=sum(c[key]['amount'] for c in known)))
 p,day=totals
 d.rounded_rectangle((24,y+10,W-24,y+190),18,fill='white')
 d.text((44,y+30),'ИТОГО · кабинет Китай (token_3)',font=font(29,True),fill=NAVY)
 d.text((44,y+82),'Расход 3 дня: '+money(p['spend'] if p else None)+' ¥   |   Расход день: '+money(day['spend'] if day else None)+' ¥',font=font(29,True),fill=INK)
 for x,label,value in [(44,'Общая ДРР 3 дня: ',p),(1050,'Общая ДРР день: ',day)]:
  d.text((x,y+132),label,font=font(29,True),fill=INK)
  d.text((x+d.textlength(label,font=font(29,True)),y+132),pct(value),font=font(29,True),fill=color(value))
 footer='ДРР = сумма расходов / сумма рекламных заказов до скидок WB. Дни без заказов входят в расходы. Нет заказов — сумма заказов 0, ДРР не вычисляется. Исторический расход исключённых сохранён. Атрибуция не равна выкупам и прибыли. Новые тесты отмечены; период может включать прежний состав. Итог относится только к кабинету Китай.'
 for j,line in enumerate(wrap(d,footer,W-88,24)):d.text((44,y+218+j*31),line,font=font(24),fill='#536b79')
 finish(im,y+240+len(wrap(d,footer,W-88,24))*31,'drr',actions)
 # Keep the existing family/cursor and exact per-image approval binding.
 im,d=canvas('Китай · пополнения для подтверждения');y=240;actions=[]
 selected=[c for c in bundle['campaigns'] if (c.get('budget_action') or {}).get('kind')=='topup_campaign']
 for c in selected:
  for line in wrap(d,'РК '+str(c['id'])+' · '+c['budget_recommendation'],W-88):
   d.text((44,y),line,font=font(27),fill=INK);y+=36
  y+=24;actions.append(c['budget_action'])
 if not selected:d.text((44,y),'Новых рекомендаций по пополнению нет.',font=font(29),fill=INK);y+=50
 finish(im,y,'budgets',actions)
 for family in ['drr','budgets']:
  parts=[f for f in files if f['family']==family]
  for i,f in enumerate(parts,1):f.update(kind=family+':'+str(i).zfill(3),page=i,total=len(parts))
 return files

