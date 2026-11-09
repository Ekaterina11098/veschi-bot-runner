"""Exact raw product-period fallback; one bad product cannot erase valid peers."""
from datetime import datetime,date,timedelta,timezone

def period(worker,start,end):
    from analytics.mpstats_primary import products
    from china_agent.daily_report_worker import MSK
    read=lambda t,p:worker.db('GET',t,params=p)
    rows,marker=products(read,'token_3',str(start),str(end),datetime.now(timezone.utc))
    if marker:return rows,marker
    records=read('analytics_snapshots',dict(cabinet='eq.token_3',source='eq.mpstats_lk_wb_products',status='eq.complete',period_from='eq.'+str(start),period_to='eq.'+str(end),select='id,payload,collected_at,period_from,period_to',order='id.desc',limit=1)) or []
    if len(records)!=1:return [],None
    record=records[0]
    try:
        obs,=record['payload'];args=obs['arguments'];body=obs['data']['data'];rows=body['data']
        closed=datetime.combine(date.fromisoformat(str(end))+timedelta(days=1),datetime.min.time(),MSK)
        collected=datetime.fromisoformat(record['collected_at'].replace('Z','+00:00'))
        if (obs.get('scope_verified')is not True or obs.get('status')!='received' or obs.get('tool')!='lk_wb_products'
            or args.get('date_from')!=str(start) or args.get('date_to')!=str(end) or args.get('start_row')!=0
            or body.get('need_update')!=0 or type(body.get('total'))is not int or body['total']!=len(rows) or args.get('end_row',0)<len(rows)
            or len({r['p_id'] for r in rows})!=len(rows) or collected<closed):return [],None
        # Current lk_wb_products contract (read back 9Nov) returns period totals
        # without sparklines. Exact requested bounds, verified cabinet, closed-day
        # collection and complete pagination establish the reporting period.
        return rows,dict(record,per_product_period_validation_required=True,
                         date_basis='lk_wb_products explicit date_from/date_to contract',
                         source_contract_key='china_agent:owner_price_delivery_recovery:2026-11-09:v1:source_contract')
    except (KeyError,TypeError,ValueError):return [],None

def conversion(read,nm,start,end):
    from types import SimpleNamespace
    worker=SimpleNamespace(db=lambda method,table,params=None:read(table,params))
    rows,marker=period(worker,str(start),str(end))
    if not marker:return None,False
    matches=[r for r in rows if str(r.get('nm_id'))==str(nm)]
    if len(matches)!=1:return None,True
    row=matches[0];views=row.get('open_card_count');orders=row.get('funnel_orders_count')
    if type(views)not in(int,float)or type(orders)not in(int,float)or views<=0 or not 0<=orders<=views:return None,True
    return orders/views,True

def install(root):
    from pathlib import Path
    path=Path(root)/'china_agent/price_sources.py'
    if not path.exists():return
    text=path.read_text(encoding='utf8')
    marker='    # current_mpstats_period_totals_contract_v1\n'
    if marker in text:return
    lines=text.splitlines(keepends=True)
    at=next((i for i,line in enumerate(lines) if line.startswith('def period_conversion(')),None)
    if at is None:raise RuntimeError('Price conversion source hook changed')
    lines.insert(at+1,marker+'    from china_price_period import conversion as exact_conversion\n    value, verified = exact_conversion(read, key, start, end)\n    if verified:return value\n')
    path.write_text(''.join(lines),encoding='utf8')

