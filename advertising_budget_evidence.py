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
