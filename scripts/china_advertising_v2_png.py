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
 if 'direction_recommendations' in c:return c['direction_recommendations'] or ['Без изменений.']
 rows=[r for r in c.get('attention',[]) if r.get('action')]
 out=[r['article']+': '+r['decision'] for r in rows]
 for r in c.get('focus',[]):
  if r.get('action'):continue
  p=(r.get('comparison') or {}).get('after') or r.get('period') or {}
  if p.get('spend',0)<=0:continue
  if r.get('pending_first_day'):
   out.append(r['article']+': '+r['decision']);continue
  if r.get('candidate_for_manual_review'):
   out.append(r['article']+': '+money(p['spend'])+' ¥, '+str(int(p.get('clicks',0)))+' кликов, '+str(int(p.get('orders',0)))+' заказов. Решение не готово: экономика/наличие не подтверждены.');continue
  if p.get('amount',0)>0 and p['spend']/p['amount']>.05:
   out.append(r['article']+': '+r['decision'])
 return out or ['Не требуется']

def budget_column(c):
 """Owner-approved display only; execution conditions remain in the structured plan."""
 if c.get('owner_budget_refused'):return 'Пока не пополнять'
 if c.get('budget_audit_state')in('paused_zero','paused_review','budget_pause_review','owner_paused','draft_review','starter_review','data_blocked'):
  return c['budget_short_note']
 if c.get('budget_audit_state')=='funding_blocked':return 'Пополнение не готово.\n'+(c.get('budget_economics_reason')or'Нужна проверка экономики РК.')
 amount=c.get('budget_reserve_amount')
 if amount is None:return 'Сумма не рассчитана'
 if (c.get('budget_action')or{}).get('kind')=='topup_campaign'or c.get('budget_economics_status')=='positive':return ('Тест: пополнить на 'if (c.get('campaign_budget_economics')or{}).get('stress_after_ads_cny',0)<0 else'Пополнить на ')+str(int(amount))+' CNY.'
 return 'Пока не пополнять.\nПоложительная экономика РК не подтверждена.'
