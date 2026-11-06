"""Approved three-day-first table, page-bound new actions, durable delivery families."""
import io
from PIL import Image,ImageDraw,ImageFont
def ratio(v):
 return None if not v or not v.get('amount') else 100*v['spend']/v['amount']
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
def original_summary(c):
 day=c.get('last');p=c.get('period')
 if c.get('never_started'):return '3 товара; кампания не запускалась.' if c.get('member_count')==3 else 'Кампания не запускалась.'
 if p is None:return 'Статистика отсутствует; числовой результат не подтверждён.'
 return ('День: '+str(int(day['orders']))+' рекламных заказов; сумма '+money(day['amount'])+' ₽.\n' if day else 'День: нет данных.\n')+str(c.get('period_count',3))+' дн.: '+str(int(p['orders']))+' рекламных заказов; сумма '+money(p['amount'])+' ₽; '+str(int(p['clicks']))+' кликов.'
def summary(c):
 text=original_summary(c)
 if c.get('no_order_count') is not None and c.get('no_order_spend') is not None and c['no_order_count']>0:
  text+='\nБез прямых заказов за день: '+str(c['no_order_count'])+' SKU · '+money(c['no_order_spend'])+' ₽.'
 return text

def recommendations(c):
 if 'direction_recommendations' in c:return c['direction_recommendations'] or ['Новых готовых действий нет.']
 rows=[r for r in c.get('attention',[]) if r.get('action')]
 out=[r['article']+': '+r['decision'] for r in rows]
 for r in c.get('focus',[]):
  if r.get('action'):continue
  p=(r.get('comparison') or {}).get('after') or r.get('period') or {}
  if p.get('spend',0)<=0:continue
  if r.get('pending_first_day'):
   out.append(r['article']+': '+r['decision']);continue
  if r.get('candidate_for_manual_review'):
   out.append(r['article']+': '+money(p['spend'])+' ₽, '+str(int(p.get('clicks',0)))+' кликов, '+str(int(p.get('orders',0)))+' заказов. Решение не готово: экономика/наличие не подтверждены.');continue
  if p.get('amount',0)>0 and p['spend']/p['amount']>.05:
   out.append(r['article']+': '+r['decision'])
 return out or ['Новых готовых действий нет.']

def budget_column(c):
 """Owner-approved display only; execution conditions remain in the structured plan."""
 if c.get('owner_budget_refused'):return 'Пока не пополнять'
 amount=c.get('budget_reserve_amount')
 if amount is None:return 'Сумма не рассчитана'
 return 'Рекомендовано '+str(int(amount))+' ₽\nпосле исполнения рекомендаций РК'

