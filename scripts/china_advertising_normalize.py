"""Validate exact China dates/scope and build the approved two PNG views."""
import math
from datetime import date,timedelta
def number(v):
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:raise ValueError('Missing or invalid advertising amount')
 return v
def normalize(p,day,articles):
 if p.get('status')!='complete' or p.get('cabinet')!='token_3' or p.get('identity',{}).get('id')!=939742 or p['identity'].get('info',{}).get('currency')!='CNY':
  raise ValueError('China source identity or currency unverified')
 end=str(date.fromisoformat(day)-timedelta(days=1));start=str(date.fromisoformat(end)-timedelta(days=6));obs=p['observations']
 def one(tool,predicate):
  found=[x for x in obs if x.get('tool')==tool and predicate(x['arguments'])]
  if len(found)!=1 or found[0].get('status')!='received' or found[0].get('scope_verified') is not True:raise ValueError('Source incomplete or ambiguous')
  return found[0]
 state=one('wbbidder_campaigns',lambda a:a['report']=='state')
 daily=one('wbbidder_campaigns',lambda a:a['report']=='stats' and a.get('d1')==end and a.get('d2')==end)
 weekly=one('wbbidder_campaigns',lambda a:a['report']=='stats' and a.get('d1')==start and a.get('d2')==end)
 for x in (state,daily,weekly):
  if x['arguments']['tokens']!=[939742] or x['data'].get('total')!=len(x['data']['data']) or x['data'].get('returned')!=len(x['data']['data']):raise ValueError('Incomplete catalogue pagination')
 for x,a,b in [(daily,end,end),(weekly,start,end)]:
  if x['data'].get('period')!={'from':a,'to':b}:raise ValueError('Reporting dates changed')
 byday={x['id']:x for x in daily['data']['data']};byweek={x['id']:x for x in weekly['data']['data']}
 catalog=state['data']['data']
 if len({x['id'] for x in catalog})!=len(catalog):raise ValueError('Duplicate campaigns')
 if {x['id'] for x in catalog}!=set(byday) or set(byday)!=set(byweek):raise ValueError('Catalogue scope mismatch')
 result=dict(period=end,week_from=start,week_to=end,observed_day=day,currency='CNY',campaigns=[],checks=[])
 for c in catalog:
  cid=c['id'];d=byday[cid];w=byweek[cid]
  conf=one('wbbidder_campaign',lambda a:a['campaign_id']==cid)
  days=one('wbbidder_campaign_stats',lambda a:a['campaign_id']==cid and a['report']=='days' and a.get('d1')==start and a.get('d2')==end)
  prod=one('wbbidder_campaign_stats',lambda a:a['campaign_id']==cid and a['report']=='products' and a.get('d1')==end and a.get('d2')==end)
  if conf['data'].get('campaign',{}).get('wb_id')!=c['wb_id'] or (conf['data'].get('budget') or {}).get('currency') not in (None,'CNY'):raise ValueError('Campaign currency/identity unverified')
  for item,a,b in [(days,start,end),(prod,end,end)]:
   if item['data'].get('period')!={'from':a,'to':b}:raise ValueError('Campaign reporting period changed')
   if len(item['data'].get('data',[]))!=item['data'].get('returned'):raise ValueError('Campaign rows incomplete')
  data=prod['data']['data'];risk=[];no_orders=[]
  if len({s['nm_id'] for s in data})!=len(data):raise ValueError('Duplicate product rows')
  for r in data:
   spend=number(r.get('ac_spending_sum'));revenue=number(r.get('ac_orders_sum'));orders=number(r.get('ac_orders'))
   if (orders==0)!=(revenue==0):raise ValueError('Product orders and turnover inconsistent')
   label=articles.get(str(r['nm_id']),'WB '+str(r['nm_id']))
   if revenue>0:
    ratio=100*spend/revenue
    if ratio>5:risk.append(dict(article=label,nm=r['nm_id'],drr=ratio,spend=spend,orders=number(r.get('ac_orders')),orders_sum=revenue))
   elif spend>0:no_orders.append(dict(article=label,nm=r['nm_id'],spend=spend))
  spend=number(d.get('ac_spending_sum'));week=number(w.get('ac_spending_sum'));revenue=number(d.get('ac_orders_sum'));budget_value=(conf['data'].get('budget') or {}).get('budget');balance=number(budget_value) if budget_value is not None else None
  new=c['create_date'][:10]>end
  day_rows=[x for x in days['data']['data'] if x['date']==end]
  day_row_spend=number(day_rows[0]['ac_spending_sum']) if len(day_rows)==1 else None
  summary_product_spend=(prod['data'].get('totals') or {}).get('ac_spending_sum')
  if spend>0 and summary_product_spend!=spend:raise ValueError('Campaign product totals do not reconcile')
  result['campaigns'].append(dict(id=cid,wb_id=c['wb_id'],name=c['campaign_name'],status=c['status_id'],is_new=new,created=c['create_date'],
   spend=spend,weekly_spend=week,orders_sum=revenue,orders=number(d.get('ac_orders')),drr=100*spend/revenue if revenue>0 else None,
   source_drr=d.get('ac_share_of_advert_spend'),postclick_orders=d.get('ac_orders_associated'),postclick_orders_sum=d.get('ac_orders_sum_associated'),
   above5=sorted(risk,key=lambda x:x['drr'],reverse=True),no_orders=sorted(no_orders,key=lambda x:x['spend'],reverse=True),
   balance=balance,balance_observed=conf['observed_at'],balance_hours=balance/spend*24 if balance is not None and not new and c['status_id']==9 and spend>0 else None,
   sku_rows=len(data),sku_with_orders_count=sum(number(x.get('ac_orders'))>0 for x in data),sku_spend_sum=sum(number(x.get('ac_spending_sum')) for x in data),
   day_match=day_row_spend==spend,day_row_spend=day_row_spend,weekly_sum_day_rows=sum(number(x['ac_spending_sum']) for x in days['data']['data'])))
 result['total_day']=sum(x['spend'] for x in result['campaigns']);result['total_week']=sum(x['weekly_spend'] for x in result['campaigns'])
 return result
