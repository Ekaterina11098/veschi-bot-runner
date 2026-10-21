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


# Owner-approved compact daily tables. Reads only retained exact-day observations.
def _number(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0

def render_daily_tables(view,limit=3800):
    """Campaign totals include associated orders once; SKU metrics remain direct."""
    import html
    def rub(v):return format(v,',.0f').replace(',',' ')
    def pct(v):return format(v,'.2f').replace('.',',')+'%'
    def split_table(title,header,rows,footer):
        result=[];current=title+'\n\n'+header
        for line in rows:
            if len(current)+len(line)+len(footer)+5>limit:
                result.append('<pre>'+html.escape(current)+'</pre>')
                current=title+' (продолжение)\n\n'+header
            current+='\n'+line
        result.append('<pre>'+html.escape(current+'\n\n'+footer)+'</pre>')
        # Telegram limits parsed text, not the escaped HTML representation.
        if any(len(html.unescape(x[5:-6]))>4096 for x in result):raise ValueError('Oversize Telegram table')
        return result
    period=view['period'];campaigns=sorted(view['campaigns'],key=lambda x:x['campaign_id'])
    lines=[];blines=[]
    for c in campaigns:
        cid=str(c['campaign_id']);cost=c.get('spend');amount=c.get('revenue')
        if not c.get('metrics_complete'):value='Нет данных';note='Нет полного среза за период'
        elif cost==0:value='Нет расхода';note='Заказов нет' if not amount else 'Без рекламного расхода'
        elif amount and amount>0:value=pct(100*cost/amount);note='Превышений нет'
        else:value='Без заказов';note='Потрачено '+rub(cost)+' ₽'
        above=c.get('above5') or []
        if above:note=above[0]['article']+' — '+pct(above[0]['drr'])
        elif c.get('direct_orders')==0 and _number(cost) and cost>0:note='Без прямых заказов; '+rub(cost)+' ₽'
        elif c.get('metrics_complete') and c.get('sku_order_basis')!='direct_only':
            note='Поартикульный прямой ДРР неизвестен'
        if c.get('status_id')==11:note+='; РК приостановлена'
        lines.append(cid+' │ '+value.ljust(13)+' │ '+note)
        for item in above[1:]:lines.append('         │               │ '+item['article']+' — '+pct(item['drr']))
        if above and c.get('within5_count'):lines.append('         │               │ Остальные с ДРР — до 5%')
        b=c.get('budget') or {};stamp=b.get('observed_at');stamp_dt=None
        try:stamp_dt=datetime.fromisoformat(stamp.replace('Z','+00:00')).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow'))
        except (TypeError,ValueError,AttributeError):pass
        balance=b.get('balance');known=_number(balance) and b.get('valid') and stamp_dt is not None
        when=stamp_dt.strftime('%d.%m %H:%M') if known else 'неизвестно'
        capacity='Нет оценки'
        if c.get('status_id')==11:capacity='Приостановлена'
        elif not known:capacity='Баланс неизвестен'
        elif not b.get('today_observation'):capacity='Исторический баланс'
        elif not c.get('metrics_complete'):capacity='Расход за день неполный'
        elif cost==0:capacity='Нет расхода'
        elif cost<10:capacity='Слишком малый расход'
        elif _number(cost) and cost>0:
            hours=balance/cost*24
            capacity=('≈ '+format(hours,'.1f').replace('.',',')+' ч') if hours<24 else ('≈ '+format(hours/24,'.1f').replace('.',',')+' дн.')
        blines.append(cid+' │ '+(rub(balance)+' ₽' if known else 'Неизвестен').rjust(9)+' │ '+when+' │ '+capacity)
    first=split_table('Реклама за '+period+' · цель ДРР до 5%',
      'РК       │ ДРР РК        │ Выше 5% по артикулам',lines,
      'ДРР РК — с подтверждённым посткликом, уже включённым в итог один раз. По артикулам — прямой ДРР; постклик не распределён без подтверждения. «Превышений нет» — только среди товаров с рассчитанным ДРР. Нет заказов или данных — не норма.')
    second=split_table('Бюджеты · наблюдения '+view['observed_day']+' · время МСК',
      'РК       │ Баланс    │ Дата, время │ На сколько хватит',blines,
      'Оценка = баланс на момент наблюдения / суточный расход '+period+'. Это условный срок при сохранении темпа, не гарантия. Последующий расход не вычтен. При малом расходе оценка неустойчива. Для исторического баланса, неизвестного расхода и приостановленной РК срок не рассчитывается.')
    return [dict(kind='drr',text=t) for t in first]+[dict(kind='budgets',text=t) for t in second]

def no_order_spend_summary(p):
    """SKU with positive spend and zero DIRECT orders; unknown is never zero."""
    unknown=dict(no_order_count=None,no_order_spend=None)
    if p.get('sku_order_basis')!='direct_only':return unknown
    rows=p.get('rows') or []
    if not rows:
        return dict(no_order_count=0,no_order_spend=0) if (p.get('totals') or {}).get('ac_spending_sum')==0 else unknown
    grouped={}
    for r in rows:
        cost=r.get('ac_spending_sum');orders=r.get('ac_orders');nm=r.get('nm_id')
        if not _number(cost) or cost<0:return unknown
        if cost==0 and nm is None:continue
        if nm is None or not _number(orders) or orders<0:return unknown
        old=grouped.setdefault(nm,[0,0]);old[0]+=cost;old[1]+=orders
    selected=[v[0] for v in grouped.values() if v[0]>0 and v[1]==0]
    return dict(no_order_count=len(selected),no_order_spend=sum(selected))

def load_daily_table_view(store,now):
    """One bounded exact-day report query; no WB/MPStats requests or cache TTL."""
    from datetime import timedelta
    from analytics.payload_storage import decode_rows
    from business_agents.data import Data
    from zoneinfo import ZoneInfo
    now=now.astimezone(ZoneInfo('Europe/Moscow'));day=str(now.date()-timedelta(days=1))
    rows=store.db('GET','analytics_snapshots',params={'source':'eq.advertising_active_configuration','cabinet':'eq.token_2','select':'id,payload,collected_at','order':'id.desc','limit':1}) or []
    cfg=rows[0]['payload'] if rows else {}
    if isinstance(cfg,list):cfg=cfg[0] if cfg else {}
    active=cfg.get('campaign_ids') or []
    if not active:raise RuntimeError('Current approved campaign scope missing')
    overview=store.cache_get('advertising:ip:daily-overview-scope:v1') or {}
    if overview.get('cabinet')=='token_2' and overview.get('chat_id')==store.registration()['chat_id']:
        active=sorted(set(active)|set(overview.get('campaign_ids') or []))
    # Bounded normalized catalog reads, never reread the large entire report index.
    catrows=decode_rows(store.db('GET','analytics_snapshots',params={'source':'eq.mpstats_campaign_catalog','cabinet':'eq.token_2','select':'id,payload,collected_at','order':'id.desc','limit':8}) or [])
    catalogs=[p for snap in catrows for p in (snap.get('payload') or []) if isinstance(p,dict)]
    mapping={};states={};mpbudgets={}
    for cat in sorted(catalogs,key=lambda x:x.get('observed_at') or ''):
        for row in cat.get('rows') or []:
            if row.get('wb_id') not in active:continue
            cid=row['wb_id'];mapping[cid]=row['id']
            if row.get('status_id') is not None:states[cid]=row['status_id']
            if _number(row.get('current_budget')) and row.get('current_budget_updated_at'):
                mpbudgets[cid]=dict(balance=row['current_budget'],observed_at=row['current_budget_updated_at'],valid=True,source='MPStats')
    week_start=str(now.date()-timedelta(days=7));week_end=day
    weekly_pages={}
    for cat in sorted(catalogs,key=lambda x:x.get('observed_at') or '',reverse=True):
        if cat.get('report')=='stats' and cat.get('period_from')==week_start and cat.get('period_to')==week_end:
            weekly_pages.setdefault(cat.get('start_row'),cat)
    week_rows=[r for _,cat in sorted(weekly_pages.items()) for r in cat.get('rows') or []]
    week_complete=bool(weekly_pages.get(0)) and len(week_rows)==weekly_pages[0].get('total') and len({r.get('id') for r in week_rows})==len(week_rows)
    weekly={r['wb_id']:r.get('ac_spending_sum') for r in week_rows if r.get('wb_id') in active and _number(r.get('ac_spending_sum'))} if week_complete else {}
    snaps=decode_rows(store.db('GET','analytics_snapshots',params={'source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','period_from':'eq.'+day,'period_to':'eq.'+day,'select':'id,payload,collected_at','order':'id.desc','limit':100}) or [])
    reports={}
    for snap in snaps:
        for p in snap.get('payload') or []:
            if p.get('report')=='products' and p.get('scope_nm_id') is None and p.get('spending_reconciled') is True and p.get('period_from')==day and p.get('period_to')==day:
                reports.setdefault(p['campaign_id'],dict(p,snapshot_id=snap['id']))
    missing={mapping[cid] for cid in active if cid in mapping and mapping[cid] not in reports}
    if missing:
        alternatives=decode_rows(store.db('GET','analytics_snapshots',params={'source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','period_from':'eq.'+day,'period_to':'eq.'+day,'payload->0->>report':'eq.days','select':'id,payload,collected_at','order':'id.desc','limit':100}) or [])
        for snap in alternatives:
            for p in snap.get('payload') or []:
                if p.get('campaign_id') not in missing or p.get('scope_nm_id') is not None or p.get('spending_reconciled') is not True:continue
                values=p.get('rows') or []
                if len(values)==1 and values[0].get('date')==day and all(_number(values[0].get(k)) for k in ('ac_spending_sum','ac_orders','ac_orders_sum')):
                    aggregate=dict(p,snapshot_id=snap['id'],rows=[],sku_order_basis='aggregate_only')
                    if values[0]['ac_spending_sum']==0 and values[0]['ac_orders']==0:aggregate['sku_order_basis']='direct_only'
                    reports.setdefault(p['campaign_id'],aggregate)
    cards=Data('operations',lambda t,p:store.db('GET',t,params=p)).snapshot('cards','token_2')
    articles={int(x['nmID']):x['vendorCode'] for x in cards.get('rows',[]) if x.get('nmID') and x.get('vendorCode')}
    bsnaps=decode_rows(store.db('GET','analytics_snapshots',params={'source':'eq.advertising_campaign_budgets','cabinet':'eq.token_2','select':'id,payload,collected_at','order':'id.desc','limit':1}) or [])
    bp=bsnaps[0]['payload'] if bsnaps else {}
    if isinstance(bp,list):bp=bp[0] if bp else {}
    wb={x['campaign_id']:x for x in bp.get('items',[])}
    result=[]
    for cid in sorted(active):
        p=reports.get(mapping.get(cid),{});t=p.get('totals') or {}
        valid=bool(p) and all(_number(t.get(k)) for k in ('ac_spending_sum','ac_orders_sum','ac_orders'))
        above=[];within=0
        no_orders=no_order_spend_summary(p)
        if p.get('sku_order_basis')=='direct_only':
            for r in p.get('rows') or []:
                spend=r.get('ac_spending_sum');rev=r.get('ac_orders_sum')
                if _number(spend) and _number(rev) and rev>0 and _number(r.get('ac_orders')) and r['ac_orders']>0:
                    drr=100*spend/rev
                    if drr>5:above.append(dict(article=articles.get(r.get('nm_id')) or 'Артикул неизвестен (nm'+str(r.get('nm_id'))+')',drr=drr))
                    else:within+=1
        options=[mpbudgets[cid]] if cid in mpbudgets else []
        w=wb.get(cid,{})
        if _number(w.get('total')) and w.get('observed_at') and (w.get('available') or w.get('stale')) and not w.get('error'):
            options.append(dict(balance=w['total'],observed_at=w['observed_at'],valid=True,source='WB'))
        budget={}
        for candidate in options:
            try:
                stamp=datetime.fromisoformat(candidate['observed_at'].replace('Z','+00:00'))
                if stamp>now:continue
                candidate=dict(candidate,today_observation=stamp.astimezone(now.tzinfo).date()==now.date())
                if not budget or stamp>datetime.fromisoformat(budget['observed_at'].replace('Z','+00:00')):budget=candidate
            except (TypeError,ValueError):continue
        result.append(dict(campaign_id=cid,metrics_complete=valid,spend=t.get('ac_spending_sum') if valid else None,revenue=t.get('ac_orders_sum') if valid else None,
          direct_orders=(t['ac_orders']-t['ac_orders_associated']) if valid and _number(t.get('ac_orders_associated')) and t['ac_orders']>=t['ac_orders_associated'] else None,
          above5=sorted(above,key=lambda x:-x['drr']),within5_count=within,**no_orders,sku_order_basis=p.get('sku_order_basis'),status_id=states.get(cid),budget=budget,source_snapshot_id=p.get('snapshot_id'),weekly_spend=weekly.get(cid)))
    return dict(period=day,observed_day=str(now.date()),campaigns=result,weekly_period_from=week_start,weekly_period_to=week_end)

def deliver_daily_tables(store,messages,chat,day,send):
    """Durable claim before each request. An uncertain result is never retried."""
    import hashlib,copy
    receipts=[]
    for i,msg in enumerate(messages,1):
        key='advertising:ip:daily-tables:v1:'+day+':'+str(i)
        digest=hashlib.sha256(msg['text'].encode()).hexdigest()
        rows=store.db('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload,updated_at','limit':1}) or []
        if rows:
            old=rows[0]['payload']
            if old.get('status')=='confirmed':
                receipts.append(old);continue
            raise RuntimeError('Prior table delivery uncertain; no blind retry')
        now=datetime.now(timezone.utc)
        from datetime import timedelta
        claim=dict(status='uncertain',chat_id=chat,sha256=digest,kind=msg['kind'],part=i,at=now.isoformat())
        body=dict(cache_key=key,payload=claim,updated_at=now.isoformat(),expires_at=(now+timedelta(days=365)).isoformat())
        saved=store.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body=body,prefer='resolution=ignore-duplicates,return=representation') or []
        if len(saved)!=1 or store.cache_get(key)!=claim:raise RuntimeError('Table claim conflict')
        receipt=send(chat,msg['text'])
        if not receipt.get('ok') or receipt.get('chat_id')!=chat or type(receipt.get('message_id')) is not int:raise RuntimeError('Unconfirmed table receipt; no retry')
        value=dict(claim,status='confirmed',message_id=receipt['message_id'],confirmed_at=datetime.now(timezone.utc).isoformat())
        for field in ('media_sha256','photo_file_unique_id'):
            if receipt.get(field):value[field]=receipt[field]
        store.cache_set(key,value,ttl_days=365)
        if store.cache_get(key)!=value:raise RuntimeError('Table receipt readback mismatch')
        receipts.append(value)
    return receipts


