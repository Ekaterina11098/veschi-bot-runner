"""Approved IP/China three-column budget display. Pure retained-data renderer, no payments."""
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image,ImageDraw
from ip_campaign_table_png import font,NAVY,BG,INK,RED,money

def number(v):return type(v) in (int,float) and math.isfinite(v) and v>=0

def budget_rows(view):
 rows=[];omitted=[];known=0;active=0
 for c in view['campaigns']:
  if c.get('status_id')!=9:continue
  active+=1;b=c.get('budget') or {};cost=c.get('spend')
  if not b.get('valid') or not b.get('today_observation') or not number(b.get('balance')) or not b.get('observed_at'):
   omitted.append((c['campaign_id'],'нет баланса за день наблюдения'));continue
  if not c.get('metrics_complete') or not number(cost):omitted.append((c['campaign_id'],'нет полного расхода за '+view['period']));continue
  known+=1
  if cost==0:omitted.append((c['campaign_id'],'нулевой расход; срок не рассчитывается'));continue
  reserve=3*cost;gap=max(0,reserve-b['balance'])
  if gap<=0:continue
  seq=[]
  for v in sorted((view.get('_recent_views') or [])+[view],key=lambda v:v['period']):
   p=next((r for r in v['campaigns'] if r['campaign_id']==c['campaign_id']),None)
   if p and p.get('metrics_complete') and number(p.get('spend')) and number(p.get('revenue')):seq.append((v['period'],p['spend'],p['revenue']))
  seq=list({p[0]:p for p in seq}.values())[-3:] or [(view['period'],cost,c.get('revenue'))]
  rows.append(dict(campaign=c['campaign_id'],name=c.get('campaign_name') or '',balance=b['balance'],observed_at=b['observed_at'],spend=cost,revenue=c.get('revenue'),reserve=reserve,gap=gap,proposal=math.ceil(gap/1000)*1000,period_rows=seq))
 return rows,dict(active=active,known=known,omitted=omitted,proposals=len(rows))

def render_budget_png(view,outdir):
 rows,coverage=budget_rows(view)
 if coverage['active'] and not coverage['known']:return None,coverage
 W=2400;H=1400+len(rows)*650;im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
 def wrap(s,w,n,b=False):
  lines=[]
  for p in str(s).split('\n'):
   line=''
   for word in p.split():
    trial=(line+' '+word).strip()
    if line and d.textlength(trial,font=font(n,b))>w:lines.append(line);line=word
    else:line=trial
   lines.append(line)
  return lines
 def text(s,x,y,w,n=27,b=False,color=INK):
  lines=wrap(s,w,n,b)
  for j,line in enumerate(lines):d.text((x,y+j*(n+8)),line,font=font(n,b),fill=color)
  return len(lines)*(n+8)
 def date(s):return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m %H:%M')
 def ratio(cost,rev):return 'нет данных' if not number(rev) else money(100*cost/rev)+'%' if rev>0 else 'без заказов' if cost>0 else 'нет расхода'
 d.rectangle((0,0,W,205),fill=NAVY)
 d.text((44,28),'ИП · бюджеты и суммы пополнения',font=font(48,True),fill='white')
 d.text((44,100),'Предложения · только РК с расчётной нехваткой · RUB',font=font(29,True),fill='white')
 d.text((44,150),'Отчёт '+view['observed_day']+' · база расхода: полный день '+view['period']+' · время МСК',font=font(24),fill='#dce9f0');y=240
 for c in rows:
  seq=c['period_rows'];label='—'.join([seq[0][0],seq[-1][0]]) if len(seq)>1 else seq[0][0] if seq else view['period'];ps=sum(p[1] for p in seq);pr=sum(p[2] for p in seq) if all(number(p[2]) for p in seq) else None
  left=[('РК '+str(c['campaign'])+' · '+c['name'],29,True),('Остаток: '+money(c['balance'])+' ₽',29,True),('Наблюдение: '+date(c['observed_at'])+' МСК',24,False),('Ориентир на 3 суток*: '+money(c['reserve'])+' ₽',27,False),('Расчётная нехватка: '+money(c['gap'])+' ₽',27,False)]
  lh=sum(len(wrap(s,730,n,b))*(n+8)+7 for s,n,b in left)+24;height=max(350,lh)
  d.rounded_rectangle((24,y,W-24,y+height),18,fill='white');ly=y+16
  for s,n,b in left:ly+=text(s,44,ly,730,n,b)+7
  text('Расходы и ДРР',860,y+16,714,29,True,color=NAVY)
  text('День '+view['period']+': '+money(c['spend'])+' ₽',860,y+64,714)
  text('Расход '+label+': '+money(ps)+' ₽',860,y+106,714,25)
  text('Средний за '+str(len(seq))+' полных дн.: '+money(ps/len(seq))+' ₽',860,y+148,714,25)
  text('ДРР периода: '+ratio(ps,pr),860,y+202,714,27,True,color=RED if not pr or ps/pr>.05 else INK)
  text('ДРР дня: '+ratio(c['spend'],c['revenue']),860,y+244,714,27,True,color=RED if not c['revenue'] or c['spend']/c['revenue']>.05 else INK)
  text('Рекомендация по пополнению',1630,y+16,714,27,True,color=NAVY)
  if not c['revenue'] or c['spend']/c['revenue']>.05 or (pr and ps/pr>.05):
   text('Пока не пополнять',1630,y+65,714,31,True,color=RED)
   text('Сначала скорректировать рекламу. Расчётная нехватка не означает, что пополнение целесообразно.',1630,y+112,714,27)
  else:
   text('Предлагается '+str(c['proposal'])+' ₽',1630,y+65,714,31,True)
   text('После исполнения рекомендаций РК.\nПополнение не выполнено.',1630,y+112,714,27)
  y+=height+18
 if not rows:
  y+=text('Расчётной нехватки на 3 суток по доступным данным нет. Проверено активных РК: '+str(coverage['known'])+' из '+str(coverage['active'])+'.' if coverage['active'] else 'Активных РК нет. Пополнения не предлагаются.',44,y,W-88,30,True)+30
 notes=['* Ориентир на 3 суток = расход '+view['period']+' × 3; нехватка = ориентир − наблюдавшийся баланс. Это условная оценка, не фактический расход за три дня и не гарантия срока.',
 'Суммы предложены с округлением вверх до 1 000 ₽ для согласования. Это не минимум WB и не разрешение перевода денег. Команда к PNG рекомендаций не разрешает пополнения.',
 'После изменений рекламы темп может измениться. Расход после времени наблюдения не вычтен. Архивные/приостановленные РК и РК без расчётной нехватки не показаны.']
 if coverage['omitted']:notes.append('Расчёт не выполнен: '+'; '.join(str(cid)+' — '+reason for cid,reason in coverage['omitted'])+'. Неизвестный или нулевой расход не означает бесконечный запас бюджета.')
 for s in notes:y+=text(s,44,y+10,W-88,24,color='#536b79')+10
 if y+25>H:raise ValueError('Budget layout overflow; do not clip')
 out=Path(outdir);out.mkdir(parents=True,exist_ok=True);path=out/'budgets.png';im.crop((0,0,W,y+25)).save(path,optimize=True)
 return dict(kind='budgets',path=str(path)),coverage
