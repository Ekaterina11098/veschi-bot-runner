"""Owner-approved compact campaign cards; separate actionable budgets, durable families."""
import io
from PIL import Image,ImageDraw,ImageFont
from china_advertising_v2 import ratio
NAVY='#193e52';BG='#edf3f7';INK='#213f51';MUTED='#627582';RED='#b4394c'
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
def render(bundle):
 files=[];W=1900;days=bundle['days'];last=days[-1][8:10]+'.'+days[-1][5:7];period=days[0][8:10]+'.'+days[0][5:7]+'–'+last
 def canvas(title):
  im=Image.new('RGB',(W,6500),BG);d=ImageDraw.Draw(im)
  def text(s,x,y,w,n=27,col=INK,b=False,draw=True):
   line=''
   for word in str(s).split():
    v=(line+' '+word).strip()
    if line and d.textlength(v,font=font(n,b))>w:
     if draw:d.text((x,y),line,font=font(n,b),fill=col)
     y+=n+9;line=word
    else:line=v
   if line:
    if draw:d.text((x,y),line,font=font(n,b),fill=col)
    y+=n+9
   return y
  d.rectangle((0,0,W,145),fill=NAVY)
  text(title,32,20,W-64,42,'white',True)
  text(bundle['day']+' · день '+last+' · 3 полных дня '+period+' · остатки: '+bundle['source_observed_at'],32,88,W-64,25,'#d8e4ec')
  return im,d,text
 def finish(im,y,family,actions):
  b=io.BytesIO();im.crop((0,0,W,min(y+24,6500))).save(b,format='PNG')
  files.append(dict(family=family,bytes=b.getvalue(),actions=actions))
 # A campaign can continue across pages; each action stays on exactly its own page.
 im,d,t=canvas('Китай · реклама и остатки по РК');y=170;actions=[]
 for c in bundle['campaigns']:
  entries=[(v,False,None) for v in c.get('notes',['Изменений не нужно.'])]
  for r in c.get('attention',[r for r in c.get('focus',[]) if r.get('action')]):
   p=r['period'];line=r['article']+' · расход '+money(p['spend'])+' ¥; '+str(int(p['orders']))+' зак. · '+r['decision']+' '+r.get('reason','')
   entries.append((line,True,r['action']))
  if c.get('budget_action') and c['budget_action']['kind']=='topup_campaign':
   entries.append((c['budget_recommendation']+' Подтверждение — в бюджетном PNG.',True,None))
  # Split exceptionally large campaign details into readable sections.
  for start in range(0,max(1,len(entries)),8):
   part=entries[start:start+8]
   hh=126+sum(t(v,44,0,W-88,27,draw=False) for v,_,_ in part)+28
   if y+hh>5700:
    y=t('ДРР = расходы / сумма рекламных заказов до скидок WB. Цель 5%. История исключённых SKU сохранена.',32,y+12,W-64,24,MUTED)
    finish(im,y,'drr',actions);im,d,t=canvas('Китай · реклама и остатки по РК');y=170;actions=[]
   top=y
   d.rounded_rectangle((22,top,W-22,top+hh-10),radius=14,fill='white')
   d.rounded_rectangle((22,top,W-22,top+110),radius=14,fill=NAVY);d.rectangle((22,top+85,W-22,top+110),fill=NAVY)
   name=c['name'];name=name if len(name)<35 else name[:34]+'…'
   t('РК '+str(c['id'])+' · '+name,42,top+12,790,27,'white',True)
   t('Остаток: '+money(c['balance'])+' ¥ · '+c['zone'],42,top+65,790,25,'#d8e4ec')
   for x,label,value in [(850,'Расход, ¥',None),(1230,'ДРР '+last,c['last']),(1550,'ДРР '+period,c['period'])]:
    t(label,x,top+12,320,23,'#d8e4ec',True)
    if value is not None:
     v=pct(value);t(v,x,top+52,320,29,'#ffb7bf' if ratio(value) is not None and ratio(value)>5 else 'white',True)
    elif x==850:
     t('День: '+money(c['last']['spend'] if c['last'] else None),x,top+46,340,26,'white',True)
     t('3 дня: '+money(c['period']['spend'] if c['period'] else None),x,top+80,340,23,'#d8e4ec')
    else:t('Нет данных',x,top+52,320,26,'white')
   y=top+126
   for v,b,a in part:
    y=t(v,44,y,W-88,27,INK,b)
    if a:actions.append(a)
   y=max(y+28,top+hh)
 y=t('ДРР = расходы / сумма рекламных заказов до скидок WB; не среднее процентов. Цель 5%. Прежний расход исключённых SKU сохранён. Новые РК — с запуска внутри периода. Атрибуция не равна выкупам или прибыли.',32,y+12,W-64,24,MUTED)
 finish(im,y,'drr',actions)
 # Do not repeat every healthy campaign in a second budget table.
 selected=[c for c in bundle['campaigns'] if c.get('budget_action')]
 im,d,t=canvas('Китай · пополнения для подтверждения');y=180;actions=[]
 if not selected:y=t('Новых подтверждённых рекомендаций по пополнению нет. Автопополнение и паузы РК не включены.',36,y,W-72,30)
 for c in selected:
  y=t('РК '+str(c['id'])+' · остаток '+money(c['balance'])+' ¥ · ДРР '+pct(c['period']),36,y,W-72,30,INK,True)
  y=t(c['budget_recommendation'],36,y,W-72,28)+25;actions.append(c['budget_action'])
 finish(im,y,'budgets',actions)
 for family in ['drr','budgets']:
  parts=[x for x in files if x['family']==family]
  for i,x in enumerate(parts,1):x.update(kind=family+':'+str(i).zfill(3),page=i,total=len(parts))
 return files