def _render_legacy(bundle):
 bundle=dict(bundle,campaigns=sorted(bundle['campaigns'],key=lambda c:not any(r.get('action') for r in c.get('attention',[]))))
 W=2400;H=6500;xs=[44,355,650,870,1090,1700,2356];files=[]
 def canvas(title):
  im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
  d.rectangle((0,0,W,205),fill=NAVY)
  d.text((44,28),title,font=font(48,True),fill='white')
  bd=bundle.get('budget_days') or []
  subtitle=('Резерв: '+bd[0]+'—'+bd[-1]+' · 3 завершённых дня МСК' if 'бюджеты' in title and len(bd)==3 else 'День: '+bundle['days'][-1]+' · 3 дня: '+bundle['days'][0]+'—'+bundle['days'][-1]+' · цель ДРР 5%')
  if bundle.get('intraday') and 'бюджеты' not in title:subtitle+=' · сегодня неполный'
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
  im,d=canvas('Китай · ДРР и рекламные расходы')
  d.text((44,216),'Рекомендации по завершённым дням · ДРР: ≤ 5% зелёный, > 5% красный',font=font(24),fill=INK)
  for i,label in enumerate(['Кампания WB','Расход, CNY','ДРР 3 дня','ДРР день','Товары: данные за 3 дня','Рекомендации по 3 дням']):
   for j,line in enumerate(wrap(d,label,xs[i+1]-xs[i]-28,29)):d.text((xs[i],267+j*35),line,font=font(29,True),fill=NAVY)
  return im,d
 im,d=table();y=365;actions=[]
 for c in bundle['campaigns']:
  if c.get('status')==7 or c.get('never_started'):continue # retained for budget audit, not ad recommendations
  p=c.get('period');day=c.get('last');draft=c.get('never_started')
  cells=[str(c['id'])+'\n'+c['name'],'День: '+(money(day['spend'])+' ¥' if day else 'не запускалась' if draft else 'нет данных')+'\n3 дня: '+(money(p['spend'])+' ¥' if p else 'не запускалась' if draft else 'нет данных'),'Не применима' if draft else pct(p),'Не применима' if draft else pct(day),summary(c),'\n'.join(recommendations(c))]
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
  unapproved=[c for c in missing if str(c['id'])not in(bundle.get('approved_statistics_exceptions')or{})]
  totals.append(None if unapproved else dict(spend=sum(c[key]['spend'] for c in known),amount=sum(c[key]['amount'] for c in known)))
 p,day=totals
 d.rounded_rectangle((24,y+10,W-24,y+190),18,fill='white')
 d.text((44,y+30),('ИТОГО · подтверждённые данные · кроме РК '+', '.join((bundle.get('approved_statistics_exceptions')or{}))) if bundle.get('approved_statistics_exceptions') else 'ИТОГО · кабинет Китай (token_3)',font=font(29,True),fill=NAVY)
 d.text((44,y+82),'Расход 3 дня: '+money(p['spend'] if p else None)+' ¥   |   Расход день: '+money(day['spend'] if day else None)+' ¥',font=font(29,True),fill=INK)
 for x,label,value in [(44,'Общая ДРР 3 дня: ',p),(1050,'Общая ДРР день: ',day)]:
  d.text((x,y+132),label,font=font(29,True),fill=INK)
  d.text((x+d.textlength(label,font=font(29,True)),y+132),pct(value),font=font(29,True),fill=color(value))
 footer='ДРР = сумма расходов / сумма рекламных заказов до скидок WB. Дни без заказов входят в расходы. Нет заказов — сумма заказов 0, ДРР не вычисляется. Исторические расходы исключённых товаров и архивных РК включены в итог. Атрибуция не равна выкупам и прибыли. Новые тесты отмечены; период может включать прежний состав. Итог относится только к кабинету Китай.'
 if bundle.get('approved_statistics_exceptions'):footer+=' РК '+', '.join(bundle['approved_statistics_exceptions'])+': новый запуск; статистика WB не сформирована, в числовой итог не включена.'
 for j,line in enumerate(wrap(d,footer,W-88,24)):d.text((44,y+218+j*31),line,font=font(24),fill='#536b79')
 finish(im,y+240+len(wrap(d,footer,W-88,24))*31,'drr',actions)
 # Owner-approved three columns; no row without a known cash shortfall.
 from china_budget_reserve import apply
 bundle=apply(bundle,bundle.get('budget_minimum_topup_cny',100))
 im,d=canvas('Китай · бюджеты и суммы пополнения');y=240;actions=[]
 selected=[c for c in bundle['campaigns'] if c.get('budget_review_required')]
 for c in selected:
  need=c.get('budget_reference_need');gap=c.get('budget_cash_gap')
  title=wrap(d,'РК '+str(c['id'])+' · '+c['name'],730,29,True)
  decision=budget_column(c)
  advice=[]
  for index,line in enumerate(decision.splitlines()):advice+=wrap(d,line,714,31 if index==0 else 27)
  height=max(300,82+39*len(advice),46+36*len(title)+150)
  if height>4800:raise ValueError('Budget card too long')
  if y+height>5500:
   finish(im,y,'budgets',actions);im,d=canvas('Китай · бюджеты и суммы пополнения');y=240;actions=[]
  d.rounded_rectangle((24,y,W-24,y+height),18,fill='white')
  for j,line in enumerate(title):d.text((44,y+16+j*36),line,font=font(29,True),fill=NAVY)
  left=y+26+len(title)*36
  d.text((44,left),'Остаток: '+money(c.get('balance'))+' ¥',font=font(29,True),fill=INK)
  d.text((44,left+48),'Запас на 3 дня: '+money(need)+' ¥',font=font(27),fill=INK)
  d.text((44,left+88),'Нехватка: '+money(gap)+' ¥',font=font(27),fill=INK)
  d.text((860,y+16),'Расходы и ДРР',font=font(29,True),fill=NAVY)
  bp=c.get('budget_period')
  budget_days=bundle.get('budget_days') or ([] if bundle.get('intraday') else bundle.get('days',[]))
  budget_day_label=__import__('datetime').date.fromisoformat(budget_days[-1]).strftime('%d.%m') if budget_days else 'неизвестную дату'
  for offset,label,value in [(64,'Вчера, '+budget_day_label+': ',c['last']['spend'] if c.get('last') else None),(104,'Расход завершённых 3 дней: ',bp['spend'] if bp else None),(144,'Средний расход в день: ',c.get('budget_average_daily'))]:
   d.text((860,y+offset),label+money(value)+' ¥',font=font(27),fill=INK)
  for offset,label,value in [(200,'ДРР завершённых дней: ',bp),(242,'ДРР за '+budget_day_label+': ',c.get('last'))]:
   d.text((860,y+offset),label,font=font(27),fill=INK)
   d.text((860+d.textlength(label,font=font(27)),y+offset),pct(value),font=font(27,True),fill=color(value))
  d.text((1630,y+16),'Рекомендация по пополнению',font=font(27,True),fill=NAVY)
  for j,line in enumerate(advice):d.text((1630,y+65+j*39),line,font=font(31 if j==0 else 27,j==0),fill=RED if j==0 and decision.startswith('Не пополнять') else INK)
  y+=height+18
  from china_budget_page_actions import page_action
  action=page_action(c,bundle)
  if action:actions.append(action)
 if not selected:
  d.text((44,y),'Проверены все РК: нет новых пополнений или неразобранных бюджетных рисков.',font=font(29),fill=INK);y+=55
 footer='Резерв на 3 дня = расход за 3 завершённых дня; нехватка = резерв − остаток. Сумма округлена вверх до 50 ¥, минимум WB '+money(bundle.get('budget_minimum_topup_cny',100))+' ¥. Пополнение — только после отдельной команды на готовую рекомендацию. Решения по РК — в рекламном PNG.'
 for line in wrap(d,footer,W-88,24):d.text((44,y+10),line,font=font(24),fill='#536b79');y+=32
 finish(im,y,'budgets',actions)
 for family in ['drr','budgets']:
  parts=[f for f in files if f['family']==family]
  for i,f in enumerate(parts,1):f.update(kind=family+':'+str(i).zfill(3),page=i,total=len(parts))
 return files