def render_ip(view,contract,outdir):
 """One campaign per row. Display context is never an executable approval."""
 from pathlib import Path
 allviews=sorted((view.get('_recent_views') or [])+[view],key=lambda v:v['period'])
 total=len(view['campaigns'])
 usable=[v for v in allviews if len(v['campaigns'])==total and all(c.get('metrics_complete') for c in v['campaigns'])]
 days=sorted(set(v['period'] for v in usable))[-3:] or [view['period']]
 index={v['period']:{c['campaign_id']:c for c in v['campaigns']} for v in allviews}
 def metrics(c):
  if not c or not c.get('metrics_complete') or any(c.get(k) is None for k in ('spend','revenue','total_orders','clicks')):return None
  return dict(spend=c['spend'],amount=c['revenue'],orders=c.get('total_orders'),clicks=c.get('clicks'))
 def decision(a):
  val=lambda v:money(v/100)+' ₽'
  if a['kind']=='remove':return a['sku']+': исключить только из этой РК.'
  if a['kind']=='add':return a['sku']+': '+('тест — ' if a.get('research_test') else '')+'добавить только в эту РК, поиск '+val(a['target_bid_minor'])+'.'
  return a['sku']+': '+('тест — ' if a.get('research_test') else '')+('повысить' if a['kind']=='raise_bid' else 'снизить')+' '+val(a['stored_bid_minor'])+' → '+val(a['target_bid_minor'])+'.'
 campaigns=[]
 for raw in view['campaigns']:
  cid=raw['campaign_id'];seq=[metrics(index.get(day,{}).get(cid)) for day in days]
  # Unknown clicks/orders must not become zero in the campaign summary.
  if any(v is not None and (v['orders'] is None or v['clicks'] is None) for v in seq):seq=[None if v and (v['orders'] is None or v['clicks'] is None) else v for v in seq]
  period={k:sum(v[k] for v in seq) for k in ('spend','amount','orders','clicks')} if all(v is not None for v in seq) else None
  current=[a for a in contract['actions'] if a['campaign']==cid]
  rec=[decision(a)+' Новое предложение.' for a in current]
  # Execution receipts and analytical notes stay internal, never recommendations.
  if not rec:rec=['РК приостановлена; запуск не предлагается.'] if raw.get('status_id')==11 else ['Архив; не запускать.'] if raw.get('status_id')==7 else ['Новых готовых действий нет.']
  label=contract.get('campaign_labels',{}).get(str(cid),{})
  name=raw.get('campaign_name') or label.get('name') or 'Название не сохранено'
  pay=raw.get('payment_type') or label.get('payment')
  name+=' · '+('CPC — оплата за клики' if pay=='cpc' else 'CPM — оплата за показы' if pay=='cpm' else 'тип оплаты не сохранён')
  campaigns.append(dict(id=cid,name=name,status=raw.get('status_id'),last=metrics(raw),period=period,period_count=len(days),attention=[{'action':a} for a in current],focus=[],direction_recommendations=rec,no_order_count=raw.get('no_order_count'),no_order_spend=raw.get('no_order_spend')))
 bundle=dict(days=days,campaigns=campaigns,source_observed_at='Сохранённые данные: '+str(sum(c.get('metrics_complete') is True for c in view['campaigns']))+'/'+str(total)+' РК за '+view['period']+' · в команде только новые действия')
 bundle['review_coverage']=contract.get('review_coverage') or {}
 files=render_campaign_table(bundle)
 if len(files)!=1:raise ValueError('Campaign table exceeds one PNG; explicit layout review required, no clipped or unbound actions')
 out=Path(outdir);out.mkdir(parents=True,exist_ok=True);path=out/'recommendations.png';path.write_bytes(files[0]['bytes'])
 return dict(kind='drr',path=str(path))
