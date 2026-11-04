"""Cash reserve and test economics use separate, explicitly completed MSK windows."""
import copy,math
from datetime import date,datetime,timedelta
from decimal import Decimal,InvalidOperation,ROUND_CEILING
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
POLICY='completed_msk_3days_target5_zeroorder_review_v3'

def number(value):
 if isinstance(value,bool) or value is None:raise ValueError('Budget input unknown')
 n=Decimal(str(value))
 if not n.is_finite() or n<0:raise ValueError('Budget input invalid')
 return n

def instant(value):
 if not isinstance(value,str):raise ValueError('Timestamp missing')
 t=datetime.fromisoformat(value.replace('Z','+00:00'))
 if t.tzinfo is None:raise ValueError('Timestamp without timezone')
 return t

def attach_completed_evidence(bundle,source,changes):
 """Keep current display figures intact; budget evidence never contains today."""
 out=copy.deepcopy(bundle)
 observed=instant(source['observed_at']);today=observed.astimezone(MSK).date()
 end=min(date.fromisoformat(source['period_to']),today-timedelta(days=1))
 days=[str(end-timedelta(days=i)) for i in (2,1,0)]
 out['budget_days']=days;out['budget_observed_at']=source['observed_at']
 out['budget_balance_observed_at_iso']=source.get('budget_balance_observed_at_iso',source['observed_at'])
 campaigns={c['id']:c for b in source['batches'].values() for c in b['campaigns']['adverts']}
 stats={c['advertId']:c for b in source['batches'].values() for c in b['stats']}
 econ=source.get('economics') or {}
 for c in out['campaigns']:
  raw=stats.get(c['id']);state=campaigns[c['id']]
  complete=bool(raw is not None and source.get('period_from','9999')<=days[0] and source['period_to']>=days[-1])
  daily={d['date'][:10]:d for d in (raw or {}).get('days',[])}
  c['budget_period']=None;c['budget_days']=days;c['budget_members']=[]
  if complete:
   values={k:0 for k in ('spend','amount','orders')}
   for day in days:
    r=daily.get(day)
    # Absent day within a complete returned campaign is inactive, not a missing campaign.
    if r is None:continue
    for k,f in [('spend','sum'),('amount','sum_price'),('orders','orders')]:
     try:values[k]+=float(number(r.get(f)))
     except (ValueError,InvalidOperation,TypeError):complete=False
   if complete:c['budget_period']=values
  for n in state.get('nm_settings',[]):
   nm=n['nm_id'];events=[x for x in changes if x.get('nm')==nm and x.get('kind') in ('bid','added','price','returned','relaunch','excluded')]
   # Price and bid changes in any campaign of the same SKU matter; membership changes only here.
   events=[x for x in events if x.get('kind') in ('price','bid') or x.get('cid')==c['id']]
   ats=[x['at'] for x in events]
   if state.get('timestamps',{}).get('started'):ats.append(state['timestamps']['started'])
   latest=max((instant(t) for t in ats),default=None)
   evidence=copy.deepcopy(econ.get('rows',{}).get(str(nm)) or {})
   evidence.setdefault('observed_at',econ.get('observed_at'))
   first_full=str(latest.astimezone(MSK).date()+timedelta(days=1)) if latest else None
   member_rows=[r for day in days if not first_full or day>=first_full for app in daily.get(day,{}).get('apps',[]) for r in app.get('nms',[]) if r.get('nmId')==nm]
   traffic=None
   if member_rows:
    try:traffic={k:sum(float(number(r.get(f))) for r in member_rows) for k,f in [('spend','sum'),('orders','orders'),('amount','sum_price')]}
    except (ValueError,InvalidOperation,TypeError):traffic=None
   c['budget_members'].append(dict(nm=nm,first_full_day=first_full,economics=evidence,completed_traffic=traffic))
 if source.get('full_growth_inputs'):
  from china_budget_ready_model import attach as attach_campaign_model
  out=attach_campaign_model(out,source,changes)
 return out

def economics_review(c,days,observed):
 """Positive own model may support a small test; DRR alone never denies funding."""
 campaign_model=c.get('campaign_budget_economics')
 if campaign_model:
  try:
   if not 0<=(observed-instant(campaign_model['observed_at'])).total_seconds()<=24*3600:raise ValueError('Stale campaign model')
   if campaign_model.get('period_to',days[-1])>days[-1]:raise ValueError('Incomplete campaign model day')
   return campaign_model['status'],campaign_model['reason']
  except (KeyError,ValueError,TypeError):return 'unknown','Нет свежей модели результата всей РК.'
 members=c.get('budget_members') or []
 if not members:return 'unknown','Не подтверждены текущий состав и экономика SKU.'
 missing=[];small=[];negative=[];waiting=[]
 for m in members:
  nm=m['nm'];first=m.get('first_full_day');e=m.get('economics') or {}
  if first and first>days[-1]:waiting.append(nm);continue
  try:
   at=instant(e['observed_at']);pfrom=e['period_from'];pto=e['period_to']
   profit=float(e['expected_total_profit_rub'])
   if not math.isfinite(profit) or not e.get('source_ids') or not e.get('basis'):raise ValueError('No dated own model')
   if not pfrom<=pto<observed.astimezone(MSK).date().isoformat():raise ValueError('Incomplete-day economics')
   if first and pfrom<first:raise ValueError('Mixed before/after change economics')
   if not 0<=(observed-at).total_seconds()<=48*3600:raise ValueError('Stale economics')
   # A profit figure without explicit own costs and selling price is not funding evidence.
   if number(e.get('own_cogs_rub'))<=0 or number(e.get('seller_revenue_rub'))<=0:raise ValueError('Missing own costs')
   if profit<=0:negative.append(nm)
   if e.get('sample_size',0)<10 or e.get('preliminary',True):small.append(nm)
  except (KeyError,TypeError,ValueError,InvalidOperation):missing.append(nm)
 if waiting:return 'waiting','Первый полный день после verified изменения ещё не завершён; согласовать резерв теста отдельно.'
 if missing:return 'unknown','Нужна свежая собственная экономика после последнего изменения: '+str(len(missing))+' SKU; неизвестные расходы не равны нулю.'
 if negative:
  # A small/unfinished cohort or fallback buyout is not a proven loss.
  return 'review','Модель экономики не даёт положительного результата: '+str(len(negative))+' SKU. Проверить выборку и расходы; согласовать продолжение теста.'
 return 'positive',('Предварительная положительная экономика; малая выборка/неподтверждённые расходы, низкая ДРР не доказана.' if small else 'Положительная собственная модель по завершённым дням; не гарантия будущего результата.')

