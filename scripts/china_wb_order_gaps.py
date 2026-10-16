"""Narrow owner-requested WB fallback for cards absent from MPStats."""
import base64
import json
import os
import re
import time
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse
from china_agent.order_coverage import MSK,KEY

def counts(rows, day, targets):
    if not isinstance(rows,list) or len(rows)>=80000:
        raise ValueError('WB daily receipt incomplete')
    unique={}
    for row in rows:
        stamp=datetime.fromisoformat(row['date'].replace('Z','+00:00'))
        d=stamp.replace(tzinfo=MSK).date() if stamp.tzinfo is None else stamp.astimezone(MSK).date()
        if d!=day or not row.get('srid') or row.get('nmId') is None or not isinstance(row.get('isCancel'),bool):
            raise ValueError('WB exact-day identity or cancellation unverified')
        srid=str(row['srid'])
        if srid in unique and str(row['nmId'])!=str(unique[srid]['nmId']):
            raise ValueError('WB duplicate order product mismatch')
        if srid not in unique or row.get('lastChangeDate','')>=unique[srid].get('lastChangeDate',''):
            unique[srid]=row
    result={nm:dict(orders=0,cancelled=0) for nm in targets}
    for row in unique.values():
        nm=str(row['nmId'])
        if nm in targets:
            if row.get('supplierArticle','').casefold()!=targets[nm].casefold():
                raise ValueError('WB seller article mismatch')
            result[nm]['cancelled' if row['isCancel'] else 'orders']+=1
    return result

def supplement(db,get,save,start,end,now=None,wait=False):
    from analytics.collect import _fetch_transport
    now=now or datetime.now(MSK)
    key=KEY+str(start)+':'+str(end); result=get(key) or {}
    if result.get('cabinet')!='token_3' or result.get('period_from')!=str(start) or result.get('period_to')!=str(end):
        raise RuntimeError('MPStats coverage must be checked first')
    missing={nm:article for nm,article in result['missing_initial'].items() if nm not in result['products']}
    if not missing:return result
    # The WB exception only fills missing order days; no finance or funnel reads.
    token=os.environ['WB_TOKEN_3'].strip(); segment=token.split('.')[1]
    claims=json.loads(base64.urlsafe_b64decode(segment+'='*(-len(segment)%4)))
    identity=db('GET','analytics_snapshots',params=dict(source='eq.seller_identity',cabinet='eq.token_3',status='eq.complete',select='payload',order='id.desc',limit=1)) or []
    if len(identity)!=1 or not claims.get('sid') or str(claims['sid'])!=str(identity[0]['payload'].get('sid')):
        raise RuntimeError('China WB seller identity unverified')
    day_counts={}; snapshot_ids=[]; last_observed=None
    for i in range((end-start).days+1):
        day=start+timedelta(days=i); daily_key='china_agent:wb_order_gaps:day:'+str(day)
        cached=get(daily_key) or {}
        valid=(cached.get('status')=='complete' and cached.get('cabinet')=='token_3' and cached.get('date')==str(day)
               and cached.get('seller_identity_verified') is True and cached.get('scope')=='flag=1 exact Moscow day')
        if valid:
            try:valid=datetime.fromisoformat(cached['observed_at'])>=datetime.combine(day+timedelta(days=1),datetime.min.time(),MSK)
            except (ValueError,KeyError,TypeError):valid=False
        if not valid:
            deadline=time.monotonic()+240
            while True:
                try:
                    rows=_fetch_transport('GET','https://statistics-api.wildberries.ru/api/v1/supplier/orders',token,params=dict(dateFrom=str(day),flag=1),max_retry_wait=0)
                    break
                except RuntimeError as exc:
                    match=re.search(r'(?:Shared WB cooldown;|Source HTTP 429;) retry after (\d+) seconds',str(exc))
                    if not wait or not match or time.monotonic()+int(match[1])+1>deadline:
                        result.update(status='partial',wb_gap_error=str(exc)[:150]);save(key,result);return result
                    time.sleep(min(60,int(match[1])+1))
            counts(rows,day,missing)
            keep=('date','lastChangeDate','nmId','supplierArticle','srid','isCancel','cancelDate','barcode')
            cached=dict(cabinet='token_3',date=str(day),status='complete',seller_identity_verified=True,
                        scope='flag=1 exact Moscow day',observed_at=datetime.now(timezone.utc).isoformat(),
                        rows=[{k:r[k] for k in keep if k in r} for r in rows])
            receipt=db('POST','analytics_snapshots',body=dict(source='wb_china_missing_orders_daily',cabinet='token_3',
                    run_id='china-order-gaps-'+os.environ.get('GITHUB_RUN_ID','verify'),period_from=str(day),period_to=str(day),status='complete',
                    payload=[cached],detail='Owner requested all catalogue order data; MPStats absent-card fallback, preliminary statistics, no finance'),prefer='return=representation') or []
            cached['snapshot_id']=receipt[0]['id'] if receipt else None
            save(daily_key,cached)
        day_counts[str(day)]=counts(cached['rows'],day,missing)
        snapshot_ids.append(cached.get('snapshot_id'));last_observed=cached['observed_at']
    for nm,article in missing.items():
        daily=[day_counts[str(start+timedelta(days=i))][nm] for i in range((end-start).days+1)]
        active=[r['orders'] for r in daily];cancelled=[r['cancelled'] for r in daily]
        result['products'][nm]=dict(nm_id=nm,article=article,status='complete',source='WB Statistics API / missing MPStats card',
                period_from=str(start),period_to=str(end),observed_at=last_observed,orders_each_day=active,orders=sum(active),
                all_orders_each_day=[a+c for a,c in zip(active,cancelled)],all_orders=sum(active)+sum(cancelled),
                cancelled_orders=sum(cancelled),source_snapshot_ids=snapshot_ids,financial_data_complete=False,
                limitation='Preliminary WB statistics; excludes unconfirmed payments, not a settled sales or profit report')
    result['remaining']={nm:a for nm,a in result['missing_initial'].items() if nm not in result['products']}
    result['status']='complete' if not result['remaining'] else 'partial'
    result['wb_fallback_scope']='Only cards with missing exact-period MPStats order history'
    save(key,result);return result