def render_campaign_table(bundle):
 bundle=dict(bundle,campaigns=sorted([c for c in bundle['campaigns'] if not c.get('never_started')],key=lambda c:not any(r.get('action') for r in c.get('attention',[]))))
 W=2400;H=6500;xs=[44,355,650,870,1090,1700,2356];files=[]
 count=len(bundle['days']);period_label=str(count)+' дн.'
 def canvas(title):
  im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
  d.rectangle((0,0,W,205),fill=NAVY)
  d.text((44,28),title,font=font(48,True),fill='white')
  bd=bundle.get('budget_days') or []
  subtitle=('Резерв: '+bd[0]+'—'+bd[-1]+' · 2 завершённых дня МСК' if 'бюджеты' in title and len(bd)==3 else 'День: '+bundle['days'][-1]+' · '+period_label+': '+bundle['days'][0]+'—'+bundle['days'][-1]+' · цель ДРР 5%')
  if bundle.get('intraday') and 'бюджеты' not in title:subtitle='Сегодня: '+str(bundle.get('observed_day'))+' · неполный день · база решений: '+bundle['days'][0]+'—'+bundle['days'][-1]
  d.text((44,100),subtitle,font=font(29,True),fill='white')
  d.text((44,150),'Срез: '+(str(bundle['source_observed_at'])+(' · остатки: '+bundle['budget_balance_observed_at'] if 'бюджеты' in title and bundle.get('budget_balance_observed_at') else '')),font=font(24),fill='#dce9f0')
  return im,d
 def wrap(d,s,w,n=27,bold=False):
  out=[]
  for p in str(s).split('\n'):
   line=''
   for word in p.split():
    test=(line+' '+word).strip()
    if line and d.textlength(test,font=font(n,bold))>w:out.append(line);line=word
    else:line=test
   out.append(line)
  return out
 def finish(im,y,family,actions):
  b=io.BytesIO();im.crop((0,0,W,min(H,y+30))).save(b,format='PNG')
  files.append(dict(family=family,bytes=b.getvalue(),actions=actions))
 def table():
  im,d=canvas('ИП · ДРР и рекламные расходы')
  d.text((44,216),'Рекомендации по завершённым дням · ДРР: ≤ 5% зелёный, > 5% красный',font=font(24),fill=INK)
  for i,label in enumerate(['Кампания WB','Расход, RUB','ДРР '+period_label,('ДРР сегодня*' if bundle.get('intraday') else 'ДРР день'),'Товары: данные за '+period_label,'Рекомендации']):
   for j,line in enumerate(wrap(d,label,xs[i+1]-xs[i]-28,29)):d.text((xs[i],267+j*35),line,font=font(29,True),fill=NAVY)
  return im,d
 im,d=table();y=365;actions=[]
 for c in bundle['campaigns']:
  if c.get('status')==7:continue # archives contribute to totals below, not recommendation rows
  p=c.get('period');day=c.get('last');draft=c.get('never_started')
  cells=[str(c['id'])+'\n'+c['name'],'День: '+(money(day['spend'])+' ₽' if day else 'не запускалась' if draft else 'нет данных')+'\n'+period_label+': '+(money(p['spend'])+' ₽' if p else 'не запускалась' if draft else 'нет данных'),'Не применима' if draft else pct(p),'Не применима' if draft else pct(day),summary(c),'\n'.join(recommendations(c))]
  ls=[wrap(d,s,xs[i+1]-xs[i]-34,bold=(i==5 and bool(c.get('attention')))) for i,s in enumerate(cells)]
  h=max(140,max(map(len,ls))*35+36)
  if h>4800:raise ValueError('Campaign row too long; refuse clipped report')
  if y+h>5500:
   finish(im,y,'drr',actions);im,d=table();y=365;actions=[]
  d.rounded_rectangle((24,y,W-24,y+h),18,fill='#fff1cc' if any(r.get('action') for r in c.get('attention',[])) else 'white')
  for i,lines in enumerate(ls):
   col=color(p) if i==2 else color(day) if i==3 else INK
   for j,line in enumerate(lines):d.text((xs[i],y+18+j*35),line,font=font(27,i==5 and bool(c.get('attention'))),fill=col)
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
 d.text((44,y+30),'ИТОГО · кабинет ИП',font=font(29,True),fill=NAVY)
 d.text((44,y+82),'Расход '+period_label+': '+money(p['spend'] if p else None)+' ₽   |   Расход день: '+money(day['spend'] if day else None)+' ₽',font=font(29,True),fill=INK)
 for x,label,value in [(44,'Общая ДРР '+period_label+': ',p),(1050,'Общая ДРР день: ',day)]:
  d.text((x,y+132),label,font=font(29,True),fill=INK)
  d.text((x+d.textlength(label,font=font(29,True)),y+132),pct(value),font=font(29,True),fill=color(value))
 footer='ДРР = сумма расходов / сумма рекламных заказов по сохранённому источнику. Дни без заказов входят в расходы. Нет заказов — сумма заказов 0, ДРР не вычисляется. Исторические расходы исключённых товаров и архивных РК включены в итог. Атрибуция не равна выкупам и прибыли. Новые тесты отмечены; период может включать прежний состав. Итог относится только к кабинету ИП. Архивные РК учтены в итоге, без рекомендаций запуска. Предложения не выполнены и требуют согласования. Суммы SKU могут отличаться от РК из-за округления.'
 if (bundle.get('review_coverage') or {}).get('conditional_basis_used'):footer+=' Часть усилений — исследовательские предложения по сохранённому сценарию выкупа при той же цене. Это не подтверждённая прибыль текущего периода или следующих заказов.'
 for j,line in enumerate(wrap(d,footer,W-88,24)):d.text((44,y+218+j*31),line,font=font(24),fill='#536b79')
 finish(im,y+240+len(wrap(d,footer,W-88,24))*31,'drr',actions)
 return files

