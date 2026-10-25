"""Reusable, read-only order-date forecast; settled profit is a separate measure."""
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

def dec(v):
    if v is None or isinstance(v, bool):
        raise ValueError('Missing monetary input')
    d = Decimal(str(v))
    if not d.is_finite():
        raise ValueError('Non-finite input')
    return d
def rounded(v):
    return float(v.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

def calculate_inputs(base, extra, orders, delivery_model, recovery=None):
    products = {r['nm_id']: r for r in base['buyout']['rows']}
    stock = {r['article'].casefold(): r for r in base['stock']['rows']}
    prices = {r['nm_id']: r for r in extra['prices']['rows']}
    historical = {}
    for r in sorted(base['history_costs'], key=lambda r: r.get('cost_date') or ''):
        if r['cost_rub'] is not None and (r.get('cost_date') or '')[:10] <= max(extra['days']):
            historical[r['nm_id']] = r
    funnel = {}
    for bundle in base['funnel']:
        assert bundle['complete'] is True
        for r in bundle['rows']:
            for part in ('past', 'selected'):
                day = r[part]['period_from']
                key = (r['nm_id'], day)
                previous = funnel.get(key)
                if previous is not None:
                    assert previous == r[part] or all(previous[k] == r[part][k] for k in ('orders', 'order_amount_cny'))
                funnel[key] = r[part]
    finance = defaultdict(list)
    for r in base['finance']['rows']:
        finance[r['nmId']].append(r)
    policy = base['policy']
    assert delivery_model['cabinet'] == 'token_3' and delivery_model['rub_per_cny'] == policy['fx_rub_cny']
    for r in (recovery or {}).get('evidence', []):
        if r.get('cost_rub') is not None:
            historical[r['nm_id']] = dict(r, source_key=r.get('source_key','MoySklad historical positive-stock cost'), cost_date=r.get('cost_date_msk'))
    fx, tax, handling = map(dec, (policy['fx_rub_cny'], policy['tax_pct'] / 100, policy['handling_rub']))
    rows, gaps = [], []
    days = extra['days']
    seen = set()
    for o in orders:
        nm, day, n = o['nm_id'], o['day'], o['orders']
        assert (nm, day) not in seen
        seen.add((nm, day))
        p = products[nm]
        assert p['article'].casefold() == o['article'].casefold()
        own_n, own_paid = p['finished'], p['paid']
        if own_n is None or own_paid is None or p['returned'] is None:
            gaps.append(dict(nm_id=nm, day=day, missing='Incomplete own buyout counts')); continue
        assert 0 <= own_paid <= own_n and own_paid + p['returned'] <= own_n
        probability = dec(own_paid) / dec(own_n) if own_n else Decimal('.5')
        if own_n and p['reported_pct'] is not None:
            assert abs(probability * 100 - dec(p['reported_pct'])) <= Decimal('.011')
        cost = stock.get(o['article'].casefold(), {}).get('cost_rub')
        cost_source = base['stock']['source_key']
        cost_date = base['stock']['observed_at']
        if cost is None:
            h = historical.get(nm, {})
            cost, cost_source, cost_date = h.get('cost_rub'), h.get('source_key'), h.get('cost_date')
        if cost is None:
            gaps.append(dict(nm_id=nm, day=day, article=o['article'], missing='Own COGS')); continue
        fees = {dec(r['commissionPercent']) for r in finance[nm] if dec(r['commissionPercent']) > 0}
        assert len(fees) <= 1
        fee = (next(iter(fees)) if fees else dec(policy['commission_pct'])) / 100
        fee_basis = 'own_finance' if fees else 'China20pct_assumption_no_own_tariff'
        delivered = [r for r in finance[nm] if dec(r['deliveryService']) > 0 and dec(r['deliveryAmount']) > 0 and dec(r['returnAmount']) == 0]
        if delivered:
            forward = sum(dec(r['deliveryService']) for r in delivered) / sum(dec(r['deliveryAmount']) for r in delivered)
            delivery_basis = 'own_finance_forward_per_delivery'
        else:
            logistics = policy['logistics_by_nm'].get(str(nm), {})
            if logistics.get('delivery_cny') is None:
                saved = delivery_model['rows'].get(o['article'], {})
                if saved.get('delivery_cny') is not None:
                    logistics = dict(delivery_cny=saved['delivery_cny'],delivery_source='agreed_delivery_model_03Oct_scenario')
            if logistics.get('delivery_cny') is None:
                gaps.append(dict(nm_id=nm, day=day, article=o['article'], missing='Delivery tariff')); continue
            forward = dec(logistics['delivery_cny'])
            delivery_basis = logistics['delivery_source']
        f = funnel.get((nm, day))
        if f is None:
            gaps.append(dict(nm_id=nm,day=day,missing='WB daily order amount unavailable')); continue
        reported_n, reported_revenue = f['orders'], dec(f['order_amount_cny'])
        assert n >= reported_n >= 0
        # Keep the actual WB funnel orderSum intact. Extra FBS units are a disclosed
        # price scenario; never relabel the extrapolation as WB orders_sum / DRR.
        extra_n = n - reported_n
        if reported_n:
            proxy_price = reported_revenue / reported_n
            proxy_basis = 'same_SKU_same_day_WB_average_order_amount'
        else:
            proxy_price = dec(prices[nm]['seller_price'])
            proxy_basis = 'seller_price_snapshot_for_unpriced_FBS_units'
        revenue = reported_revenue + dec(extra_n) * proxy_price
        ads = extra['ad_expenses']['daily'][day]['by_sku'].get(str(nm), 0)
        value = probability * (revenue * fx * (1 - fee - tax) - dec(n) * dec(cost)) - dec(n) * (forward * fx + handling) - dec(ads) * fx
        rows.append(dict(nm_id=nm, article=o['article'], date=day, orders=n,
            wb_funnel_orders=reported_n, wb_funnel_order_sum_cny=rounded(reported_revenue),
            price_scenario_units=extra_n, price_scenario_cny=rounded(proxy_price), price_scenario_basis=proxy_basis,
            model_revenue_cny=rounded(revenue), expected_buyouts=float(dec(n)*probability),
            buyout_pct=float(probability*100), buyout_paid=own_paid, buyout_completed=own_n,
            buyout_fallback=own_n == 0, small_sample=0 < own_n < 10,
            cost_rub=float(cost), cost_source=cost_source, cost_observed_at=cost_date,
            commission_pct=float(fee*100), commission_basis=fee_basis,
            forward_cny=float(forward), forward_basis=delivery_basis,
            tax_pct=float(tax*100), handling_rub=float(handling), ad_expense_cny=ads,
            expected_profit_rub=rounded(value), reverse_logistics_included=False,
            all_expenses_confirmed=False, is_actual=False))
    for day in days:
        for nm_string, spend in extra['ad_expenses']['daily'][day]['by_sku'].items():
            nm = int(nm_string)
            if dec(spend) <= 0 or (nm, day) in seen or nm not in products:
                continue
            p = products[nm]
            probability = dec(p['paid']) / dec(p['finished']) if p['finished'] else Decimal('.5')
            rows.append(dict(nm_id=nm, article=p['article'], date=day, orders=0,
                wb_funnel_orders=0, wb_funnel_order_sum_cny=0, price_scenario_units=0,
                expected_buyouts=0, buyout_pct=float(probability*100),
                buyout_paid=p['paid'], buyout_completed=p['finished'],
                buyout_fallback=p['finished']==0, small_sample=0<p['finished']<10,
                ad_expense_cny=spend,expected_profit_rub=rounded(-dec(spend)*fx),
                is_actual=False,ad_only=True,all_expenses_confirmed=False))
    daily = []
    for day in days:
        selected = [r for r in rows if r['date'] == day]
        cabinet_ads = dec(extra['ad_expenses']['daily'][day]['spend_cny'])
        allocated = sum(dec(r['ad_expense_cny']) for r in selected)
        # Expense on products without orders belongs in the cabinet result too.
        ad_remainder = cabinet_ads - allocated
        assert ad_remainder >= Decimal('-.01')
        result = sum(dec(r['expected_profit_rub']) for r in selected) - ad_remainder * fx
        daily.append(dict(date=day, created_orders=sum(o['orders'] for o in orders if o['day'] == day),
            calculated_orders=sum(r['orders'] for r in selected), forecast_profit_rub=rounded(result) if not any(g['day']==day for g in gaps) else None,
            calculated_subtotal_rub=rounded(result), cabinet_ads_cny=float(cabinet_ads),
            advertising_on_unordered_skus_rub=rounded((ad_remainder+sum(dec(r['ad_expense_cny']) for r in selected if r['orders']==0))*fx),
            expected_buyouts=round(sum(r['expected_buyouts'] for r in selected),2),
            fallback50_orders=sum(r['orders'] for r in selected if r['buyout_fallback']),
            small_sample_orders=sum(r['orders'] for r in selected if r['small_sample']),
            price_scenario_units=sum(r['price_scenario_units'] for r in selected),
            forecast_basis='created_order_date_expected_own30day_buyout',is_actual=False))
    result = dict(status='calculated_preliminary' if not gaps else 'partial_missing_inputs',
        buyout_source=base['buyout']['snapshot_id'],buyout_period=[base['buyout']['period_from'],base['buyout']['period_to']],
        buyout_observed_at=base['buyout']['observed_at'],orders_observed_at=extra['orders_observed_at'],
        ads_observed_at=extra['ad_expenses']['observed_at'],currency='RUB',fx_rub_cny=float(fx),daily=daily,rows=rows,gaps=gaps,
        assumptions=['Own settled buyout fixed across compared dates, pending excluded',
          '50% only where no own completed sample; genuine own0% retained',
          'WB funnel amount unchanged; extra FBS units use disclosed same-day-average/seller-snapshot price scenario',
          'Forward delivery reserve per created order, including pre-dispatch cancellations',
          'Additional reverse/return-to-RF and unallocated other expenses unknown, not included; not assumed zero',
          'Actual daily advertising all campaign statuses once, no WBPromotion duplicate',
          'Own MoySklad COGS; earlier positive-stock date only if unavailable now',
          'Tax5% on expected seller revenue before WB discounts; handling10RUB; FX12RUB/CNY'],
        wb_writes=0,telegram_sends=0)
    return result


def collect(w,job,date_from,date_to,nm_ids=()):
    """Collect inputs through authorized reads, retaining dates and missing costs."""
    import hashlib,os,requests
    from datetime import date,datetime,timedelta,timezone
    from china_analytic_dialog import Analyst,reading
    from china_wb_evidence import Reports,ROOT as EVIDENCE,own_costs,ad_expenses,settlement
    msk=timezone(timedelta(hours=3));clock=datetime.now(timezone.utc)
    first,last=date.fromisoformat(date_from),date.fromisoformat(date_to)
    today=w.now.astimezone(msk).date()
    if not 0<=(last-first).days<31 or last>today:raise ValueError('Нужен период1–31день без будущего')
    valid={int(n):a for n,a in w.catalog()}
    if any(n not in valid for n in nm_ids):raise ValueError('Неизвестный nmID Китая')
    key='china_agent:order_profit_forecast:v1:'+str(job['id'])+':'+date_from+':'+date_to
    cached=w.get(key)
    if cached and (clock-datetime.fromisoformat(cached['observed_at'])).total_seconds()<1200:
        return summary(cached,nm_ids)
    analyst=Analyst(w,job,[]);end=today-timedelta(days=1);start=end-timedelta(days=29)
    try:
        own=analyst.live('products',[],str(start),str(end))
        if not own.get('rows'):raise ValueError('Own completed sample source empty')
    except (ValueError,RuntimeError):
        # If the newest day is not published yet, a complete dated snapshot is
        # useful evidence. Do not ask the person to resend data already stored.
        from analytics.mpstats_primary import products as saved_products
        own=None
        for lag in (0,1,2):
            b=end-timedelta(days=lag);a=b-timedelta(days=29)
            saved,marker=saved_products(lambda t,p:w.db('GET',t,params=p),'token_3',a,b,w.now)
            if marker and saved:
                own=dict(rows=saved,observed_at=marker['collected_at'],source_key='analytics_snapshots:'+str(marker['id']),
                    period_from=str(a),period_to=str(b),source='Complete stored own buyout snapshot',freshness_note='Newest period unavailable; exact earlier30full days disclosed')
                start,end=a,b;break
        if own is None:raise ValueError('Нет завершённой собственной30дневной выборки и полного сохранённого среза')
    stock=analyst.live('stock',[],date_from,date_to)
    prices=analyst.live('prices',[],date_from,date_to)
    products=[dict(nm_id=int(r['nm_id']),article=r['sa_name'],finished=r.get('finished_orders'),
        paid=r.get('is_payed'),returned=r.get('finish_as_return'),reported_pct=r.get('buyout_pct')) for r in own['rows']]
    days=[str(first+timedelta(days=i)) for i in range((last-first).days+1)]
    policy=w.get('china_agent:new_ad_economics_policy:v1')
    model=w.get('china_agent:expected_profit_delivery_model:v1')
    if not policy or not model:raise ValueError('Нет согласованной модели логистики/налога/курса')
    orders={};cursor=0;pages=0;requests_used=0
    cutoff=min(clock,datetime.combine(last+timedelta(days=1),datetime.min.time(),msk))
    a=datetime.combine(first,datetime.min.time(),msk)
    with reading():
        while True:
            r=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',headers={'Authorization':os.environ['WB_TOKEN_3']},
                params=dict(limit=1000,next=cursor,dateFrom=int(a.timestamp()),dateTo=int(cutoff.timestamp())),timeout=60)
            requests_used+=1;pages+=1
            if not r.ok:raise RuntimeError('WB orders HTTP '+str(r.status_code))
            body=r.json();part=body.get('orders',[])
            for item in part:
                if item['id'] in orders and orders[item['id']]!=item:raise ValueError('Conflicting WB order')
                orders[item['id']]=item
            nxt=body.get('next')
            if not part or not nxt:break
            if nxt==cursor or pages>=20:raise ValueError('WB order pagination incomplete')
            cursor=nxt
        grouped={}
        for item in orders.values():
            nm=int(item['nmId']);day=str(datetime.fromisoformat(item['createdAt'].replace('Z','+00:00')).astimezone(msk).date())
            if nm not in valid or item['article'].casefold()!=valid[nm].casefold() or day not in days:raise ValueError('WB order catalogue/date identity mismatch')
            o=grouped.setdefault((nm,day),dict(nm_id=nm,article=item['article'],day=day,orders=0));o['orders']+=1
        reports=Reports(w);pointer=w.get(EVIDENCE+'finance_latest') or {}
        finance=w.get(pointer['source_key']) if pointer.get('source_key') else None
        if not finance or not finance.get('complete'):finance=reports.finance(str(start),str(end))
        bundles=[];seen_bundles=set();collection_gaps=[]
        for day in days:
            candidates=[day,str(date.fromisoformat(day)+timedelta(days=1))]
            saved=None
            for candidate in candidates:
                state=w.get(EVIDENCE+'funnel:'+candidate+':'+candidate)
                if not state or not state.get('complete'):continue
                if (clock-datetime.fromisoformat(state['observed_at'])).total_seconds()>43200:continue
                if any(r[k]['period_from']==day for r in state.get('rows',[]) for k in ('past','selected')):
                    saved=state;break
            if saved is None:
                if requests_used>=12:
                    collection_gaps.append(dict(date=day,missing='Лимит узкого сбора; дневная сумма WB ещё не получена'));continue
                saved=reports.funnel(day,day);requests_used+=1
            if saved.get('complete'):
                source=saved.get('source_key',saved.get('observed_at'))
                if source not in seen_bundles:bundles.append(saved);seen_bundles.add(source)
            else:collection_gaps.append(dict(date=day,missing='Дневная воронка WB не завершена',status=saved.get('status'),retry_at=saved.get('retry_at')))
        fake=[dict(nmId=n,rrDate=date_from,sellerOperName='销售') for n in sorted({o['nm_id'] for o in grouped.values()})]
        # Own COGS is looked up at an earlier positive-stock date when missing now.
        costs,evidence=own_costs(w,stock,fake+finance.get('rows',[]),date_from,date_to)
        ads=ad_expenses(w,date_from,date_to)
        if not ads.get('complete'):raise ValueError('Расход рекламы за период не подтверждён')
    base=dict(buyout=dict(rows=products,snapshot_id=own.get('source_key'),period_from=str(start),period_to=str(end),observed_at=own['observed_at']),
        stock=stock,history_costs=[dict(nm_id=e['nm_id'],cost_rub=e.get('cost_rub'),cost_date=e.get('cost_date_msk'),source_key=e.get('source','MoySklad history')) for e in evidence],
        funnel=bundles,finance=finance,policy=policy)
    extra=dict(prices=prices,ad_expenses=ads,days=days,orders_observed_at=clock.isoformat())
    result=calculate_inputs(base,extra,list(grouped.values()),model)
    result.update(observed_at=clock.isoformat(),source_key=key,cutoff_msk=cutoff.astimezone(msk).isoformat(),
        is_partial_day=last==today,collection_gaps=collection_gaps,requests_used=requests_used)
    result['published_daily']=[dict(date=day,**settlement(finance,day,day,costs=costs,ads=ads)) for day in days]
    from china_experience import decision_context
    events=decision_context(w)['experiences']
    result['verified_changes']=[dict(started_at=e['started_at'],action=e['action'],source_key=e.get('source_key')) for e in events
        if e.get('started_at') and first<=datetime.fromisoformat(e['started_at'].replace('Z','+00:00')).astimezone(msk).date()<=last]
    w.save(key,result)
    return summary(result,nm_ids)


