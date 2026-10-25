import json,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
O=Path('outputs');rs=json.loads((O/'ad25-numeric-review.json').read_text('utf-8'))['rows'];inputs=json.loads((O/'ad25-analysis-input.json').read_text('utf-8'));summaries=json.loads((O/'ad25-campaign-summary.json').read_text('utf-8'));weekly={r['cid']:r for b in summaries if b['from']!=b['to'] for r in b['rows']};bud={r['id']:r for r in json.loads((O/'ad25-budgets-source.json').read_text('utf-8'))};F=lambda n,b=False:ImageFont.truetype('/usr/share/fonts/truetype/dejavu/'+('DejaVuSans-Bold.ttf' if b else 'DejaVuSans.ttf'),max(18,n-2))
agg={}
for r in inputs['stats']:
 k=(r['cid'],r['day']);v=agg.setdefault(k,dict(spend=0,amount=0,orders=0))
 for a,b in [('spend','sum'),('amount','sum_price'),('orders','orders')]:v[a]+=r.get(b) or 0
def fmt(v,n=2):return '—' if v is None else f'{v:,.{n}f}'.replace(',',' ').replace('.',',')
def drr(v):return v['spend']/v['amount']*100 if v and v['amount'] else None
pages=[];manifest=[]
for cid in sorted({r['cid'] for r in rs}):
 rr=sorted([r for r in rs if r['cid']==cid],key=lambda r:(not r['changed'],r['article']));v=agg.get((cid,'2026-10-24'),{});ss=sum(agg.get((cid,day),{}).get('spend',0) for day in ['2026-10-22','2026-10-23','2026-10-24']);aa=sum(agg.get((cid,day),{}).get('amount',0) for day in ['2026-10-22','2026-10-23','2026-10-24']);period=ss/aa*100 if aa else None
 for start in range(0,len(rr),8):
  num=len(pages)+1;W=2800;im=Image.new('RGB',(W,3000),'#edf3f7');d=ImageDraw.Draw(im)
  def t(s,x,y,w,n=25,col='#234154',b=False):
   line=''
   for word in s.split():
    nxt=(line+' '+word).strip()
    if line and d.textlength(nxt,font=F(n,b))>w:d.text((x,y),line,font=F(n,b),fill=col);y+=n+7;line=word
    else:line=nxt
   if line:d.text((x,y),line,font=F(n,b),fill=col);y+=n+7
   return y
  d.rectangle((0,0,W,110),fill='#193d54');t('Китай · рекомендации и выполненные действия · 25.10.2026',30,22,2700,42,'white',True);y=130
  d.rectangle((15,y,W-15,y+135),fill='#193d54');t(f'РК {cid} · {bud[cid]["name"]} · часть {start//8+1}/{math.ceil(len(rr)/8)}',30,y+15,2700,33,'white',True)
  t(f'Расход 24.10: {fmt(v.get("spend"))} ¥  |  18–24.10: {fmt(weekly[cid]["spend"],0)} ¥  |  ДРР 24.10: {fmt(drr(v))}%  |  ДРР 22–24.10: {fmt(period)}%',30,y+72,2700,29,'white',True);y+=155
  xs=[30,405,565,725,890,1160,1750];headers=['Артикул','22.10','23.10','24.10','ДРР периода','Уже сделано · МСК','Рекомендация сейчас / подтверждение']
  for x,z in zip(xs,headers):t(z,x,y,1000,25,b=True)
  y+=55
  selected=rr[start:start+8]
  for idx,r in enumerate(selected):
   top=y;h=245;d.rectangle((15,y,W-15,y+h-8),fill='white' if idx%2==0 else '#e1ebf3');end=[t(r['article'],30,y+13,355,25,b=True)]
   for x,day in zip(xs[1:4],['2026-10-22','2026-10-23','2026-10-24']):
    z=r['daily'].get(day);ratio=drr(z);t(fmt(ratio)+'%',x,y+13,160,26,'#b63345' if ratio and ratio>5 else '#234154',True)
   end.append(t(fmt(r['period_drr'])+'%',890,y+13,255,27,b=True));t(f'{r["period"]["orders"]} рекл. зак. за 3 дня',890,y+52,255,23)
   if r['drr_change_pct'] is not None:t(f'22→24: {fmt(r["drr_change_pct"],1)}%',890,y+91,255,23)
   end.append(t(r['done'],1160,y+13,560,25,col='#26725a' if r['changed'] else '#647b8c'))
   color='#b63345' if r['kind'] in ['exclude','lower','pause_risk'] else '#234154';yy=t(r['action'],1750,y+13,1010,26,color,True);yy=t(r['reason'],1750,yy+5,1010,24)
   a=r['after'];b=r['before'];yy=t(f'Расход 24.10: {fmt(a["spend"])} ¥; {a["orders"]} зак.; показы {(b or {}).get("views","—")}→{a["views"]}; клики {(b or {}).get("clicks","—")}→{a["clicks"]}.',1750,yy+5,1010,23,col='#647b8c');end.append(yy)
   assert max(end)<=top+h,(r['article'],max(end)-top)
   y+=h
  y=t('ДРР периода = сумма расходов / сумма рекламных заказов, не среднее процентов. WB приоритетнее MPStats. Расход дня / ДРР — WB; расход недели — округлённая сводка MPStats. «—» при нуле суммы заказов.',30,y+10,2740,24,col='#647b8c')
  y=t('Сравнение теста: 22→24.10 для изменений 23.10. Заказы в колонке периода — сумма 22–24.10; дневные значения относятся к отдельным дням. Для 553 отдельно предложено исключение из-за повторного безрезультатного расхода, без ожидания нового полного дня.',30,y+6,2740,24,col='#647b8c')
  y=t('Экономика предварительная: собственный выкуп 30 полных дней, COGS МойСклад, комиссия 20%, налог 5%, 12 ₽/¥, обработка 10 ₽, историческая логистика; другие расходы неполны. Ставки/состав: WB 25.10 около 08:04 МСК. Изменения не применены.',30,y+6,2740,24,col='#647b8c')
  path=O/f'VESCHI-China-ad-grouped-final-2026-10-25-{num:02}.png';im.crop((0,0,W,y+20)).save(path);pages.append(str(path));manifest.append({'file':str(path),'campaign':cid,'nm_ids':[r['nm'] for r in selected]})
(O/'ad25-grouped-final-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8');assert sum(len(x['nm_ids']) for x in manifest)==len(rs);print(json.dumps({'pages':len(pages),'rows':len(rs),'files':pages},ensure_ascii=False))

