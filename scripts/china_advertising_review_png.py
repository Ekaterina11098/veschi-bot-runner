"""Calculated per-SKU proposals; internal collection diagnostics are never substituted for decisions."""
import io
from PIL import Image,ImageDraw
from china_advertising_v2_png import font,money,pct,NAVY,BG,INK,GREEN,RED

def pages(bundle):
 if not bundle.get('economic_review_complete'):raise ValueError('Economic review not complete')
 W,H=2400,7000;xs=[40,560,1020,1600,2360];files=[]
 def wrap(d,s,width,size=28):
  lines=[]
  for para in str(s).split('\n'):
   row=''
   for word in para.split():
    if row and d.textlength(row+' '+word,font=font(size))>width:lines.append(row);row=word
    else:row=(row+' '+word).strip()
   lines.append(row)
  return lines
 def canvas():
  im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im);d.rectangle((0,0,W,225),fill=NAVY)
  d.text((40,24),'Китай · рассчитанные рекомендации по РК',font=font(46,True),fill='white')
  d.text((40,90),'Полные дни после последнего изменения · цель ДРР 5% · текущие минимумы WB',font=font(28,True),fill='white')
  d.text((40,137),bundle['source_observed_at'],font=font(25),fill='white')
  d.text((40,179),'Дополнительные предложения: '+str(sum(bool(r.get('action')) for c in bundle['campaigns'] for r in c['focus']))+' · исполнение — после согласования',font=font(25),fill='white')
  for i,label in enumerate(['РК · товар · период','Реклама за полные дни','Цена · собственная экономика','Рекомендация']):d.text((xs[i],245),label,font=font(28,True),fill=NAVY)
  return im,d
 def finish(im,d,y,actions):
  footer='Модель на созданный рекламный заказ, не прибыль на выкуп: свой выкуп 02–31.10, текущие цена/COGS, комиссия своя или допущение20%, налог5%, обработка10₽, курс ЦБ31.10, историческая логистика. Общие/обратные расходы не подтверждены полностью. Прямые и ассоциированные рекламные заказы не складывать как уникальные.'
  for line in wrap(d,footer,W-80,23):d.text((40,y+20),line,font=font(23),fill='#536b79');y+=30
  out=io.BytesIO();im.crop((0,0,W,min(H,y+55))).save(out,format='PNG');files.append(dict(family='drr',bytes=out.getvalue(),actions=actions))
 im,d=canvas();y=300;actions=[]
 for c in sorted(bundle['campaigns'],key=lambda c:not bool(c.get('attention'))):
  for r in sorted(c['focus'],key=lambda r:not bool(r.get('action'))):
   if r.get('pending_first_day') or r.get('already_excluded'):continue
   p=(r.get('comparison') or {}).get('after') or r['period']
   if p['spend']<=0:continue
   risk=p['orders']==0 or p['amount']<=0 or 100*p['spend']/p['amount']>5
   if not (r.get('action') or risk or r.get('pending_first_day')):continue
   e=r.get('economics') or {};days=(r.get('comparison') or {}).get('to_days') or bundle['days']
   first=days[0][8:10]+'.'+days[0][5:7];last=days[-1][8:10]+'.'+days[-1][5:7]
   period=first if first==last else first+'—'+last
   stats=f'Расход {money(p["spend"])} ¥\nКлики {int(p["clicks"])} · заказы {int(p["orders"])}\nСумма {money(p["amount"])} ¥\nДРР '+pct(p)
   if e.get('model_unavailable'):econ='Свободно МСК: '+str(e['stock_free'])+'\nОценка себестоимости при нулевом остатке недоступна.'
   elif e:
    sample=str(e.get('sample_size',0));q=money(e.get('buyout',0)*100)+'%'
    econ='Цена '+money(e['seller_price_cny'])+' ¥ · COGS '+money(e['own_cogs_rub'])+' ₽\nСвободно МСК '+str(e['stock_free'])+'\nВыкуп '+q+' · завершено '+sample+'\nДо рекламы / заказ '+money(e['expected_margin_before_ads_cny'])+' ¥'
    if e.get('buyout_fallback'):econ+='\nВыкуп50% — допущение без своей выборки'
    if r.get('model_profit_for_attributed_orders_cny') is not None:econ+='\nМодель на прямых заказах '+money(r['model_profit_for_attributed_orders_cny'])+' ¥'
   else:econ='День изменения исключён.\nНовая оценка — после первого полного дня.'
   bidline=''
   if r.get('current_bid_minor') is not None and r.get('minimum_bid_minor') is not None:bidline='Ставка '+money(r['current_bid_minor']/100)+' ¥ · минимум '+money(r['minimum_bid_minor']/100)+' ¥\n'
   cells=[str(c['id'])+' · '+c['zone']+'\n'+r['article']+'\n'+period,stats,econ,bidline+r['decision']]
   lines=[wrap(d,t,xs[i+1]-xs[i]-30) for i,t in enumerate(cells)];height=max(205,max(map(len,lines))*35+30)
   if y+height>6500:finish(im,d,y,actions);im,d=canvas();y=300;actions=[]
   d.rounded_rectangle((20,y,W-20,y+height),16,fill='#fff1cc' if r.get('action') else 'white')
   for i,ls in enumerate(lines):
    for j,line in enumerate(ls):d.text((xs[i],y+14+j*35),line,font=font(28,i==3),fill=INK)
   if r.get('action'):actions.append(r['action'])
   y+=height+12
 finish(im,d,y,actions)
 for i,f in enumerate(files,1):f.update(kind='drr:'+str(i).zfill(3),page=i,total=len(files))
 return files

