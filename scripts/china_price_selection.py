"""Bounded full-catalogue price selection under the current MPStats contract."""
import copy
from datetime import datetime,timedelta
from decimal import Decimal

def choose(worker,preview=False):
    from china_agent import demand
    from china_agent.daily_report_worker import MSK
    from china_agent.price_economic_target import verified_price_history
    from china_price_period import period
    from china_price_evidence import valid_daily_orders
    from china_agent.price_brief import render_plain
    from china_agent.buyer_price_forecast import load as load_buyer
    rows,marker=worker.completed_products()
    worker.now=datetime.now(MSK)
    prices=demand.live_prices(worker.now,worker.get,worker.save)
    if prices.get('cabinet')!='token_3' or not prices.get('rows'):raise RuntimeError('Current China price catalogue unavailable')
    state=copy.deepcopy(worker.get(demand.STATE_KEY) or {})
    history=state.setdefault('price_history',{})
    events=verified_price_history(worker)
    end=worker.day-timedelta(days=1);start=end-timedelta(days=3)
    grouped={}
    for r in rows:grouped.setdefault(str(r['nm_id']),[]).append(r)
    daily={nm:r[0]['sparkline_orders'] for nm,r in grouped.items() if len(r)==1 and valid_daily_orders(r[0],4)}
    cache={}
    def read(table,params):
        import json
        key=(table,json.dumps(params,sort_keys=True))
        if key not in cache:cache[key]=worker.db('GET',table,params=params)
        return cache[key]
    from types import SimpleNamespace
    source=SimpleNamespace(db=lambda method,table,params=None:read(table,params))
    from business_agents.data import Data
    business=Data('china',read)
    def cr(nm,a,b):
        data,receipt=period(source,str(a),str(b))
        matches=[r for r in data if str(r.get('nm_id'))==nm]
        if not receipt or len(matches)!=1:return None
        views=matches[0].get('open_card_count');orders=matches[0].get('funnel_orders_count')
        if type(views)not in(int,float)or type(orders)not in(int,float)or views<=0 or not 0<=orders<=views:return None
        return orders/views
    rises=[];results={};stable=0
    for row in prices['rows']:
        nm=str(row['nmID']);article=row['vendorCode'];offer=demand.offer(row)
        if business.excluded(article):continue
        if not offer:continue
        entry=history.setdefault(nm,dict(article=article))
        old=entry.get('price');change=entry.get('last_price_change') or entry.get('increase')
        if old and Decimal(str(old['current_cny']))!=Decimal(str(offer['current_cny'])):
            change=dict(before_price=old,after_price=offer,detected_at=worker.now.isoformat())
            entry['last_price_change']=change
            if offer['current_cny']>old['current_cny']:
                entry['increase']=dict(change,start_date=str(worker.day+timedelta(days=1)),baseline_from=str(worker.day-timedelta(days=4)),baseline_to=str(worker.day-timedelta(days=1)))
            else:entry.pop('increase',None)
        entry.update(article=article,price=offer,observed_at=worker.now.isoformat())
        values=daily.get(nm);qualified=values is not None and all(v>=1 for v in values)
        if qualified:stable+=1
        result=dict(article=article,orders_each_day=values,orders_stable=qualified,action='observe',has_previous_increase=bool(change),full_days=0)
        if nm in ('1473245494','1473245510'):
            result['blocked']='owner_hold';results[nm]=result;continue
        eligible=False
        if qualified and not change and not events.get(nm):
            eligible=True;result['raise_kind']='initial'
        elif qualified and change:
            observed=datetime.fromisoformat(change['detected_at'].replace('Z','+00:00')).astimezone(MSK).date()
            matched=[e['day'] for e in events.get(nm,[]) if e['price_cny']==Decimal(str(offer['current_cny']))]
            actual=max(matched) if matched else observed
            changed=actual if actual>=observed-timedelta(days=1) else observed
            # A newer observed price change cannot be displaced by an old receipt.
            after=(change.get('after_price') or {}).get('current_cny')
            if after is None or Decimal(str(after))!=Decimal(str(offer['current_cny'])):changed=worker.day
            full_days=max(0,(worker.day-changed).days-1);result['full_days']=full_days
            a=changed-timedelta(days=4);b=changed-timedelta(days=1)
            prior=[e['day'] for e in events.get(nm,[]) if a<=e['day']<=b]
            if full_days>=4 and not prior:
                before=cr(nm,a,b);after_cr=cr(nm,start,end)
                result.update(conversion_before=before,conversion_after=after_cr,baseline_from=str(a),baseline_to=str(b),period_from=str(start),period_to=str(end))
                eligible=before is not None and after_cr is not None and after_cr>=before
                result['conversion_held']=None if before is None or after_cr is None else after_cr>=before
                result['raise_kind']='repeat'
        if eligible:
            result['action']='raise';rises.append((article,nm,values,offer))
        results[nm]=result
    assessment=dict(period_from=str(start),period_to=str(end),data_available=True,orders_stable_count=stable,candidate_count=len(rises),results=results)
    worker.audit.update(assessment=assessment,source_snapshot_id=marker['id'],source_collected_at=marker.get('collected_at'))
    state.update(cabinet='token_3',last_checked_at=worker.now.isoformat(),latest=assessment)
    if not preview:worker.save(demand.STATE_KEY,state)
    from china_agent.daily_expected_control import build
    worker.control_preview=preview
    try:review=build(worker,candidate_review=True)
    except (RuntimeError,ValueError) as exc:
        worker.audit['control_source_blocker']=str(exc)[:200]
        review=dict(status='unavailable',report_date=str(worker.day),products=[])
        worker.save('china_agent:daily_expected_candidates:'+str(worker.day)+(':verify' if preview else ''),review)
    worker.price_control_review=review
    lines=['ПЕРВОЕ ПОВЫШЕНИЕ +5%: '+str(len(rises))]
    fmt=lambda x:str(x).replace('.',',')
    for article,nm,values,offer in sorted(rises):
        lines+=['',article,'Заказы по дням: '+('/'.join(map(str,values))),
                'Цена продавца после скидки: '+fmt(offer['current_cny'])+' → '+fmt(offer['target_cny'])+' ¥.']
    lines+=['','Повторное повышение включено по общей конверсии.']
    buyer=load_buyer(worker);omitted=[]
    answer=render_plain('\n'.join(lines),'morning',review,worker.day,prices,buyer,omitted=omitted)
    worker.audit['price_proposal_exclusions']=omitted
    return answer,[dict(name='china_price_daily_report',report_date=str(worker.day),period_from=str(start),period_to=str(end),source_snapshot_id=marker['id'],status='complete_orders',ready_rises=len(rises),execution_authorized=False)]

