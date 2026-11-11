"""Exact closed-period linked-card totals; never invent absent members or daily series."""
import math
def repair(context,datasets,markers,costs):
 if context.get('status')!='incomplete' or not context.get('baseline_membership_known') or context.get('membership_changed'):return context
 from advertising_agent.mpstats_economics import calculate
 from datetime import date
 members=context['membership']['members'];values={};refs=[]
 for label,start,end in [('before',context['baseline_from'],context['baseline_to']),('after',context['period_from'],context['period_to'])]:
  marker=markers.get((start,end));rows=datasets.get((start,end),{})
  if not marker or any(nm not in rows for nm in members):return context
  counts=[rows[nm].get('sales_count')for nm in members]
  if any(type(v)not in(int,float)or not math.isfinite(v)or v<0 or int(v)!=v for v in counts):return context
  try:
   obs,=marker['payload']
   economics=calculate(obs,costs,start,end,tax_rate=0)
  except (KeyError,TypeError,ValueError):return context
  amounts=[]
  for nm in members:
   e=economics.get(int(nm),{})
   if e.get('finance_complete')is not True or e.get('economics_status')!='complete':return context
   amount=e.get('net_profit')
   if type(amount)not in(int,float)or not math.isfinite(amount):return context
   amounts.append(amount)
  days=(date.fromisoformat(end)-date.fromisoformat(start)).days+1
  values[label]=dict(sales=sum(counts),profit=sum(amounts),days=days)
  refs.append(dict(id=marker['id'],period_from=start,period_to=end))
 before,after=values['before'],values['after']
 growing=after['sales']/after['days']>before['sales']/before['days'] or after['profit']/after['days']>before['profit']/before['days']
 return dict(context,status='growing'if growing else'not_growing',reason='Сопоставлены средние в день по точным завершённым периодам и всем карточкам связки.',sales_before=before['sales'],sales_after=after['sales'],profit_before=before['profit'],profit_after=after['profit'],profit_basis='mpstats_rub_own_costs_exact_period',comparison_basis='per_completed_day',period_sources=refs,daily_series_available=False)
