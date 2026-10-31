"""Read-only hourly China collector. Private snapshots; no marketplace mutations or messages."""
import json
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
from china_cloud_cost_control import Cache, WB, validate_identity, stamp

MSK = ZoneInfo('Europe/Moscow')
ROOT = 'china_agent:hourly_sales_api:v1'
POLICY = ROOT + ':policy'
FIELDS = ('id', 'nmId', 'article', 'createdAt', 'convertedPrice', 'convertedCurrencyCode', 'isZeroOrder')


class ReadOnlyWB(WB):
    def req(self, path, method='GET', body=None, write=False):
        bare = path.split('?')[0]
        allowed = {('GET', '/adv/v1/promotion/count'), ('GET', '/api/advert/v2/adverts'),
                   ('GET', '/adv/v3/fullstats'), ('POST', '/api/advert/v2/budget')}
        if write or (method, bare) not in allowed:
            raise ValueError('Read-only collector endpoint guard')
        return super().req(path, method, body, write=False)


def slot_key(cut):
    return ROOT + ':snapshot:' + cut.strftime('%Y-%m-%dT%H') + ':MSK'


def aggregate(rows):
    bad = [r['id'] for r in rows if r.get('convertedCurrencyCode') != 156
           or type(r.get('convertedPrice')) not in (int, float)]
    return dict(count=len(rows), amount_cny=None if bad else round(sum(r['convertedPrice'] for r in rows) / 100, 2),
                unknown_amount_ids=bad)


def read_orders(get, start, end):
    rows = {}; cursor = 0
    for page in range(12):
        data = get('/api/v3/orders', dict(limit=1000, next=cursor,
                   dateFrom=int(start.timestamp()), dateTo=int(end.timestamp())))
        part = data.get('orders')
        if not isinstance(part, list):
            raise ValueError('Malformed order page')
        for row in part:
            rows[row['id']] = row
        nxt = data.get('next')
        if not part or not nxt:
            return rows
        if nxt == cursor:
            raise ValueError('Order cursor did not advance')
        cursor = nxt
        time.sleep(.4)
    raise ValueError('Order pagination incomplete')


def select_rows(rows, start, end):
    out = []
    for row in rows:
        at = datetime.fromisoformat(row['createdAt'].replace('Z', '+00:00'))
        if at.tzinfo is None:
            raise ValueError('Missing order timezone')
        if start <= at.astimezone(MSK) < end:
            out.append({k: row.get(k) for k in FIELDS})
    return sorted(out, key=lambda r: r['id'])


def comparison(current, baseline):
    out = {}
    for field in ('count', 'amount_cny'):
        a, b = current.get(field), baseline.get(field)
        out[field] = dict(current=a, baseline=b, delta=None if a is None or b is None else round(a-b, 2),
                          pct=round((a/b-1)*100, 2) if a is not None and b else None)
    return out


def safe_error(ex):
    return str(ex) if isinstance(ex, (ValueError, RuntimeError)) else type(ex).__name__


def collect_funnel(c, cut, nm_ids):
    """General funnel counters, never advertising orders divided by all visits."""
    from china_wb_evidence import Reports, FUNNEL, normalize_funnel
    if not nm_ids or len(nm_ids) > 5 or any(type(nm) is not int for nm in nm_ids):
        raise ValueError('Exact bounded funnel scope required')
    class Adapter:
        def get(self, key): return c.get(key)
        def save(self, key, value): return c.put(key, value)
        def db(self, method, table, params=None, body=None, prefer=None):
            if table != 'telegram_api_cache':
                raise ValueError('Private report cache only')
            return c.req(method, params, body, prefer)
    selected = dict(start=cut.date().isoformat(), end=cut.date().isoformat())
    yesterday = (cut-timedelta(days=1)).date().isoformat()
    past = dict(start=yesterday, end=yesterday)
    body = dict(selectedPeriod=selected, pastPeriod=past, nmIds=nm_ids, brandNames=[],
                subjectIds=[], tagIds=[], skipDeletedNm=False,
                orderBy=dict(field='openCard', mode='desc'), limit=10, offset=0)
    result = Reports(Adapter()).request(FUNNEL, body)
    if not result['available']:
        return dict(status='unavailable', reason=result.get('status'), retry_at=result.get('retry_at'))
    data = result['data'].get('data', {})
    products = data.get('products')
    if not isinstance(products, list) or data.get('currency', '').upper() != 'CNY':
        raise ValueError('Funnel currency/shape mismatch')
    if {p['product']['nmId'] for p in products} != set(nm_ids) or len(products) != len(nm_ids):
        raise ValueError('Funnel target coverage mismatch')
    return dict(status='complete', observed_at=result['observed_at'], scope='all_sources',
                rows=normalize_funnel(products, selected, past, slot_key(cut)),
                update_delay_hours=2, past_period_is_full_day=True,
                samehour_baseline_key=slot_key(cut-timedelta(days=1)),
                warning='Current partial day; API past is full previous day, not same hour. Use saved observed snapshots for same-clock comparison, with reporting lag explicitly.')


