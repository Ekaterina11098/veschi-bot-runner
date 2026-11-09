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
        # This fallback does not validate any SKU's funnel. The consumer must
        # reconcile that SKU's daily view length and sum before using conversion.
        return rows,dict(record,per_product_period_validation_required=True)
    except (KeyError,TypeError,ValueError):return [],None

