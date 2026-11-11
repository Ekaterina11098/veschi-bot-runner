"""Do not turn the owner's no-automatic-reduction rule into a veto on ready +5% repeats."""
import re
from datetime import timedelta
from decimal import Decimal,InvalidOperation
def protected_repeats(worker,rows):
 state=worker.get('china_agent:demand_watch:v1')or{};latest=state.get('latest')or{}
 end=worker.day-timedelta(days=1);start=end-timedelta(days=3)
 if latest.get('data_available')is not True or latest.get('period_from')!=str(start)or latest.get('period_to')!=str(end):return set()
 by_article={r.get('article'):(nm,r)for nm,r in latest.get('results',{}).items()}
 result=set()
 for key,line in rows.items():
  m=re.match(r'^Повышение · (.+?) Продавец: ([0-9.,]+) → ([0-9.,]+) [¥￥]',line)
  if not m or m[1]not in by_article:continue
  nm,r=by_article[m[1]]
  if str(nm)in('1473245494','1473245510')or r.get('action')!='raise'or r.get('raise_kind')!='repeat'or r.get('orders_stable')is not True or r.get('conversion_held')is not True or r.get('full_days',0)<4:continue
  days=r.get('orders_each_day');p=state.get('price_history',{}).get(nm,{}).get('price',{})
  if not isinstance(days,list)or len(days)!=4 or any(type(n)is not int or n<1 for n in days):continue
  try:
   old=Decimal(m[2].replace(',','.'));new=Decimal(m[3].replace(',','.'))
   if old<=0 or new<=old or old!=Decimal(str(p['current_cny']))or new!=Decimal(str(p['target_cny'])):continue
  except(KeyError,InvalidOperation):continue
  result.add(key)
 return result

