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