def summary(result,nm_ids=()):
    """Keep cabinet totals intact; expose requested SKUs or the main order declines."""
    days=sorted(r['date'] for r in result['daily']);counts={}
    for r in result['rows']:counts.setdefault(r['nm_id'],{})[r['date']]=r['orders']
    selected=set(nm_ids) if nm_ids else set(sorted(counts,key=lambda n:counts[n].get(days[-1],0)-counts[n].get(days[-2],0) if len(days)>1 else -counts[n].get(days[-1],0))[:10])
    fields=['status','daily','buyout_period','buyout_source','buyout_observed_at','orders_observed_at','ads_observed_at','observed_at','currency','fx_rub_cny','source_key','cutoff_msk','is_partial_day','assumptions','gaps','collection_gaps','published_daily','wb_writes','telegram_sends']
    out={k:result.get(k) for k in fields}
    columns=['nm_id','article','date','orders','wb_funnel_orders','wb_funnel_order_sum_cny','price_scenario_units','buyout_pct','buyout_paid','buyout_completed','buyout_fallback','small_sample','ad_expense_cny','expected_profit_rub']
    out.update(rows=[{k:r.get(k) for k in columns} for r in result['rows'] if r['nm_id'] in selected],
        verified_changes=[e for e in result.get('verified_changes',[]) if set(e.get('action',{}).get('nm_ids',[]))&selected],
        scope='Daily totals are the whole China cabinet; rows are selected SKUs',
        full_rows_available_privately=True)
    return out



