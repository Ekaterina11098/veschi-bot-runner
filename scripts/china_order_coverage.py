"""China catalogue order coverage from scoped MPStats card reads only."""
import copy
import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

MSK = ZoneInfo('Europe/Moscow')
KEY = 'china_agent:order_coverage:v1:'

def table(value):
    if not isinstance(value, dict):
        raise ValueError('Expected card table')
    body = value.get('data')
    if isinstance(body, dict):
        body = body
    else:
        body = value
    rows, total = body.get('data'), body.get('total')
    if not isinstance(rows, list) or type(total) is not int or total < 0:
        raise ValueError('Table completeness unverified')
    if body.get('need_update') not in (None, 0):
        raise ValueError('Report not ready')
    return body, rows, total

def validate_orders(observation, nm, pid, start, end):
    args = observation['arguments']
    if (observation.get('scope_verified') is not True or observation.get('status') != 'received'
            or args != dict(type='products', value=str(pid), date_from=str(start), date_to=str(end), start_row=0, end_row=300)):
        raise ValueError('Order receipt scope mismatch')
    body, rows, total = table(observation['data'])
    filters = body.get('filterModel') or {}
    f = filters.get('product_id') or {}
    d = filters.get('order_dt') or {}
    if (str(f.get('filter')) != str(pid) or f.get('type') != 'equals'
            or d.get('dateFrom') != str(start) or d.get('dateTo') != str(end) or d.get('type') != 'inRange'
            or total != len(rows)):
        raise ValueError('Card rows incomplete or filter mismatch')
    counts = {str(start+timedelta(days=i)): 0 for i in range((end-start).days+1)}
    all_counts = dict(counts)
    seen = set()
    for row in rows:
        if str(row.get('nm_id')) != str(nm) or str(row.get('product_id')) != str(pid):
            raise ValueError('Order identity mismatch')
        stamp = datetime.fromisoformat(row['order_dt'])
        day = str(stamp.replace(tzinfo=MSK).date() if stamp.tzinfo is None else stamp.astimezone(MSK).date())
        if day not in counts or row.get('is_canceled_order') not in (0, 1, False, True):
            raise ValueError('Order date or cancellation unknown')
        identity = row.get('srid') or row.get('gnumber')
        if not identity or str(identity) in seen:
            raise ValueError('Order identity absent or duplicated')
        seen.add(str(identity))
        all_counts[day] += 1
        if not row['is_canceled_order']:
            counts[day] += 1
    return dict(nm_id=str(nm), product_id=str(pid), orders_each_day=list(counts.values()),
                orders=sum(counts.values()), all_orders_each_day=list(all_counts.values()),
                all_orders=sum(all_counts.values()), cancelled_orders=total-sum(counts.values()),
                source='MPStats / lk_wb_card_orders', period_from=str(start), period_to=str(end),
                observed_at=observation['observed_at'], status='complete', financial_data_complete=False)

