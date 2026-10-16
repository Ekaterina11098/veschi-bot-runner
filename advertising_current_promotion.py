"""Current promotion epoch guard; historical evidence never becomes a new launch result."""
import copy
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
def guard(report,configuration):
    out=copy.deepcopy(report)
    config=configuration.get('payload') or {}
    advert=next((x for x in config.get('adverts',[]) if x.get('id')==40223879),None)
    if not advert:return out
    stamp=(advert.get('timestamps') or {}).get('started')
    try:
        start=datetime.fromisoformat(stamp.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow'))
        first_full=(start.date()+timedelta(days=1)).isoformat()
    except (ValueError,TypeError,AttributeError):return out
    for c in out.get('campaigns',[]):
        if c.get('wb_campaign_id')!=40223879:continue
        c['current_promotion']=dict(started_at=stamp,configuration_snapshot_id=configuration.get('id'),
            first_full_day=first_full,period_from=out.get('period_from'),period_to=out.get('period_to'),
            current_promotion_metrics_verified=bool(out.get('period_from') and out['period_from']>=first_full),
            initial_partial_day_requires_intraday_scope=True)
        if c['current_promotion']['current_promotion_metrics_verified']:continue
        c['historical_advertising_totals']=copy.deepcopy(c.get('totals'))
        c['totals']={};c['spending_reconciled']=False;c['sku_order_basis']='unverified'
        c['product_report_source']='Historical campaign period; not verified current promotion'
        for p in c.get('products',[]):
            p['historical_advertising']=copy.deepcopy(p.get('advertising'))
            p['advertising']=dict(nm_id=p.get('nm_id'),advertising_status='current_promotion_period_unverified')
            p['current_promotion']=copy.deepcopy(c['current_promotion'])
    out['current_promotion_epoch_checked']=True
    return out
def install():
    import analytics.ip_daily_recommendations as daily
    from analytics.stage_one import read
    original=daily.build
    if getattr(original,'_epoch_guard',False):return
    def build(report,*a,**kw):
        rows=read('analytics_snapshots',dict(source='eq.advertising_active_configuration',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1)) or []
        return original(guard(report,rows[0]) if rows else report,*a,**kw)
    build._epoch_guard=True
    daily.build=build
