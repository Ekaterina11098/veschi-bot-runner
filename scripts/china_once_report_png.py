import io
from PIL import Image,ImageDraw
from china_advertising_v2_png import font,money

def render(data,names):
 rows=data['rows'];by={(r['nm_id'],r['day']):r for r in rows}
 def drr(r):
  a=r['advertising'];return 100*a['spend']/a['amount']if a and a['amount']>0 else None
 ids=sorted(names,key=lambda n:-(drr(by[n,'2026-11-01'])or-1));W=2400
 im=Image.new('RGB',(W,1850),'#edf3f7');d=ImageDraw.Draw(im);navy='#193f51';ink='#203b48'
 d.rectangle((0,0,W,205),fill=navy)
 d.text((40,25),'Китай · отчёт Павлу · расходы и ДРР',font=font(48,True),fill='white')
 d.text((40,95),'Рекламный срез: 01.11.2026 18:16 МСК · сортировка по ДРР 1 ноября ↓',font=font(31),fill='white')
 d.text((40,148),'31 октября — полный день; 1 ноября — неполный. Точного рекламного среза на 18:00 нет.',font=font(28),fill='white')
 xs=[35,660,1090,1350,1780,2365]
 d.text((50,245),'Артикул',font=font(32,True),fill=navy)
 d.text((690,226),'31 октября · полный день',font=font(32,True),fill=navy)
 d.text((1380,226),'1 ноября · до среза 18:16 МСК',font=font(32,True),fill=navy)
 for x,label in [(690,'Расход, CNY'),(1120,'ДРР'),(1380,'Расход, CNY'),(1810,'ДРР')]:d.text((x,282),label,font=font(30,True),fill=navy)
 y=340
 for nm in ids:
  d.rounded_rectangle((25,y,W-25,y+105),14,fill='white');d.text((50,y+33),names[nm],font=font(33,True),fill=ink)
  for day,x1,x2 in [('2026-10-31',690,1120),('2026-11-01',1380,1810)]:
   r=by[nm,day];rate=drr(r);d.text((x1,y+32),money(r['advertising']['spend'])+' ¥',font=font(34),fill=ink)
   d.text((x2,y+32),money(rate)+'%'if rate is not None else'Не определена',font=font(34,True),fill='#23834f'if rate is not None and rate<=5 else'#bf3548'if rate is not None else ink)
  y+=122
 total={day:dict(spend=sum(by[n,day]['advertising']['spend']for n in ids),amount=sum(by[n,day]['advertising']['amount']for n in ids))for day in ['2026-10-31','2026-11-01']}
 d.rounded_rectangle((25,y,W-25,y+90),14,fill='#dce8ee');d.text((50,y+25),'Итого по указанным SKU',font=font(31,True),fill=ink)
 for day,x1,x2 in [('2026-10-31',690,1120),('2026-11-01',1380,1810)]:
  t=total[day];d.text((x1,y+25),money(t['spend'])+' ¥',font=font(33,True),fill=ink);d.text((x2,y+25),money(100*t['spend']/t['amount'])+'%',font=font(33,True),fill='#bf3548')
 y+=125
 d.text((40,y),'Заказы · разные источники, не складывать',font=font(34,True),fill=navy);y+=65
 for x,label in [(50,'Артикул'),(690,'WB-воронка 31.10 / 01.11'),(1530,'FBS: 31.10 полный / 01.11 до 18:00')]:d.text((x,y),label,font=font(28,True),fill=navy)
 y+=55
 for nm in ids:
  d.rounded_rectangle((25,y,W-25,y+70),10,fill='white');d.text((50,y+18),names[nm],font=font(29),fill=ink)
  d.text((690,y+18),' / '.join(str(by[nm,day]['general_funnel']['orders'])for day in ['2026-10-31','2026-11-01']),font=font(30,True),fill=ink)
  d.text((1530,y+18),' / '.join(str(by[nm,day]['fbs_created'])for day in ['2026-10-31','2026-11-01']),font=font(30,True),fill=ink);y+=82
 y+=20
 footer=['ДРР = сумма рекламных расходов / атрибутированную сумму заказов. Без суммы заказов ДРР не определена.',
 'WB-воронка — все источники, задержка до 2 часов. FBS — созданные сборочные задания, не выкупы и не весь кабинет.',
 'FBS 31.10: полный день; FBS 01.11: строго до 18:00 МСК. Реклама и воронка — фактический срез 18:16 МСК.',
 'Рекламные атрибуции разных РК могут пересекаться. Разные окна не сравниваются как одинаковые.',
 'Источник: WB API, сохранённый срез отчёта b85939ba. Только статистика; рекомендаций и изменений WB нет.']
 for line in footer:d.text((40,y),line,font=font(25),fill='#536b79');y+=38
 im=im.crop((0,0,W,y+25))
 out=io.BytesIO();im.save(out,format="PNG");return out.getvalue()

