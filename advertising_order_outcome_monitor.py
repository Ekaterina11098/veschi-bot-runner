"""Read-only bounded observation of known SKU order dates; no financial maturity inference."""
from datetime import datetime,timedelta,timezone
import copy,hashlib,json
KEY='advertising:ip:order_outcome_monitor:v1'
PRODUCTS={'139147637':1123677454,'124391695':320248210}
def dt(s):
 if not s:return None
 v=datetime.fromisoformat(str(s).replace('Z','+00:00'))
 return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
def status(x):
 if x.get('refund_dt') or (x.get('refunded_times') or 0)>0:return 'returned'
 if x.get('is_canceled_order')==1:return 'cancelled'
 if not x.get('billed_times') and (x.get('backlogistic_times') or 0)>0:return 'nonbuyout_reverse'
 if x.get('sale_dt') and (x.get('billed_times') or 0)>0:return 'buyout'
 return 'unresolved'
FIELDS=('sale_dt','refund_dt','billed_times','refunded_times','is_canceled_order','backlogistic_times','forward_logistic_rub','backward_logistic_rub','confirmed','full_commission','profit','order_profit')
def ingest(state,obs,snapshot_id):
 if obs.get('tool')!='lk_wb_card_orders' or obs.get('status')!='received' or obs.get('scope_verified') is not True:return state
 args=obs['arguments'];pid=str(args.get('value'));body=obs.get('data') or {};rows=body.get('data')
 if pid not in PRODUCTS or args.get('type')!='products':raise ValueError('Unapproved order product')
 if not isinstance(rows,list) or body.get('total')!=len(rows) or args.get('start_row',0)!=0:raise ValueError('Order page incomplete; do not overwrite known observations')
 f=body.get('filterModel') or {}
 if f.get('product_id',{}).get('filter')!=int(pid) or f.get('order_dt',{}).get('dateFrom')!=args['date_from'] or f.get('order_dt',{}).get('dateTo')!=args['date_to']:raise ValueError('Order filter unverified')
 ids=[str(x.get('gnumber') or '') for x in rows]
 if '' in ids or len(ids)!=len(set(ids)):raise ValueError('Order identity duplicate')
 result=copy.deepcopy(state or {'version':1,'orders':{},'history':[]})
 result.setdefault('history',[]);result.setdefault('version',1)
 orders=result.setdefault('orders',{});observed=dt(obs['observed_at'])
 old_scope=[gn for gn,x in orders.items() if x['product_id']==pid and args['date_from']<=x['ordered_on']<=args['date_to']]
 if set(old_scope)-set(ids):raise ValueError('Previously known order omitted; retain previous history')
 for row in rows:
  if row.get('nm_id')!=PRODUCTS[pid] or not args['date_from']<=row['order_dt'][:10]<=args['date_to']:raise ValueError('Order scope mismatch')
  gn=str(row['gnumber']);old=orders.get(gn)
  fingerprint=hashlib.sha256(json.dumps({k:row.get(k) for k in FIELDS},sort_keys=True).encode()).hexdigest()
  if old and dt(old['observed_at'])>=observed:continue
  changed=not old or old['fingerprint']!=fingerprint
  changed_at=observed.isoformat() if changed else old['last_changed_at']
  kind=status(row);sale=dt(row.get('sale_dt'))
  stable=(observed-dt(changed_at)).total_seconds()/86400
  # This controls polling only. It never sets finality, settled cost or a mature buyout ratio.
  archived=stable>=14 and ((kind=='buyout' and sale and (observed-sale).days>=30) or (kind in ('returned','cancelled','nonbuyout_reverse') and row.get('confirmed')==1 and (row.get('forward_logistic_rub') or 0)+(row.get('backward_logistic_rub') or 0)>0))
  interval=7 if kind=='unresolved' and (observed-dt(row['order_dt'])).days>=30 else 1
  value=dict(product_id=pid,nm_id=PRODUCTS[pid],gnumber=gn,ordered_on=row['order_dt'][:10],observed_at=observed.isoformat(),last_changed_at=changed_at,
   fingerprint=fingerprint,status=kind,raw=row,snapshot_id=snapshot_id,active=not archived,
   monitoring_state='stable_observation_archived_not_financially_final' if archived else 'weekly_unresolved' if interval==7 else 'daily',
   next_check_at=None if archived else (observed+timedelta(days=interval)).isoformat(),financially_final=False,mature_retention_ratio=None)
  orders[gn]=value
  result['history'].append(dict(gnumber=gn,snapshot_id=snapshot_id,observed_at=observed.isoformat(),changed=changed,status=kind,fingerprint=fingerprint))
 return result
def seed(state,memory):
 result=state
 for snapshot in (memory.get('outcome_refresh_20261016') or {}).get('saved',[]):
  result=ingest(result,snapshot['payload'][0],snapshot['id'])
 return result or {'version':1,'orders':{},'history':[]}
def financial_revision(state,obs,now):
 if obs.get('tool')!='lk_wb_products' or obs.get('status')!='received':return state
 body=(obs.get('data') or {}).get('data') or {}
 if body.get('need_update')!=0 or body.get('total')!=len(body.get('data') or []):return state
 result=copy.deepcopy(state);versions=result.setdefault('financial_versions',{})
 day=obs['arguments'].get('date_from')
 for row in body.get('data') or []:
  nm=str(row.get('nm_id') or row.get('nmId') or '')
  if nm not in {str(v) for v in PRODUCTS.values()}:continue
  key=day+':'+nm;value=hashlib.sha256(json.dumps({k:row.get(k) for k in ('logistic_all','advertisement','for_pay','storage_fee','deduction','penalty')},sort_keys=True).encode()).hexdigest()
  previous=versions.get(key);versions[key]=value
  if previous is None or previous==value:continue
  for order in result.get('orders',{}).values():
   if str(order['nm_id'])==nm:
    order.update(active=True,next_check_at=now.isoformat(),monitoring_state='reopened_financial_revision',financially_final=False)
 return result
def plan(state,now,max_requests=4,incident_order_ids=()):
 due={}
 for gn,x in (state or {}).get('orders',{}).items():
  incident=gn in incident_order_ids
  if not incident and (not x.get('active') or dt(x['next_check_at'])>now):continue
  ident=(x['product_id'],x['ordered_on'])
  score=dt(x['observed_at'])
  due[ident]=min(due.get(ident,score),score)
 spans=[]
 for (pid,day),stamp in sorted(due.items()):
  if spans and spans[-1][0]==pid and (dt(day)-dt(spans[-1][2])).days==1 and (dt(day)-dt(spans[-1][1])).days<7:
   spans[-1][2]=day;spans[-1][3]=min(stamp,spans[-1][3])
  else:spans.append([pid,day,day,stamp])
 result=[]
 for pid,first,last,stamp in sorted(spans,key=lambda v:(v[3],v[0],v[1]))[:max_requests]:
  args=dict(type='products',value=pid,date_from=first,date_to=last,start_row=0,end_row=300)
  result.append(dict(key='order-outcome:'+pid+':'+first+':'+last+':'+now.date().isoformat(),cabinet='token_2',tool='lk_wb_card_orders',arguments=args,priority=100))
 return result