def recover(db, get, save, start, end, prices, now=None):
    from analytics.mpstats_primary import products
    from analytics.mpstats_probe import discover
    from analytics.mpstats_gaps import execute_reads
    now = now or datetime.now(MSK)
    read = lambda t, p: db('GET', t, params=p)
    rows, marker = products(read, 'token_3', str(start), str(end), now)
    if not marker:
        raise RuntimeError('Primary exact-period product receipt unavailable')
    have = {str(r['nm_id']) for r in rows}
    wanted = {str(r['nmID']): r['vendorCode'] for r in prices if str(r['nmID']) not in have}
    key = KEY+str(start)+':'+str(end)
    previous = get(key) or {}
    result = dict(cabinet='token_3', period_from=str(start), period_to=str(end),
                  primary_snapshot_id=marker['id'], catalogue_count=len({str(r['nmID']) for r in prices}),
                  primary_product_count=len(have), missing_initial=wanted, products={}, errors=[],
                  observed_at=now.isoformat(), wb_calls=0, telegram_calls=0)
    # Reuse verified historical receipts after the final date has closed.
    final = datetime.combine(end+timedelta(days=1), datetime.min.time(), MSK)
    for nm, r in previous.get('products', {}).items():
        try:
            if (nm in wanted and r['status']=='complete' and r['period_from']==str(start) and r['period_to']==str(end)
                    and datetime.fromisoformat(r['observed_at']) >= final):
                result['products'][nm] = r
        except (KeyError, ValueError, TypeError):
            pass
    pending = set(wanted)-set(result['products'])
    if not pending:
        result['status'] = 'complete'
        save(key, result)
        return result
    pause = read('telegram_api_cache', dict(cache_key='eq.mpstats:cooldown', expires_at='gt.'+datetime.now(timezone.utc).isoformat(), select='cache_key', limit=1))
    if pause:
        result.update(status='pending', reason='shared_cooldown')
        save(key, result)
        return result
    observations = []
    def persist(cabinet, observation):
        if cabinet != 'token_3' or not observation.get('scope_verified'):
            raise RuntimeError('Recovery cabinet mismatch')
        a = observation['arguments']
        if observation['tool']=='lk_wb_card_orders':
            if a.get('date_from')!=str(start) or a.get('date_to')!=str(end):
                raise RuntimeError('Recovery period mismatch')
        receipt = db('POST', 'analytics_snapshots', body=dict(source='mpstats_'+observation['tool'], cabinet='token_3',
                     run_id='china-order-coverage-'+os.environ.get('GITHUB_RUN_ID', 'verify'), period_from=str(start), period_to=str(end),
                     status='complete' if observation['status']=='received' else 'error', payload=[observation],
                     detail='Exact-period missing China card evidence; no synthetic finance'), prefer='return=representation') or []
        observation['_snapshot_id'] = receipt[0]['id'] if receipt else None
        observations.append(observation)
        if observation.get('retry_after'):
            save('mpstats:cooldown', dict(pending=True), max(1, observation['retry_after'])/86400)
    def extra(call, checks, known):
        # show_all includes excluded products that the ordinary products table omits.
        args = dict(d11=(start-timedelta(days=4)).strftime('%d.%m.%Y'), d12=(start-timedelta(days=1)).strftime('%d.%m.%Y'),
                    d21=start.strftime('%d.%m.%Y'), d22=end.strftime('%d.%m.%Y'), show_all=True, size_group=False, start_row=0, end_row=1500)
        req = dict(cabinet='token_3', tool='lk_wb_reports_compare', arguments=args, key='china-coverage:compare', priority=90)
        execute_reads(call, checks, known, [req], {}, persist, max_requests=1)
        if not observations or observations[-1]['status']!='received':
            return
        comparison = observations[-1]['data']
        mapping_rows = comparison.get('data')
        if comparison.get('status')!='success' or not isinstance(mapping_rows,list):
            raise RuntimeError('Extended catalogue not ready')
        # Mapping is accepted per exact returned SKU/product_id. Missing rows
        # remain unknown; an omitted card is never interpreted as zero orders.
        registry = {}
        for row in mapping_rows:
            registry.setdefault(str(row.get('nm_id')), []).append(row)
        requests = []
        targets = {}
        for nm in sorted(pending):
            variants = registry.get(nm, [])
            if len(variants)!=1 or not str(variants[0].get('product_id', '')).isdigit() or variants[0].get('article', '').casefold()!=wanted[nm].casefold():
                result['errors'].append(dict(nm_id=nm, article=wanted[nm], reason='product_mapping_unavailable_or_ambiguous'))
                continue
            row = variants[0]
            pid = str(row['product_id'])
            targets[pid] = (nm, row)
            requests.append(dict(cabinet='token_3', tool='lk_wb_card_orders',
                            arguments=dict(type='products', value=pid, date_from=str(start), date_to=str(end), start_row=0, end_row=300),
                            key='china-coverage:orders:'+nm, priority=90))
        def card_save(cabinet, obs):
            persist(cabinet, obs)
            pid=obs['arguments']['value']; nm, mapped=targets[pid]
            try:
                product=validate_orders(obs,nm,pid,start,end)
                product.update(article=wanted[nm], source_snapshot_id=obs.get('_snapshot_id'), extended_orders=mapped.get('orders_count2'))
                # An explicit count from the independent expanded table must reconcile.
                if mapped.get('orders_count2') is not None and mapped['orders_count2'] not in (product['orders'],product['all_orders']):
                    raise ValueError('Expanded order total differs from card receipt')
                result['products'][nm]=product
            except (KeyError,TypeError,ValueError) as exc:
                result['errors'].append(dict(nm_id=nm,article=wanted[nm],reason=str(exc)))
            result['status']='complete' if set(wanted)<=set(result['products']) else 'partial'
            save(key,result)
        return execute_reads(call, checks, known, requests, {}, card_save, max_requests=24)
    connection=discover(os.environ.get('MPSTATS_API_TOKEN',''),read_checks=True,extra_reader=extra)
    result['connection']={k:connection.get(k) for k in ('status','connected','retry_after','detail')}
    if connection.get('retry_after'):
        save('mpstats:cooldown',dict(pending=True),max(1,connection['retry_after'])/86400)
    result['status']='complete' if set(wanted)<=set(result['products']) else 'partial'
    result['remaining']={nm:article for nm,article in wanted.items() if nm not in result['products']}
    save(key,result)
    return result

def main():
    import requests
    from advertising_agent.notify import db, cache_get, cache_set
    original=requests.sessions.Session.request
    def guard(session,method,url,*a,**kw):
        host=urlparse(url).hostname; path=urlparse(url).path
        if host not in ('mcp.mpstats.io',urlparse(os.environ['SUPABASE_URL']).hostname):
            raise RuntimeError('Only MPStats and data storage allowed')
        if host!='mcp.mpstats.io':
            if '/rpc/' in path or (method.upper()!='GET' and path.rsplit('/',1)[-1] not in ('analytics_snapshots','telegram_api_cache')):
                raise RuntimeError('Unrelated database operation forbidden')
        return original(session,method,url,*a,**kw)
    requests.sessions.Session.request=guard
    day=datetime.now(MSK).date(); end=day-timedelta(days=1); start=end-timedelta(days=3)
    prices=cache_get('china_agent:prices:v1') or {}
    if prices.get('cabinet')!='token_3' or not prices.get('rows'):
        raise RuntimeError('China price catalogue missing')
    def save(key,value,ttl_days=365):
        cache_set(key,value,ttl_days)
        if cache_get(key)!=json.loads(json.dumps(value)):
            raise RuntimeError('Coverage storage verification failed')
    try:
        result=recover(db,cache_get,save,start,end,prices['rows'])
        print(json.dumps(dict(status=result['status'],catalogue=result['catalogue_count'],initial_missing=len(result['missing_initial']),recovered=len(result['products']),remaining=len(result.get('remaining',{})),wb_calls=0,telegram_calls=0)))
    except Exception as exc:
        cache_set(KEY+'error:'+str(day),dict(error=type(exc).__name__,detail=str(exc)[:200]),365)
        raise RuntimeError('Order coverage recovery failed; private diagnostic saved') from None

if __name__=='__main__':main()