def apply(bundle,minimum_cny=100):
 out=copy.deepcopy(bundle);minimum=number(minimum_cny)
 if minimum<=0:raise ValueError('WB topup minimum unknown')
 out['budget_reserve_policy']=POLICY;out['budget_minimum_topup_cny']=float(minimum)
 for c in out['campaigns']:
  c['budget_action']=None;c['budget_review_required']=False
  for field in ('budget_reserve_amount','budget_economics_status','budget_economics_reason','budget_drr','budget_followup'):c.pop(field,None)
  if c.get('status')!=9 or c.get('never_started'):continue
  try:
   days=out['budget_days'];observed=instant(out['budget_observed_at'])
   balance_at=instant(out['budget_balance_observed_at_iso'])
   if not 0<=(observed-balance_at).total_seconds()<=80*60:raise ValueError('Stale campaign balance')
   parsed=[date.fromisoformat(d) for d in days]
   if len(parsed)!=3 or parsed!=[parsed[-1]-timedelta(days=i) for i in (2,1,0)] or parsed[-1]>=observed.astimezone(MSK).date():raise ValueError('Not three completed days')
   period=c.get('budget_period') or {};spend=number(period.get('spend')).quantize(Decimal('.01'));balance=number(c.get('balance')).quantize(Decimal('.01'))
   revenue=number(period.get('amount'))
  except (KeyError,ValueError,InvalidOperation,TypeError):
   c.update(budget_review_required=True,budget_reference_need=None,budget_cash_gap=None,budget_average_daily=None,budget_short_note='Сумма не рассчитана: нет полного среза за 3 завершённых дня МСК или свежего остатка.');continue
  gap=max(Decimal(0),spend-balance)
  c.update(budget_reference_need=float(spend),budget_cash_gap=float(gap),budget_average_daily=float(spend/3),budget_review_required=gap>0,budget_drr=float(spend/revenue*100) if revenue else None)
  c.pop('budget_risk_note',None);c.pop('budget_reference_amount',None)
  if gap==0:
   c['budget_short_note']='Пополнение не требуется по расчётному запасу на 3 дня.';c['budget_recommendation']=c['budget_short_note'];continue
  amount=(max(minimum,gap)/50).to_integral_value(rounding=ROUND_CEILING)*50
  c['budget_reserve_amount']=int(amount)
  state,reason=economics_review(c,days,observed)
  c['budget_economics_status']=state;c['budget_economics_reason']=reason
  label='ДРР завершённых дней не определена без суммы рекламных заказов. ' if revenue==0 else ''
  decision='Пока не пополнять. '+label+reason
  zero_orders=spend>0 and period.get('orders')==0
  zero_members=[m['nm'] for m in c.get('budget_members',[]) if (m.get('completed_traffic') or {}).get('spend',0)>0 and m['completed_traffic'].get('orders')==0]
  zero_orders=zero_orders or bool(zero_members)
  over5=c['budget_drr'] is not None and c['budget_drr']>5
  approved=c.get('approved_test_risk_remaining_cny')
  bounded=type(approved) in (int,float) and math.isfinite(approved) and approved>0
  campaign_positive=(c.get('campaign_budget_economics')or{}).get('status')=='positive'
  blocked=(zero_orders or over5) and not campaign_positive and not (bounded and (not over5 or c.get('approved_drr_exception') is True))
  if blocked:
   decision='Пока не пополнять. '+label+reason
   c['budget_followup']=dict(status='recommendation_only',requires_fresh_review=True,execution_authorized=False)
  if state=='positive' and not blocked:
   decision='Пополнить на '+str(int(amount))+' ¥\nЗапас на 3 дня. '+label+reason
   members=sorted({m['nm'] for m in c['budget_members']})
   if not out.get('view_only'):
    c['budget_action']=dict(id='topup:'+str(c['id']),kind='topup_campaign',campaign_id=c['id'],amount_cny=int(amount),balance_before=float(balance),target_balance=float(balance+amount),status_before=9,nm_ids=members,basis=POLICY,completed_days=days,budget_evidence=copy.deepcopy(c.get('campaign_budget_economics')))
  c['budget_short_note']=decision;c['budget_recommendation']=decision
 return out