def validate_mandatory_format(bundle):
 if not bundle.get('mandatory_campaign_format'):return
 sections=bundle.get('recommendation_directions')
 if not isinstance(sections,dict)or set(sections)!={'raise','add','reduce','exclude'}:
  raise ValueError('Mandatory campaign format requires all four recommendation directions')
 from datetime import date,timedelta
 days=bundle.get('days',[])
 if len(days)!=3 or [date.fromisoformat(d)for d in days]!=[date.fromisoformat(days[-1])-timedelta(days=i)for i in(2,1,0)]:
  raise ValueError('Mandatory campaign format requires three consecutive completed days')
 campaigns=bundle.get('campaigns')
 if not isinstance(campaigns,list)or not campaigns or len({c.get('id')for c in campaigns})!=len(campaigns):
  raise ValueError('Mandatory campaign format requires unique actual campaign rows')
 for c in campaigns:
  if c.get('never_started'):continue
  if any(k not in c for k in ['period','last','name','status']):
   raise ValueError('Mandatory campaign row missing historical/current metrics')
  if c['period'] is None or c['last'] is None:
   exception=(bundle.get('approved_statistics_exceptions')or{}).get(str(c['id']))or{}
   if not(exception.get('owner_id')==5122667182 and exception.get('reason')=='new_campaign_no_wb_statistics' and exception.get('owner_accepted_separate_row')is True and c.get('created')==days[-1]):
    raise ValueError('Complete campaign statistics required before publication: '+str(c['id']))
  for metrics in[c['period'],c['last']]:
   if metrics is not None and any(k not in metrics for k in['spend','amount','orders','clicks']):
    raise ValueError('Mandatory campaign metrics incomplete')

def render(bundle):
 validate_mandatory_format(bundle)
 if bundle.get('recommendation_directions'):
  from china_advertising_directions import campaign_table
  files=_render_legacy(campaign_table(bundle))
 elif not bundle.get('economic_review_complete'):files=_render_legacy(bundle)
 else:
  from china_advertising_review_png import pages
  files=pages(bundle)+[f for f in _render_legacy(bundle) if f['family']=='budgets']
 for family in ['drr','budgets']:
  parts=[f for f in files if f['family']==family]
  for index,f in enumerate(parts,1):f.update(kind=family+':'+str(index).zfill(3),page=index,total=len(parts))
 return files





