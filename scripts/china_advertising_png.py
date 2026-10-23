import json,math
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image,ImageDraw,ImageFont

def campaign_notes(c,money,pct):
 """Positive-spend zero-direct-order products are distinct from calculable DRR."""
 notes=[r['article']+' · '+pct(r['drr']) for r in c['above5']]
 if c['is_new']:return ['Создана '+datetime.fromisoformat(c['created'][:10]).strftime('%d.%m.%Y')+' — вне отчётного периода']
 if c['spend']==0:return ['За день не откручивалась']
 if not notes:
  notes=['У товаров с заказами ДРР до 5%'] if c.get('sku_with_orders_count',0)>0 else ['Прямых заказов нет']
 count=len(c['no_orders'])
 word='товар' if count%10==1 and count%100!=11 else 'товара' if count%10 in (2,3,4) and count%100 not in (12,13,14) else 'товаров'
 notes.append('Без заказов: '+str(count)+' '+word+' · '+money(sum(r['spend'] for r in c['no_orders'])))
 return notes

def render(b,outdir):
 root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
 def fmt(day):return datetime.fromisoformat(day).strftime('%d.%m.%Y')
 W=1400;P=42;INK='#183448';MUTED='#536b7d';RED='#b42b3c';GREEN='#18705b';BG='#eef3f7';NAVY='#193d54'
 def font(n,bold=False):
  import os
  path=('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf')) if os.name=='nt' else ('/usr/share/fonts/truetype/dejavu/'+('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'))
  return ImageFont.truetype(path,n)
 measure=ImageDraw.Draw(Image.new('RGB',(1,1)))
 def wrap(t,f,width):
  out=[];line=''
  for word in t.split():
   nxt=(line+' '+word).strip()
   if line and measure.textlength(nxt,font=f)>width:out.append(line);line=word
   else:line=nxt
  if line:out.append(line)
  return out
 def number(v):return f'{v:,.0f}'.replace(',',' ')
 def money(v):return number(v)+' ¥'
 def pct(v):return f'{v:.2f}'.replace('.',',')+'%'
 def canvas(title,subtitle):
  im=Image.new('RGB',(W,12000),BG);d=ImageDraw.Draw(im);d.rectangle((0,0,W,190),fill=NAVY)
  d.text((P,30),title,font=font(49,True),fill='white');d.text((P,110),subtitle,font=font(30),fill='#dceaf2');return im,d,220
 def paragraph(d,y,text,size=27,color=MUTED):
  for line in wrap(text,font(size),W-2*P):d.text((P,y),line,font=font(size),fill=color);y+=size+11
  return y+10
 im,d,y=canvas('Китай · ДРР и рекламные расходы',fmt(b['period'])+' · 7 дней: '+fmt(b['week_from'])+'–'+fmt(b['week_to'])+' · ориентир ДРР 5%')
 y=paragraph(d,y,'Расход за день: '+money(b['total_day'])+'     За 7 дней: '+money(b['total_week']),36,INK)
 y=paragraph(d,y,'Суммы — по сводкам кампаний MPStats. ДРР пересчитан по этим суммам; значения округлены источником.',25)
 xs=[P,325,545,720,925]
 for x,t in zip(xs,['Кампания WB','Расход','ДРР за день','ДРР ср. 3 дн.','Товары: ДРР и расход']):d.text((x,y),t,font=font(24,True),fill=MUTED)
 y+=58
 for c in b['campaigns']:
  notes=[]
  for line in campaign_notes(c,money,pct):notes+=wrap(line,font(26),W-xs[4]-P-15)
  if not c['day_match']:notes+=wrap('Сводка: '+money(c['spend'])+'; дневной ряд: '+(money(c.get('day_row_spend')) if c.get('day_row_spend') is not None else 'нет данных'),font(25),W-xs[4]-P-15)
  warning=wrap('Без заказов: '+str(c.get('drr_3d_no_orders_days',0))+' дн. · '+money(c.get('drr_3d_no_orders_spend',0)),font(23),xs[4]-xs[3]-20) if c.get('drr_3d_no_orders_days',0) else []
  h=max(143,34+len(notes)*37,135+len(warning)*31)
  d.rounded_rectangle((P-14,y,W-P+14,y+h-9),radius=14,fill='white')
  d.text((xs[0],y+15),str(c['wb_id']),font=font(35,True),fill=INK)
  for k,line in enumerate(wrap(c['name'],font(25),xs[1]-xs[0]-18)):d.text((xs[0],y+61+k*31),line,font=font(25),fill=MUTED)
  d.text((xs[1],y+20),'День: '+money(c['spend']),font=font(26,True),fill=INK)
  d.text((xs[1],y+65),'7 дн.: '+money(c['weekly_spend']),font=font(27),fill=MUTED)
  label='Нет расхода' if c['spend']==0 else pct(c['drr']) if c['drr'] is not None else 'Без заказов'
  for k,line in enumerate(wrap(label,font(28,True),xs[3]-xs[2]-20)):d.text((xs[2],y+22+k*35),line,font=font(28,True),fill=RED if c['drr'] and c['drr']>5 else INK)
  mean=c.get('drr_mean_3d');count=c.get('drr_mean_3d_count',0)
  for k,line in enumerate(wrap(pct(mean) if mean is not None else 'Нет данных',font(27,True),xs[4]-xs[3]-20)):d.text((xs[3],y+22+k*35),line,font=font(27,True),fill=RED if mean is not None and mean>5 else INK)
  d.text((xs[3],y+88),str(count)+' из 3',font=font(24),fill=MUTED)
  for k,line in enumerate(warning):d.text((xs[3],y+125+k*31),line,font=font(23),fill=RED)
  for k,line in enumerate(notes):d.text((xs[4],y+18+k*37),line,font=font(26),fill=RED if c['above5'] else MUTED)
  y+=h
 y+=20
 y=paragraph(d,y,'ДРР ср. 3 дн. — среднее арифметическое имеющихся дневных ДРР за последние 3 дня отчётного периода. Дни без определённого ДРР исключены из делителя; 0% учитывается. Под значением указано число учтённых дней. Расходы дней без рекламных заказов показаны красным отдельно и не скрыты за средним.',25)
 y=paragraph(d,y,'ДРР = расход / сумма рекламных заказов. Постклик уже включён в итог РК и повторно не прибавлен. По товарам — прямые заказы. «Без заказов» — товары с расходом, но без прямых заказов; поздние и связанные заказы могут изменить оценку. Это рекламная атрибуция, не выкупы и не прибыль.',25)
 y=paragraph(d,y,'Расхождения исходных срезов показаны в строках. Товарные суммы могут отличаться от итогов РК из-за точности и версий источника; итог РК не заменён суммой товаров. Нули новых кампаний не означают эффективность.',25)
 im.crop((0,0,W,y+24)).save(root/'drr.png',optimize=True)
 im,d,y=canvas('Китай · бюджеты кампаний','Проверка '+fmt(b['observed_day'])+' · валюта CNY · время МСК')
 xs=[P,390,650,955]
 for x,t in zip(xs,['Кампания WB','Остаток','Проверено','Хватит примерно*']):d.text((x,y),t,font=font(29,True),fill=MUTED)
 y+=60
 for c in b['campaigns']:
  t=datetime.fromisoformat(c['balance_observed']).astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m %H:%M')
  hours=c['balance_hours']
  if c['balance'] is None:label='Нет данных бюджета'
  elif c['is_new']:label='Новая РК — нет базы'
  elif c['status']!=9:label='Нет оценки · код '+str(c['status'])
  elif not c['spend']:label='Нет расхода за день'
  else:label=('≈ '+f'{hours:.1f}'.replace('.',',')+' ч') if hours<24 else ('≈ '+f'{hours/24:.1f}'.replace('.',',')+' дн.')
  notes=wrap(label,font(29,True),W-xs[3]-P-15);h=max(133,35+len(notes)*37)
  d.rounded_rectangle((P-14,y,W-P+14,y+h-9),radius=14,fill='white')
  d.text((P,y+17),str(c['wb_id']),font=font(35,True),fill=INK)
  for k,line in enumerate(wrap(c['name'],font(25),xs[1]-P-20)):d.text((P,y+64+k*31),line,font=font(25),fill=MUTED)
  d.text((xs[1],y+23),(money(c['balance']) if c['balance'] is not None else 'Нет данных'),font=font(35,True),fill=INK)
  d.text((xs[2],y+26),t,font=font(28),fill=INK)
  for k,line in enumerate(notes):d.text((xs[3],y+22+k*37),line,font=font(29,True),fill=RED if hours is not None and hours<24 else INK)
  y+=h
 y+=22
 y=paragraph(d,y,'*Условная оценка: остаток при проверке / расход за '+fmt(b['period'])+' × 24 часа. Это не прогноз по сегодняшнему темпу и не гарантия срока. Расход после проверки не вычтен.',28)
 y=paragraph(d,y,'Для новых кампаний без полного дня расхода срок не рассчитывается. Нулевой бюджет и отсутствие расхода сами по себе не раскрывают причину статуса.',27)
 im.crop((0,0,W,y+25)).save(root/'budgets.png',optimize=True)
 
 return [root/'drr.png',root/'budgets.png']