def run():
    if os.environ.get('GITHUB_REPOSITORY') != 'Ekaterina11098/veschi-bot-runner':
        raise RuntimeError('Public owner runner only')
    c = Cache(); w = ReadOnlyWB()
    policy = c.get(POLICY) or {}
    if policy.get('enabled') is not True or policy.get('cabinet') != 'token_3' or policy.get('wb_writes') != 0:
        raise RuntimeError('Read-only owner policy unavailable')
    validate_identity(c, w)
    cut = datetime.now(timezone.utc).astimezone(MSK).replace(minute=0, second=0, microsecond=0)
    key = slot_key(cut)
    if c.get(key):
        print('Frozen hourly slot already exists; no API reads repeated')
        return
    catalog = c.get('china_agent:prices:v1') or {}
    if catalog.get('cabinet') != 'token_3':
        raise ValueError('China catalogue identity unavailable')
    allowed = {int(r['nmID']) for r in catalog.get('rows', [])}
    e = dict(status='reading', cabinet='token_3', slot_msk=cut.isoformat(), observed_at=stamp(),
             wb_writes=0, telegram_calls=0, workflow_run=os.environ.get('GITHUB_RUN_ID'),
             orders={}, advertising={}, grants_action_permission=False)
    if not c.create(key + ':lease', dict(created_at=stamp(), workflow_run=e['workflow_run'])):
        raise RuntimeError('Hourly slot already attempted; inspect lease before recovery')

    def get(path, params=None):
        if path not in ('/api/v3/orders', '/api/v3/orders/new'):
            raise ValueError('FBS read-only endpoint guard')
        r = requests.get('https://marketplace-api.wildberries.ru' + path,
                         headers={'Authorization': w.token}, params=params, timeout=50)
        if not r.ok:
            raise ValueError('FBS read HTTP ' + str(r.status_code))
        return r.json()

    try:
        new = get('/api/v3/orders/new').get('orders')
        if not isinstance(new, list):
            raise ValueError('Malformed new orders response')
    except Exception as ex:
        new = []; e['new_orders_error'] = safe_error(ex)
    for offset in (0, 1, 7):
        end = cut - timedelta(days=offset)
        start = end.replace(hour=0)
        try:
            raw = read_orders(get, start, end) if end > start else {}
            raw.update({r['id']: r for r in new})
            rows = select_rows(raw.values(), start, end)
            unknown = sorted({r['nmId'] for r in rows if r['nmId'] not in allowed})
            totals = aggregate(rows)
            last = select_rows(raw.values(), end-timedelta(hours=1), end) if end > start else []
            complete = not unknown and not totals['unknown_amount_ids'] and not e.get('new_orders_error')
            e['orders'][str(offset)] = dict(status='complete' if complete else 'partial',
                start_msk=start.isoformat(), end_msk=end.isoformat(), observed_at=stamp(),
                rows=rows, totals=totals, last_completed_hour=aggregate(last) if end > start else None,
                unknown_catalogue_nmids=unknown, basis='FBS created units, all statuses, dedup id; native CNY buyer-discounted amount; not buyouts or all sales models')
        except Exception as ex:
            e['orders'][str(offset)] = dict(status='unavailable', reason=safe_error(ex), observed_at=stamp())
    if all(e['orders'][str(x)]['status'] == 'complete' for x in (0, 1, 7)):
        e['sales_comparisons'] = {str(x): comparison(e['orders']['0']['totals'], e['orders'][str(x)]['totals']) for x in (1, 7)}
        if cut.hour:
            e['last_hour_comparisons'] = {str(x): comparison(e['orders']['0']['last_completed_hour'], e['orders'][str(x)]['last_completed_hour']) for x in (1, 7)}
    if policy.get('funnel_nm_ids'):
        try:
            e['general_funnel'] = collect_funnel(c, cut, policy['funnel_nm_ids'])
        except Exception as ex:
            e['general_funnel'] = dict(status='unavailable', reason=safe_error(ex))
    try:
        inv = w.req('/adv/v1/promotion/count')
        ids = sorted({a['advertId'] for group in inv.get('adverts', []) if group['status'] in (7, 9, 11)
                      for a in group.get('advert_list', [])})
        if len(ids) > 50:
            raise ValueError('Campaign pagination required')
        campaigns = w.campaigns(ids) if ids else {}
        if any(row.get('currency') != 'CNY' for row in campaigns.values()):
            raise ValueError('Non-CNY campaign state')
        raw = w.req('/adv/v3/fullstats?ids=' + ','.join(map(str, ids)) + '&beginDate=' + cut.date().isoformat() + '&endDate=' + cut.date().isoformat()) if ids else []
        if not isinstance(raw, list):
            raise ValueError('Malformed advertising response')
        missing = sorted(set(ids)-{r['advertId'] for r in raw})
        spend = sum(r['sum'] for r in raw); amount = sum(r['sum_price'] for r in raw)
        e['advertising'] = dict(status='partial' if missing else 'complete', observed_at=stamp(),
            requested_ids=ids, missing_ids=missing, campaigns=campaigns, stats=raw, currency='CNY',
            totals=dict(spend_cny=round(spend,2), attributed_order_amount_cny=round(amount,2),
                        orders=sum(r['orders'] for r in raw), clicks=sum(r['clicks'] for r in raw),
                        views=sum(r['views'] for r in raw), drr_pct=spend/amount*100 if amount>0 else None),
            basis='Current cumulative advertising attribution snapshot, including completed campaigns; overlapping attributed orders not unique; not exact order cutoff')
        try:
            budget_ids = sorted(int(cid) for cid, row in campaigns.items() if row['status'] in (9, 11))
            budgets = w.req('/api/advert/v2/budget', 'POST', dict(advertIds=budget_ids)).get('adverts', []) if budget_ids else []
            e['budgets'] = dict(status='complete' if {r['advertId'] for r in budgets} == set(budget_ids) else 'partial',
                                observed_at=stamp(), rows=budgets, requested_ids=budget_ids,
                                scope='Active and paused only; completed campaign expenses retained in advertising stats')
        except Exception as ex:
            e['budgets'] = dict(status='unavailable', reason=safe_error(ex))
        adtime = datetime.fromisoformat(e['advertising']['observed_at'])
        e['ad_comparisons'] = {}
        for offset in (1, 7):
            oldkey = slot_key(cut-timedelta(days=offset)); old = c.get(oldkey) or {}
            prev = old.get('advertising', {})
            result = dict(status='unavailable_no_saved_same_clock_snapshot', source_key=oldkey)
            if prev.get('status') == 'complete' and e['advertising']['status'] == 'complete':
                prior_time = datetime.fromisoformat(prev['observed_at'])
                diff = abs((adtime-prior_time-timedelta(days=offset)).total_seconds())
                result.update(clock_difference_seconds=diff)
                if diff <= 600 and prev.get('currency') == 'CNY':
                    result.update(status='comparable_snapshot', current=e['advertising']['totals'],
                                  baseline=prev['totals'], current_observed_at=adtime.isoformat(),
                                  baseline_observed_at=prior_time.isoformat(), tolerance_minutes=10)
                else:
                    result['status']='unavailable_clock_mismatch'
            e['ad_comparisons'][str(offset)] = result
    except Exception as ex:
        e['advertising'] = dict(status='unavailable', reason=safe_error(ex), observed_at=stamp())
    e.update(status='complete' if all(r['status']=='complete' for r in e['orders'].values()) and e['advertising']['status']=='complete' else 'partial', completed_at=stamp())
    if not c.create(key, e):
        raise RuntimeError('Frozen slot conflict')
    if c.get(key) != e:
        raise RuntimeError('Frozen snapshot readback mismatch')
    c.put(ROOT + ':latest', dict(source_key=key, status=e['status'], observed_at=e['observed_at'],
                               completed_at=e['completed_at'], slot_msk=e['slot_msk'], wb_writes=0))
    print(json.dumps(dict(status=e['status'], source_key=key, orders={k:v['status'] for k,v in e['orders'].items()}, advertising=e['advertising']['status'], wb_writes=0, telegram_calls=0)))


if __name__ == '__main__':
    run()

