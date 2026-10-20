"""Expected order-date profit; scenario costs are mandatory and never zero-filled."""
from decimal import Decimal

def dec(value):
 if value is None or isinstance(value,bool):raise ValueError('Expected-profit input missing')
 v=Decimal(str(value))
 if not v.is_finite():raise ValueError('Expected-profit input invalid')
 return v

def buyout_probability(paid_kept,finished,reported_percent=None):
 paid,completed=dec(paid_kept),dec(finished)
 if completed<=0: return None
 if any(v<0 or v!=int(v) for v in (paid,completed)) or paid>completed:raise ValueError('Buyout sample invalid')
 rate=paid/completed
 if reported_percent is not None and abs(rate*100-dec(reported_percent))>Decimal('.011'):raise ValueError('Buyout percentage does not reconcile')
 return rate

def expected_profit(orders,probability,advertising,shared_costs):
 """Each order supplies net profit in each outcome, with documented cost inclusion.

 buyout_profit and nonbuyout_profit include all applicable unit costs, logistics,
 commission and tax. Source payout already net of a fee must not lose that fee twice.
 Period advertising/shared costs occur regardless of buyout and are subtracted once.
 """
 p=dec(probability)
 if not 0<=p<=1:raise ValueError('Buyout probability outside 0..1')
 value=Decimal(0);seen=set()
 for row in orders:
  identity=row['order_id']
  if identity in seen:raise ValueError('Duplicate order')
  seen.add(identity)
  value+=p*dec(row['buyout_profit'])+(1-p)*dec(row['nonbuyout_profit'])
 value-=dec(advertising)+dec(shared_costs)
 return dict(expected_profit=float(value.quantize(Decimal('.01'))),buyout_percent=float(p*100),basis='order_date',label='Ожидаемая прибыль, скорректированная на текущий % выкупа артикула',is_actual=False)

def resolved_buyout_rate(paid_kept,finished,reported_percent=None):
 """Use every available settled sample, including small samples and true 0%."""
 if paid_kept is None and finished is None:
  return dict(probability=Decimal('.5'),percent=50,source='fallback',sample_size=0,
   note='50% — принято для расчёта: собственной завершённой статистики нет')
 if paid_kept is None or finished is None:raise ValueError('Buyout counters incomplete')
 paid,completed=dec(paid_kept),dec(finished)
 if completed==0:
  if paid!=0:raise ValueError('Paid orders without completed sample')
  return resolved_buyout_rate(None,None)
 probability=buyout_probability(paid,completed,reported_percent)
 if probability is None:raise ValueError('Invalid completed sample')
 return dict(probability=probability,percent=float(probability*100),source='own_article',sample_size=int(completed),
  note='Фактический выкуп артикула по завершённым заказам с учётом возвратов')

def buyout_from_product(row):
 """Product is_payed already excludes returns; do not subtract finish_as_return twice."""
 if row is None:raise ValueError('Product buyout source missing')
 paid,returned,finished=(row.get(k) for k in ('is_payed','finish_as_return','finished_orders'))
 if all(v is None for v in (paid,returned,finished)):return resolved_buyout_rate(None,None)
 if any(v is None for v in (paid,returned,finished)):raise ValueError('Product buyout counters incomplete')
 paid,returned,finished=map(dec,(paid,returned,finished))
 if any(v<0 or v!=int(v) for v in (paid,returned,finished)) or paid+returned>finished:
  raise ValueError('Product settled counters invalid')
 return resolved_buyout_rate(paid,finished,row.get('is_payed_percent_after_returns'))
