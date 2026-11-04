"""Private pricing evidence. Collection only; no marketplace or Telegram writes."""
import copy
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo('Europe/Moscow')

def valid_daily_orders(row, size):
    values = row.get('sparkline_orders')
    return (isinstance(values, list) and len(values) == size
            and all(type(v) in (int, float) and math.isfinite(v) and v >= 0 and int(v) == v for v in values)
            and type(row.get('orders_count')) in (int, float)
            and sum(values) == row['orders_count'])

def cached_order_products(get, start, end, wanted):
    """Only exact, complete, post-close, seller-verified WB receipts; no synthetic zeros."""
    from china_agent.wb_order_gaps import counts
    daily = []; refs = []; observed = []
    for i in range((end-start).days+1):
        day = start+timedelta(days=i)
        key = 'china_agent:wb_order_gaps:day:'+str(day)
        value = get(key) or {}
        try:
            stamp = datetime.fromisoformat(value['observed_at'].replace('Z', '+00:00'))
            if (value.get('cabinet') != 'token_3' or value.get('status') != 'complete'
                    or value.get('seller_identity_verified') is not True or value.get('date') != str(day)
                    or value.get('scope') != 'flag=1 exact Moscow day' or stamp.tzinfo is None
                    or stamp < datetime.combine(day+timedelta(days=1), datetime.min.time(), MSK)):
                return {}
            daily.append(counts(value['rows'], day, wanted))
        except (KeyError, TypeError, ValueError, OverflowError):
            return {}
        refs.append(key); observed.append(stamp.isoformat())
    result = {}
    for nm, article in wanted.items():
        active = [d[nm]['orders'] for d in daily]
        cancelled = [d[nm]['cancelled'] for d in daily]
        result[nm] = dict(nm_id=nm, article=article, status='complete',
            source='WB Statistics API / verified cached daily orders',
            period_from=str(start), period_to=str(end), observed_at=max(observed),
            orders_each_day=active, orders=sum(active), cancelled_orders=sum(cancelled),
            all_orders_each_day=[a+c for a,c in zip(active,cancelled)],
            all_orders=sum(active)+sum(cancelled), source_keys=refs,
            financial_data_complete=False, limitation='Created noncancelled orders, not buyouts or profit')
    return result

FINANCE_FIELDS = ('nm_id','sa_name','orders_count','orders_sum','sales_count','returns_count',
    'sales_sum','returns_sum','for_pay','cost_price','sales_cost','returns_cost','profit',
    'advertisement','advertisement_expenses_in_orders','logistic_all','taxes','penalty',
    'deduction','storage_fee','acquiring','acceptance','finished_orders','not_finished_orders')

def price_evidence(worker):
    """Pass acquisition facts to analysis, independently of text formatting/candidate count."""
    marker = getattr(worker, '_price_completed_marker', None) or {}
    evidence = dict(status='unavailable', cabinet='token_3', financial_currency='RUB',
        financial_basis='MPStats reported completed-period sales/returns/costs, not a settled order cohort',
        settled_cohort_profit_status='unavailable',
        limitation='Current created orders, attributed advertising orders and completed-period sales are different cohorts. Unknown costs are not zero.',
        source_snapshot_id=marker.get('id'), financial_rows=[],
        assessment=copy.deepcopy(worker.audit.get('assessment')),
        order_coverage=copy.deepcopy(worker.audit.get('order_coverage')))
    if not marker.get('id'):
        evidence['blocker']='Completed source marker unavailable'
        return evidence
    snapshots = worker.db('GET','analytics_snapshots',params=dict(id='eq.'+str(marker['id']),
        cabinet='eq.token_3',status='eq.complete',select='id,cabinet,period_from,period_to,collected_at,payload',limit=1)) or []
    if len(snapshots) != 1:
        evidence['blocker']='Completed source receipt unavailable'
        return evidence
    source = snapshots[0]
    end = worker.day-timedelta(days=1); start=end-timedelta(days=3)
    try:
        stamp=datetime.fromisoformat(source['collected_at'].replace('Z','+00:00'))
        if (source.get('cabinet')!='token_3' or str(source['period_from'])!=str(start)
                or str(source['period_to'])!=str(end) or stamp.tzinfo is None
                or stamp < datetime.combine(end+timedelta(days=1),datetime.min.time(),MSK)):
            raise ValueError('Completed source scope mismatch')
        body=source['payload']
        if isinstance(body,list) and len(body)==1: body=body[0]
        # Both raw MCP observations and nested response envelopes are supported.
        for _ in range(6):
            if isinstance(body,dict) and isinstance(body.get('data'),list):
                raw=body['data']; break
            if isinstance(body,dict) and isinstance(body.get('data'),dict):body=body['data']
            else:raise ValueError('Financial rows missing in completed source')
        else:raise ValueError('Financial source nesting unsupported')
        if not raw or any(not isinstance(r,dict) or r.get('nm_id') is None for r in raw):
            raise ValueError('Financial row identities unavailable')
        evidence.update(status='reported_period_available', period_from=str(start), period_to=str(end),
            observed_at=source['collected_at'], financial_rows=[{k:r[k] for k in FINANCE_FIELDS if k in r} for r in raw])
        # Missing individual costs remain absent, never fabricated as zero.
    except (KeyError,TypeError,ValueError) as exc:
        evidence['blocker']=str(exc)
    return evidence

