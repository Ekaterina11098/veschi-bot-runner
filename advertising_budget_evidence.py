"""Dated budget evidence for recommendations only; no collection or execution."""
import math
from datetime import datetime,timezone
def budget_analysis(report,now):
    snapshots=report.get('budgets') or []
    found={}
    for snapshot in sorted(snapshots,key=lambda s:s.get('collected_at') or '',reverse=True):
        payload=snapshot.get('payload') or {}
        if isinstance(payload,list):
            payload=next((x for x in payload if isinstance(x,dict) and 'items' in x),{})
        for row in payload.get('items',[]):
            cid=row.get('campaign_id')
            if type(cid) is not int or cid in found:continue
            total=row.get('total');stamp=row.get('observed_at')
            known=((row.get('available') is True or row.get('stale') is True) and not row.get('error') and type(total) in (int,float) and math.isfinite(total) and total>=0)
            try:age=(now-datetime.fromisoformat(stamp.replace('Z','+00:00'))).total_seconds()
            except (ValueError,TypeError,AttributeError):age=None
            if known and age is not None and age>=0:
                found[cid]=dict(balance=total,balance_observed_at=stamp,balance_snapshot_id=snapshot.get('id'),
                    balance_is_current=age<21600,balance_status='observed_recent' if age<21600 else 'historical',
                    balance_age_seconds=round(age))
    result=[]
    for c in report.get('campaigns',[]):
        if c.get('active_catalog_verified') is not True:continue
        cid=c['wb_campaign_id']
        evidence=found.get(cid) or dict(balance=None,balance_observed_at=None,balance_snapshot_id=None,
            balance_is_current=False,balance_status='unknown',balance_age_seconds=None)
        result.append(dict(campaign_id=cid,**evidence,current_spend_per_hour=None,forecast_hours=None,
            effectiveness_verified=False,automatic_topup=False))
    return result
def install():
    import analytics.ip_daily_recommendations as daily
    daily.budget_analysis=budget_analysis

def compact_report(daily,now,include_budget_scenario=False):
    """Pure saved-data view; unknown pairs never count as normal, no source calls."""
    from datetime import date
    review=daily.get('campaign_review') or {}
    rows=review.get('rows') or []
    ids=sorted({r['campaign_id'] for r in rows})
    budgets={x['campaign_id']:x for x in daily.get('budget_analysis') or []}
    start=daily.get('period_from');end=daily.get('period_to')
    duration=(date.fromisoformat(end)-date.fromisoformat(start)).days+1 if start and end else 0
    parts=[];details=[]
    def known(x):return type(x) in (int,float) and math.isfinite(x) and x>=0
    def fmt(x):return format(x,'.2f').replace('.',',')
    for cid in ids:
        scoped=[r for r in rows if r['campaign_id']==cid]
        usable=[r for r in scoped if all(known(r.get('facts',{}).get(k)) for k in ('spend','direct_orders','direct_turnover'))]
        cost=sum(r['facts']['spend'] for r in usable);revenue=sum(r['facts']['direct_turnover'] for r in usable)
        complete=len(usable)==len(scoped) and bool(scoped)
        drr=100*cost/revenue if revenue else None
        header='РК '+str(cid)+' · ДРР '+(fmt(drr)+'%' if drr is not None else 'нет данных' if not usable else 'нет прямых заказов')
        if usable and not complete:header+=' — только по доступным товарам'
        lines=[header];above=[];within=0;zero=0;inactive=0
        for row in usable:
            f=row['facts']
            if f['direct_turnover']>0 and f['direct_orders']>0:
                v=100*f['spend']/f['direct_turnover']
                if v>5:above.append((row['article'],v))
                else:within+=1
            elif f['spend']>0:zero+=1
            else:inactive+=1
        if above:
            lines.append('ДРР выше 5%:')
            lines.extend('• '+a+' — '+fmt(v)+'%' for a,v in sorted(above,key=lambda x:-x[1]))
        elif usable:lines.append('Подтверждённых превышений 5% нет.')
        if within:lines.append('В пределах 5%: '+str(within)+' товаров.')
        if zero:lines.append('С расходом без прямых заказов: '+str(zero)+'.')
        missing=len(scoped)-len(usable)
        if missing:lines.append('Нет данных за период: '+str(missing)+' товаров.')
        if inactive:lines.append('Без расхода и заказов: '+str(inactive)+'.')
        b=budgets.get(cid,{})
        if known(b.get('balance')):
            lines.append('Сохранённый баланс: '+fmt(b['balance'])+' ₽; наблюдение '+str(b.get('balance_observed_at'))+('.' if b.get('balance_is_current') else ' — исторический, текущий неизвестен.'))
        else:lines.append('Текущий бюджет неизвестен.')
        scenario=None;reason=None
        if include_budget_scenario:
            observed=b.get('balance_observed_at')
            try:same_day=datetime.fromisoformat(observed.replace('Z','+00:00')).astimezone(now.tzinfo).date()==now.date()
            except (TypeError,ValueError,AttributeError):same_day=False
            if not (complete and cost>0 and duration>0 and b.get('balance_is_current') and same_day and known(b.get('balance'))):
                reason='Нет свежего баланса или полного расхода сопоставимого периода'
                lines.append('На сколько хватит: оценка недоступна — '+reason.lower()+'.')
            else:
                scenario=b['balance']/(cost/duration)
                lines.append('Условно хватит на '+fmt(scenario)+' суток при среднем расходе указанного периода. Это не гарантия; текущий расход после наблюдения баланса неизвестен.')
        details.append(dict(campaign_id=cid,metrics_complete=complete,known_pairs=len(usable),missing_pairs=missing,scenario_days=scenario,scenario_unavailable_reason=reason,budget=b))
        parts.append('\n'.join(lines))
    return dict(period_from=start,period_to=end,campaign_count=len(ids),messages=parts,details=details,
        complete=bool(ids) and all(x['metrics_complete'] for x in details),
        basis='direct_orders; saved balances retain original observation date; no full-attribution claim',
        forecast_module_enabled=False,source_calls=0,telegram_calls=0,wb_writes=0)
