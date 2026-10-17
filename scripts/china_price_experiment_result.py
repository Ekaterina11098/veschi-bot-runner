"""Explain observed China price-test results without claiming price causality."""
from math import comb

def conversion_test(before_views,before_orders,after_views,after_orders):
 values=(before_views,before_orders,after_views,after_orders)
 if any(type(v) is not int or v<0 for v in values):return None
 if before_views==0 or after_views==0 or before_orders>before_views or after_orders>after_views:return None
 # Fisher's exact two-sided test, conditional on observed margins.
 a,b,c,d=before_orders,before_views-before_orders,after_orders,after_views-after_orders
 population=a+b+c+d;successes=a+c;draws=a+b
 denominator=comb(population,draws)
 def probability(k):return comb(successes,k)*comb(population-successes,draws-k)/denominator
 low=max(0,draws-(population-successes));high=min(successes,draws)
 observed=probability(a)
 return min(1,sum(probability(k) for k in range(low,high+1) if probability(k)<=observed*(1+1e-10)))

def experiment_result(before_profit,after_profit,before_views,before_orders,after_views,after_orders,full_days,buyout_sample,missing=()):
 delta=None if before_profit is None or after_profit is None else round(after_profit-before_profit,2)
 # A percentage increase across a zero/negative baseline is misleading.
 percent=round(delta/before_profit*100,2) if delta is not None and before_profit>0 else None
 result=dict(profit_delta_rub=delta,profit_delta_percent=percent,execution_authorized=False)
 if missing or delta is None:
  result.update(status='incomplete',result_action='Расчёт ожидаемой прибыли не завершён: '+('; '.join(missing) if missing else 'не подтверждены все входные данные')+'. Вывод об успешности не сформирован.')
  return result
 p=conversion_test(before_views,before_orders,after_views,after_orders)
 result['conversion_fisher_p']=p
 if p is None or before_orders+after_orders==0 or not buyout_sample:
  text='Недостаточно наблюдений для решения — продолжаем сбор данных.';status='insufficient_observations'
 else:
  decline=after_orders/after_views<before_orders/before_views
  strong=decline and p<.05
  if strong and delta<0:
   text='Ожидаемая прибыль и конверсия снизились — внимательно наблюдаем; '+('проверяем связку и рассматриваем возврат прежней цены.' if full_days>=4 else 'решение о возврате после четырёх полных дней и проверки связки.')
   status='rollback_review' if full_days>=4 else 'watch_decline'
  elif delta>0 and decline:
   text='Ожидаемая прибыль выросла, конверсия снизилась — результат смешанный, внимательно наблюдаем.';status='mixed'
  elif delta>0:
   text='После повышения ожидаемая прибыль выросла — продолжаем эксперимент.';status='positive'
  elif delta<0:
   text='Ожидаемая прибыль снизилась — проверяем число заказов, трафик и расходы; причина пока не установлена.';status='investigate'
  else:
   text='Рост ожидаемой прибыли не подтверждён — продолжаем наблюдение.';status='observe'
 if full_days<4:text+=' Промежуточно: '+str(full_days)+' из 4 полных дней.'
 if buyout_sample and buyout_sample<10:text+=' Процент выкупа основан на '+str(buyout_sample)+' завершённых заказах; оценка неустойчива.'
 result.update(status=status,result_action=text)
 return result