def main():
    import requests
    from advertising_agent.notify import db,cache_get,cache_set
    now=datetime.now(MSK);end=now.date()-timedelta(days=1);start=end-timedelta(days=3)
    original=requests.sessions.Session.request
    def guard(session,method,url,*a,**kw):
        host=urlparse(url).hostname;path=urlparse(url).path
        if host=='statistics-api.wildberries.ru':
            params=kw.get('params') or {}
            if method.upper()!='GET' or path!='/api/v1/supplier/orders' or params.get('flag')!=1 or not str(start)<=params.get('dateFrom','')<=str(end):
                raise RuntimeError('WB call outside exact order gap scope')
        elif host==urlparse(os.environ['SUPABASE_URL']).hostname:
            if '/rpc/' in path or (method.upper()!='GET' and path.rsplit('/',1)[-1] not in ('analytics_snapshots','telegram_api_cache')):
                raise RuntimeError('Unrelated storage write forbidden')
        else:raise RuntimeError('Unapproved host')
        return original(session,method,url,*a,**kw)
    requests.sessions.Session.request=guard
    def save(key,value,ttl_days=365):
        cache_set(key,value,ttl_days)
        if cache_get(key)!=json.loads(json.dumps(value)):raise RuntimeError('Storage readback failed')
    result=supplement(db,cache_get,save,start,end,now,wait=True)
    print(json.dumps(dict(status=result['status'],catalogue=result['catalogue_count'],recovered=len(result['products']),remaining=len(result.get('remaining',{})),telegram_calls=0)))

if __name__=='__main__':main()
