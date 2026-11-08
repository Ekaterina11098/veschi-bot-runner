"""Evidence for reconsidering former advertising exclusions; no model or WB writes."""
import json,math
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

PERIOD='china_agent:ad_retest_period:v1:'
NEVER_AUTORETEST={1007948808,1473245494,1473245510,1473243903}  # Explicit owner holds remain.

def finite(v):return type(v) in (int,float) and math.isfinite(v)
def changed_day(event):return datetime.fromisoformat(event['started_at'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date()
def funnel(row):
    v,n=row.get('open_card_count'),row.get('funnel_orders_count')
    if not finite(v) or not finite(n) or v<=0 or n<0:return None
    return dict(views=v,orders=n,cr_pct=100*n/v)

def period(io,first,last,collect=False):
    from china_saved_products import saved_products
    def db(method,table,params=None):
        if method!='GET':raise PermissionError('Period adapter is read-only')
        return io.db(table+'?'+urlencode(params or {}))
    saved=saved_products(SimpleNamespace(db=db),first,last,[])
    if saved:return saved
    key=PERIOD+str(first)+':'+str(last);old=io.get(key)
    if old and old.get('status')=='complete':return old
    if not collect:return None
    now=datetime.now(timezone.utc)
    if old and old.get('status')!='complete' and (now-datetime.fromisoformat(old['at'])).total_seconds()<900:return None
    cooldown=io.db('telegram_api_cache?'+urlencode(dict(cache_key='eq.mpstats:cooldown',expires_at='gt.'+now.isoformat(),select='cache_key',limit=1)))
    if cooldown:return None
    from analytics.mpstats_probe import discover
    from analytics.mpstats_gaps import execute_reads
    import os
    args=dict(date_from=str(first),date_to=str(last),start_row=0,end_row=1000)
    calls=[dict(cabinet='token_3',tool='lk_wb_products',key=key,priority=75,arguments=args)]
    observations=[]
    def persist(cabinet,obs):
        if cabinet=='token_3' and obs.get('tool')=='lk_wb_products' and obs.get('arguments')==args and obs.get('status')=='received' and obs.get('scope_verified') is True:
            observations.append(obs)
    def extra(call,checks,known):return execute_reads(call,checks,known,calls,{},persist,max_requests=1)
    io.put(key,dict(status='collecting',at=now.isoformat()))
    try:
        discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
        if len(observations)!=1:raise ValueError('Exact-period evidence unavailable')
        data=observations[0].get('data',{}).get('data',{});rows=data.get('data')
        if not isinstance(rows,list) or data.get('need_update')!=0 or (data.get('pagination_complete') is not True and data.get('total')!=len(rows)):
            raise ValueError('Incomplete exact-period rows')
        fields=('nm_id','sa_name','open_card_count','funnel_orders_count','finished_orders','is_payed','advertisement')
        value=dict(status='complete',period_from=str(first),period_to=str(last),observed_at=now.isoformat(),source_key=key,
                   rows=[{k:r.get(k) for k in fields} for r in rows],source='validated MPStats whole-cabinet period',wb_writes=0)
        io.put(key,value);return value
    except Exception as exc:
        io.put(key,dict(status='unavailable',at=now.isoformat(),error=type(exc).__name__,wb_writes=0))
        return None

def compare(event,before,after,required_to):
    changed=str(changed_day(event))
    base=dict(excluded_at=event['started_at'],event_id=event['event_id'],requires_new_confirmation=True,causality='not_established')
    if not before or not after:return dict(base,status='missing_period')
    if (date.fromisoformat(before['period_to'])>=date.fromisoformat(changed)
        or date.fromisoformat(after['period_from'])<=date.fromisoformat(changed)
        or (date.fromisoformat(before['period_to'])-date.fromisoformat(before['period_from'])).days!=3
        or (date.fromisoformat(after['period_to'])-date.fromisoformat(after['period_from'])).days!=3):
        return dict(base,status='invalid_period')
    b,a=funnel(before['row']),funnel(after['row'])
    if b is None or a is None:return dict(base,status='missing_counts')
    adequate=b['views']>=100 and a['views']>=100 and a['orders']>=5
    improved=a['cr_pct']>b['cr_pct']
    return dict(base,status='improved' if improved and adequate else 'small_sample' if improved else 'not_improved',
                before=dict(b,period_from=before['period_from'],period_to=before['period_to'],source=before.get('source')),
                after=dict(a,period_from=after['period_from'],period_to=after['period_to'],source=after.get('source')),
                fresh_complete=after['period_to']==required_to,delta_pp=a['cr_pct']-b['cr_pct'])

def evidence(io,s,collect_latest=True):
    from china_experience import read_rows,ROOT
    events=read_rows(io,ROOT,limit=5000);latest={}
    for entry in events:
        e=entry['payload']
        if e.get('record_type')!='verified_action' or e.get('action',{}).get('kind')!='sku_exclusion' or not e.get('started_at'):continue
        for n in e['action'].get('nm_ids',[]):
            if n not in latest or e['started_at']>latest[n]['started_at']:latest[n]=e
    end=date.fromisoformat(s['period_to']);current=None;cache={}
    for lag in range(3):
        last=end-timedelta(days=lag);first=last-timedelta(days=3)
        current=period(io,first,last,collect=collect_latest and lag==0)
        if current:break
    out={}
    for n,e in latest.items():
        changed=changed_day(e);first=changed-timedelta(days=4);last=changed-timedelta(days=1)
        key=(str(first),str(last))
        if key not in cache:cache[key]=period(io,first,last)
        b=cache[key]
        def selected(p):
            if not p:return None
            matches=[r for r in p['rows'] if int(r['nm_id'])==int(n)]
            if len(matches)!=1:return None
            return dict(p,row=matches[0],source=p.get('source_key') or p.get('snapshot_id'))
        out[str(n)]=compare(e,selected(b),selected(current),str(end))
    return out

def attach(io,s):
    s['retest_evidence']=evidence(io,s)
    return s

def assess(s,nm_ids=(),manual_review=False):
    from china_experience import assess_candidate
    active={n['nm_id'] for c in s['campaigns'].values() if c.get('status',9)==9 for n in c.get('nm_settings',[])}
    recent=set(s['experience'].get('recent_changed_nm_ids',[]));protected=set(s.get('protected',[]))
    prices={p['nmID']:p for p in s['prices']};stocks={};orders={}
    for st in s['stock']:
        if st.get('article'):stocks.setdefault(st['article'].casefold(),[]).append(st)
    for row in s['orders']:
        try:order_day=datetime.fromisoformat(row['createdAt'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
        except (KeyError,ValueError,TypeError):continue
        if not s.get('period_to') or order_day>s['period_to']:continue
        orders[row['nmId']]=orders.get(row['nmId'],0)+1
    result=[]
    for row in s['products']:
        n=int(row['nm_id'])
        if nm_ids and n not in nm_ids or n in active:continue
        p=prices.get(n);stock=stocks.get(row['sa_name'].casefold(),[]);log=s['policy']['logistics_by_nm'].get(str(n))
        if not p or len(stock)!=1 or not log:continue
        st=stock[0];f,paid=row.get('finished_orders'),row.get('is_payed')
        counts=funnel(row)
        if counts is None or not finite(f) or f<3 or not finite(paid) or not 0<=paid<=f:continue
        if not all(finite(st.get(k)) for k in ('stock','reserve','price')):continue
        free=st['stock']-st['reserve'];price=p['sizes'][0]['discountedPrice']
        if not finite(price) or price<=0:continue
        ratio=(row.get('price_after_spp') or 0)/(row.get('price_after_discount') or 1)
        if free<5 or ratio<=0:continue
        # Existing owner's scenario and cost model; not closed net profit.
        expected=paid/f*(price*12*(1-.20-.05*ratio)-st['price']/100)-log['delivery_cny']*12-10-.05*price*12
        if expected<=0:continue
        history=assess_candidate(s['experience'].get('experiences',[]),n,dict(seller_price=price,stock_available=free,rating=row.get('commentsvaluation')))
        retest=(s.get('retest_evidence') or {}).get(str(n));has_history=bool(retest) or n in protected or finite(row.get('advertisement')) and row['advertisement']>0
        needs_retest=bool(retest) or n in protected or has_history and not manual_review
        reasons=[]
        if n in NEVER_AUTORETEST:reasons.append('Отдельный запрет владельца')
        if n in recent:reasons.append('Недавнее изменение: нужны полные сопоставимые дни')
        if history['needs_review']:reasons.append('Не разобрана причина прежнего финансового убытка')
        if needs_retest and (not retest or retest.get('status')!='improved'):reasons.append('Не подтверждено улучшение конверсии после отключения')
        if needs_retest and retest and not retest.get('fresh_complete'):reasons.append('Нужен последний полный период конверсии')
        if row.get('advertisement') is None:reasons.append('Не подтверждена история рекламных расходов')
        group='orders' if orders.get(n,0)>0 else 'demand'
        if not has_history and (counts['cr_pct']<(1 if group=='orders' else .5) or group=='orders' and f<5):reasons.append('Малая конверсия/выборка нового теста')
        bid=s['policy'].get('category_minimum_minor',{}).get(str(row.get('subject_id')))
        if type(bid) is not int:reasons.append('Не подтверждена минимальная ставка')
        result.append(dict(nm_id=n,article=row['sa_name'],subject_id=row.get('subject_id'),bid_minor=bid,stock=free,paid=paid,finished=f,
                           conversion=round(counts['cr_pct'],2),recent_orders=orders.get(n,0),expected_rub_per_order=round(expected,2),
                           price_cny=price,history_advertisement=row.get('advertisement'),memory_event_ids=history['event_ids'],memory_used=True,
                           group=group,retest=retest,requires_review=reasons,eligible=not reasons,wb_writes=0))
    return result
