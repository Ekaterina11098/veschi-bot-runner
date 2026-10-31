"""Owner conditional cash estimate after verified eight actions. No transport."""
import io
from PIL import Image,ImageDraw
from china_advertising_v2_png import font,money,pct,color,NAVY,BG,INK,RED
def wrap(d,s,width,n=27,b=False):
 out=[]
 for part in str(s).split('\n'):
  line=''
  for word in part.split():
   test=(line+' '+word).strip()
   if line and d.textlength(test,font=font(n,b))>width:out.append(line);line=word
   else:line=test
  out.append(line)
 return out
def render(bundle):
 p=bundle['budget_after_eight']
 if p.get('all_eight_verified')is not True:raise ValueError('Post-action readback missing')
 rows=[r for r in p['rows']if r['gap']>0 or r['risk']]
 W=2400;im=Image.new('RGB',(W,4800),BG);d=ImageDraw.Draw(im)
 d.rectangle((0,0,W,225),fill=NAVY)
 d.text((40,25),'Китай · бюджеты после 8 выполненных действий',font=font(43,True),fill='white')
 d.text((40,92),'Остатки: '+p['observed_msk']+' · клики и факт расходов: 28–30.10 · все суммы CNY',font=font(27),fill='white')
 d.text((40,143),'К исполнению: 2 пополнения · 2 дополнительных резерва требуют решения · 8 действий подтверждены WB',font=font(27,True),fill='white')
 d.text((40,184),'Расчёт будущего расхода условный: прежнее число кликов, текущие ставки и состав.',font=font(24),fill='#dce9f0')
 xs=[40,790,1500,2350];y=250;actions=[]
 for r in rows:
  original=next(c for c in bundle['campaigns']if c['id']==r['cid'])
  left=['РК '+str(r['cid'])+' · '+r['name'],'Остаток: '+money(r['balance'])+' ¥','Условный резерв 3 дня: '+money(r['scenario3'])+' ¥','Нехватка: '+money(r['gap'])+' ¥']
  mid=['Факт: расход день '+money(r['actual1'])+' ¥','Факт: расход 3 дня '+money(r['actual3'])+' ¥','ДРР 3 дня: '+pct(original['period']),'ДРР день: '+pct(original['last'])]
  advice=[r['decision']]+([r['blocker']]if r['blocker']else[])+([r['risk']]if r['risk']else[])
  ls=[sum((wrap(d,t,xs[i+1]-xs[i]-35,29 if j==0 else 26,j==0)for j,t in enumerate(col)),[])for i,col in enumerate([left,mid,advice])]
  h=max(265,max(len(x)for x in ls)*37+48)
  d.rounded_rectangle((20,y,W-20,y+h),16,fill='#fff1cc'if r['action']else'white')
  for i,lines in enumerate(ls):
   for j,line in enumerate(lines):d.text((xs[i],y+18+j*37),line,font=font(29 if j==0 else 26,j==0),fill=(color(original['period']) if i==1 and line.startswith('ДРР 3 дня:') else color(original['last']) if i==1 and line.startswith('ДРР день:') else NAVY if j==0 else INK))
  y+=h+16
  if r['action']:actions.append(r['action'])
 footer=[
 'Остальные РК: по среднему сценарию пополнение не требуется. Для «Сумки2» отдельно показан риск ускорения. Резервы250/100CNY не входят в команду исполнения.',
 'Сценарий3дня = клики28–30.10 только оставшихся вРКSKU × их текущаяCPC. Это денежный резерв при прежнем числе кликов,не прогноз продаж или ДРР. Трафик может перераспределиться.',
 'Фактические расходы и ДРР выше сохранены целиком,включая прежний состав. Исторический расход исключённых не удалён. ДРР после8изменений ещё не измерена.',
 'Сумма пополнения = сценарный резерв − остаток; округление вверх до50CNY,минимумWB100CNY. Потребность в деньгах и разрешение продолжать рискованный тест — разные решения.',
 'Ответ «Делай всё» на этот PNG относится только к двум выделенным пополнениям. Цены,ставки,состав,паузы и остатки этой командой не меняются.'
 ]
 for s in footer:
  for line in wrap(d,s,W-80,24):d.text((40,y+8),line,font=font(24),fill='#536b79');y+=32
 raw=io.BytesIO();im.crop((0,0,W,y+35)).save(raw,format='PNG')
 if len(actions)!=2:raise ValueError('Expected exactly two ready topups')
 return [dict(kind='budgets:001',family='budgets',page=1,total=1,bytes=raw.getvalue(),actions=actions)]
