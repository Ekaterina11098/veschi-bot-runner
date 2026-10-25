"""Paginated owner-approved campaign headings, SKU details and separate budgets."""
import io,math
from PIL import Image,ImageDraw,ImageFont
from china_advertising_v2 import ratio
NAVY='#193d54';BG='#edf3f7';INK='#234154';MUTED='#647b8c';RED='#b63345';GREEN='#26725a'
def font(n,b=False):
 for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf','C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf')]:
  try:return ImageFont.truetype(p,n)
  except OSError:pass
 return ImageFont.load_default(size=n)
def money(x):return 'Нет данных' if x is None else f'{x:,.2f}'.replace(',',' ').replace('.',',')
def pct(x):return 'Нет заказов' if x is None else money(x)+'%'
def render(bundle):
 files=[];days=bundle['days'];shortdays=[d[8:10]+'.'+d[5:7] for d in days]
 def canvas(title,subtitle):
  im=Image.new('RGB',(2800,5000),BG);d=ImageDraw.Draw(im)
  def text(s,x,y,w,n=25,col=INK,b=False):
   line=''
   for word in str(s).split():
    z=(line+' '+word).strip()
    if line and d.textlength(z,font=font(n,b))>w:d.text((x,y),line,font=font(n,b),fill=col);y+=n+7;line=word
    else:line=z
   if line:d.text((x,y),line,font=font(n,b),fill=col);y+=n+7
   return y
  d.rectangle((0,0,2800,128),fill=NAVY);text(title,30,19,2720,37,'white',True);text(subtitle,30,80,2720,24,'white');return im,d,text
 def finish(im,y,kind,actions):
  stream=io.BytesIO();im.crop((0,0,2800,y+25)).save(stream,format='PNG');files.append(dict(family=kind,bytes=stream.getvalue(),actions=actions))
 quiet=[]
 for c in bundle['campaigns']:
  if not c['focus']:quiet.append(c);continue
  for start in range(0,len(c['focus']),6):
   im,d,t=canvas('Китай · рекомендации и выполненные действия',bundle.get('period_label',bundle['day']+' · полные '+days[0]+' — '+days[-1]+' · цель ДРР 5%'));y=150
   d.rectangle((15,y,2785,y+175),fill=NAVY)
   for x,label in [(30,'Кампания WB'),(850,'Расход, ¥'),(1510,'ДРР за '+shortdays[-1]),(2180,'ДРР за 3 дня')]:t(label,x,y+12,750,26,'#d8e5ec',True)
   t(str(c['id'])+' · '+c['zone'],30,y+61,780,31,'white',True);t(c['name'],30,y+108,780,25,'white')
   t('День: '+money(c['last']['spend'] if c['last'] else None),850,y+61,620,29,'white',True);t('3 дня: '+money(c['period']['spend'] if c['period'] else None),850,y+108,620,26,'white')
   t(pct(ratio(c['last'])),1510,y+65,620,32,'white',True);t(pct(c['drr']),2180,y+65,580,32,'white',True);y+=196
   xs=[30,385,625,785,945,1105,1360,1880];ws=[335,220,150,150,150,235,490,880]
   headers=['Артикул','Расход, ¥',*shortdays,'ДРР 3 дня','Уже сделано · МСК','Рекомендация / подтверждение']
   for x,w,h in zip(xs,ws,headers):t(h,x,y,w,24,b=True)
   y+=58;actions=[]
   for i,r in enumerate(c['focus'][start:start+6]):
    top=y;values=[r['article'],'День: '+money(r['daily'][-1]['spend'])+'; 3 дня: '+money(r['period']['spend']),*[pct(ratio(z)) for z in r['daily']],pct(r['period_drr'])+'; '+str(int(r['period']['orders']))+' зак.; сумма '+money(r['period']['amount'])+' ¥',r['done'],r['decision']+' '+r.get('reason','')]
    # Measure on a scratch image first so long recommendations never clip.
    heights=[]
    for j,(v,x,w) in enumerate(zip(values,xs,ws)):heights.append(t(v,x,4000,w,24 if j!=7 else 25))
    h=max(150,max(heights)-4000+26);d.rectangle((15,top,2785,top+h-7),fill='white' if i%2==0 else '#e1ebf3')
    for j,(v,x,w) in enumerate(zip(values,xs,ws)):t(v,x,top+12,w,24 if j!=7 else 25,RED if j==7 and r['action'] else GREEN if j==6 and r['done']!='Нет подтверждённых изменений' else INK,j in [0,7])
    y+=h
    if r['action']:actions.append(r['action'])
   for note in ['ДРР периода = все расходы / сумма рекламных заказов до скидок WB; это не среднее процентов. Дни без заказов входят в расходы. Рекламная атрибуция не равна всем заказам WB, выкупам или прибыли.', 'Первый полный день после изменения обязателен для оценки теста. День изменения исключён из сравнения до/после. Учитываем темп изменения ДРР и трафика; один скачок не означает устойчивую неэффективность.', ('Просмотр текущего неполного дня; этот PNG не исполняет изменения. ' if bundle.get('view_only') else '«Сделай всё» — только новые действия этого PNG. Уже выполненное не повторяется. ')+ 'Источник WB: '+bundle['source_observed_at']]:y=t(note,30,y+10,2740,23,MUTED)+3
   finish(im,y,'drr',actions)
 # Keep aggregate data for every campaign, even where healthy SKU rows are hidden.
 for start in range(0,len(quiet),6):
  im,d,t=canvas('Китай · общие данные РК без новых действий',bundle.get('period_label',bundle['day']+' · '+days[0]+' — '+days[-1]));y=150
  for c in quiet[start:start+6]:
   d.rectangle((15,y,2785,y+175),fill=NAVY)
   for x,h in [(30,'Кампания WB'),(850,'Расход, ¥'),(1510,'ДРР за день'),(2180,'ДРР за 3 дня')]:t(h,x,y+12,750,25,'#d8e5ec',True)
   t(str(c['id'])+' · '+c['zone'],30,y+58,780,29,'white',True);t(c['name'],30,y+108,780,24,'white')
   t('День: '+money(c['last']['spend'] if c['last'] else None),850,y+58,620,27,'white');t('3 дня: '+money(c['period']['spend'] if c['period'] else None),850,y+108,620,25,'white')
   t(pct(ratio(c['last'])),1510,y+65,620,31,'white',True);t(pct(c['drr']),2180,y+65,580,31,'white',True);y+=185
   note='Первый полный день нового состава ещё не оценён.' if c['new_composition'] else 'Нет новых действий по SKU.'
   if c['missing_stats']:note='Нет полной статистики WB за период; отсутствие данных не означает нулевой расход.'
   y=t(note,30,y,2720,24,MUTED)+15
  y=t('Товары без необходимого действия скрыты; их показатели входят в общие данные РК. Этот PNG не содержит действий для исполнения.',30,y+10,2740,24,MUTED)
  finish(im,y,'drr',[])
 for start in range(0,len(bundle['campaigns']),5):
  im,d,t=canvas('Китай · бюджеты и действия',bundle.get('budget_label',bundle['day']+' · расходы: полные '+days[0]+' — '+days[-1]+' · остатки: свежий срез WB'));y=152
  xs=[30,550,800,1150,1500,1850,2270];ws=[500,230,330,330,330,400,490]
  for x,w,h in zip(xs,ws,['Кампания WB / зона','Остаток, ¥','Расход день / 3 дня','ДРР день / 3 дня','На 3 дня / хватит','Уже сделано','Нужно подтвердить']):t(h,x,y,w,25,b=True)
  y+=88;actions=[]
  for i,c in enumerate(bundle['campaigns'][start:start+5]):
   values=[str(c['id'])+' · '+c['name']+' · '+c['zone'],money(c['balance']),'День: '+money(c['last']['spend'] if c['last'] else None)+'; 3 дня: '+money(c['period']['spend'] if c['period'] else None),pct(ratio(c['last']))+' / '+pct(c['drr']),'Нужен полный день нового состава' if c['forecast'] is None else money(c['forecast'])+' ¥; ≈'+money(c['coverage'])+' дн.',c.get('funding_done','Нет новых подтверждённых пополнений'),c['budget_recommendation']]
   hs=[t(v,x,4000,w,24) for v,x,w in zip(values,xs,ws)];h=max(140,max(hs)-4000+26);d.rectangle((15,y,2785,y+h-7),fill='white' if i%2==0 else '#e1ebf3')
   for j,(v,x,w) in enumerate(zip(values,xs,ws)):t(v,x,y+12,w,24,RED if j==6 and c['budget_action'] else INK,j in [0,6])
   y+=h
   if c['budget_action']:actions.append(c['budget_action'])
  for note in ['Потребность на 3 дня рассчитана по расходу текущего состава за полные дни; фактический срок может отличаться. Для нового состава без полного дня прогноз не подменён нулём. Поиск и рекомендации учитываются отдельно.', 'Пополнение предлагается только для целесообразных РК с результатом теста; неэффективным — конкретная пауза/правки SKU. ДРР и общая прибыль — разные показатели. Пополнение само по себе не гарантирует ДРР 5%.', 'Ответ «Сделай всё» — только новые пополнения/паузы этого PNG. Выполненные пополнения и условные действия не повторяются. Автопополнение не включаем. Время среза: '+bundle['source_observed_at']]:y=t(note,30,y+10,2740,23,MUTED)+3
  finish(im,y,'budgets',actions)
 for family in ['drr','budgets']:
  part=[f for f in files if f['family']==family]
  for i,f in enumerate(part,1):f['kind']=family+':'+str(i).zfill(3);f['page']=i;f['total']=len(part)
 return files

