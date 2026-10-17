"""Order-date realized contribution. Pending forecasts and shared charges stay separate."""
from decimal import Decimal
from datetime import date

def number(row,key):
 value=row.get(key)
 if isinstance(value,bool) or not isinstance(value,(int,float,Decimal)):raise ValueError('Missing '+key)
 value=Decimal(str(value))
 if not value.is_finite():raise ValueError('Invalid '+key)
 return value

def cohort(rows,nm,article,day,cost):
 seen={};out=dict(orders=0,cancelled=0,buyouts=0,returns=0,pending=0,realized_contribution=Decimal(0),unresolved=[])
 for r in rows:
  if str(r.get('nm_id'))!=str(nm) or r.get('api_id')!=10026946 or str(r.get('sa_name','')).casefold()!=article.casefold():raise ValueError('Order cabinet/product identity mismatch')
  identity=str(r.get('srid') or r.get('gnumber') or '')
  if not identity:raise ValueError('Order identity missing')
  if identity in seen:
   if seen[identity]!=r:raise ValueError('Conflicting duplicate order')
   continue
  seen[identity]=r
  if str(r.get('order_dt',''))[:10]!=day:continue
  cancelled=r.get('is_canceled_order')
  if cancelled not in (0,1,False,True):raise ValueError('Cancellation unknown')
  out['cancelled']+=int(cancelled)
  out['orders']+=int(not cancelled)
  billed=number(r,'billed_times');refunded=number(r,'refunded_times')
  if any(v<0 or v!=int(v) for v in (billed,refunded)) or refunded>billed:raise ValueError('Unreconciled settlement units')
  out['buyouts']+=int(billed);out['returns']+=int(refunded)
  if billed==0 and refunded==0:
   if not cancelled:out['pending']+=1
   # Pending order_for_pay/profit/logistics rates are not realized cash.
   out['unresolved'].append(dict(order_id=identity,reason='pending' if not cancelled else 'cancelled_costs_not_reconciled'))
   continue
  if not r.get('sale_date') and not r.get('sale_dt'):raise ValueError('Paid order without sale date')
  if refunded and not r.get('refund_dt'):raise ValueError('Return date missing')
  cash=number(r,'billedmoney')-number(r,'refundedmoney')-number(r,'comission')-number(r,'forward_logistic_rub')-number(r,'backward_logistic_rub')
  own=Decimal(str(cost)) if cost is not None else None
  if own is None or not own.is_finite() or own<0:raise ValueError('Own cost missing')
  out['realized_contribution']+=cash-(billed-refunded)*own
 out['realized_contribution']=float(out['realized_contribution'].quantize(Decimal('.01')))
 out['finalized']=not out['unresolved']
 out['basis']='actual order-linked buyout contribution before advertising/shared charges; not final net profit'
 return out
