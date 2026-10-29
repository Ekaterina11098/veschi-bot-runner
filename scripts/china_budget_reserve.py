"""Owner29Oct: cash reserve from completed whole-campaign spend; no transport."""
import copy,math
from decimal import Decimal,InvalidOperation,ROUND_CEILING
POLICY='average_completed_3days_exact_topup_v1'
def number(value):
 if isinstance(value,bool) or value is None:raise ValueError('Budget input unknown')
 n=Decimal(str(value))
 if not n.is_finite() or n<0:raise ValueError('Budget input invalid')
 return n
def apply(bundle,minimum_cny=100):
 out=copy.deepcopy(bundle);minimum=number(minimum_cny)
 if minimum<=0:raise ValueError('WB topup minimum unknown')
 out['budget_reserve_policy']=POLICY;out['budget_minimum_topup_cny']=float(minimum)
 for c in out['campaigns']:
  c['budget_action']=None;c['budget_review_required']=False
  if c.get('status')!=9 or c.get('never_started'):continue
  try:
   if c.get('missing_stats') or len(out.get('days',[]))!=3:raise ValueError('Incomplete completed-day source')
   period=c.get('period') or {};spend=number(period.get('spend')).quantize(Decimal('.01'));balance=number(c.get('balance')).quantize(Decimal('.01'))
  except (ValueError,InvalidOperation,TypeError):
   c.update(budget_review_required=True,budget_reference_need=None,budget_cash_gap=None,budget_average_daily=None,budget_short_note='Сумма не рассчитана: нет подтверждённых расходов или остатка.');continue
  gap=max(Decimal(0),spend-balance)
  c.update(budget_reference_need=float(spend),budget_cash_gap=float(gap),budget_average_daily=float(spend/3),budget_review_required=gap>0)
  c.pop('budget_risk_note',None);c.pop('budget_reference_amount',None)
  if gap==0:
   c['budget_short_note']='Пополнение не требуется';c['budget_recommendation']=c['budget_short_note'];continue
  amount=(max(minimum,gap)/50).to_integral_value(rounding=ROUND_CEILING)*50
  c['budget_reserve_amount']=int(amount) if amount==int(amount) else float(amount)
  try:revenue=number(period.get('amount'))
  except (ValueError,InvalidOperation,TypeError):revenue=Decimal(0)
  drr=spend/revenue*100 if revenue else None
  if drr is None:
   decision='Согласовать продолжение теста: ДРР не определена без суммы рекламных заказов.'
  elif drr>5:
   decision='Не пополнять сейчас\nДРР за 3 дня '+f'{drr:.2f}'.replace('.',',')+'% выше цели 5%.'
   if c.get('new_composition'):decision+='\nСначала оценить полный день нового состава.'
  else:
   members=sorted({r['nm'] for r in c.get('current_articles',[]) if type(r.get('nm'))is int})
   if not members:decision='Сумма резерва '+str(c['budget_reserve_amount'])+' ¥; состав РК не подтверждён.'
   else:
    decision='Пополнить на '+str(c['budget_reserve_amount'])+' ¥\nЗапас на 3 дня по среднему расходу.'
    c['budget_action']=dict(id='topup:'+str(c['id']),kind='topup_campaign',campaign_id=c['id'],amount_cny=c['budget_reserve_amount'],balance_before=float(balance),target_balance=float(balance+amount),status_before=9,nm_ids=members,basis=POLICY)
  c['budget_short_note']=decision;c['budget_recommendation']=decision
 return out
