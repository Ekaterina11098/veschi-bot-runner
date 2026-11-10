"""Read-only maintenance reports. No model calls, approvals, or marketplace writes."""
import math,os,re,time
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
CHAT=-1004342917488
ROOT='china_agent:free_drr:v1:'

def intent(text):
    if re.search(r'блокировк|(?:минимальн\w*\s+цен|минимум\w*\s+(?:цен|для\s+автоакц))',text,re.I):
        if not re.search(r'безубыточ|себестоим',text,re.I) and re.search(r'блокировк|автоакц|сделай|свер|установ|проверь',text,re.I):return 'minimums'
    acquisition=re.search(r'кандидат|добав|нов\w*\s+рк|тест',text,re.I)
    maintenance=re.search(r'отсеч|исключ|убер|дорог|сниз|пониз|вырос|больш|высок|отключ',text,re.I)
    if acquisition and not maintenance:return None
    if re.search(r'дрр|ддр|дорог\w*.*реклам|реклам.*дорог',text,re.I) and re.search(r'больш|высок|вырос|рост|дорог|отсеч|исключ|убер|сниз|пониз|покаж|посмотр|какие',text,re.I):
        return 'drr'
    if re.search(r'почему\s+недоступ|почему\s+нет\s+данных|почему.*экономик|экономик.*(?:недоступ|ошиб)|(?:статус|источник|покрыти).*экономик',text,re.I):return 'coverage'
    return None

def allowed_read(method,url,body=None):
    p=urlparse(url)
    return method.upper()=='GET' and p.scheme=='https' and p.hostname=='advert-api.wildberries.ru' and p.path in (
        '/adv/v1/promotion/count','/api/advert/v2/adverts','/adv/v3/fullstats')

def window(w,text):
    today=w.now.astimezone(MSK).date()
    dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
    if dates:
        if len(dates)>2:raise ValueError('Укажите один период')
        first=datetime.fromisoformat(dates[0]).date();last=datetime.fromisoformat(dates[-1]).date()
    elif re.search(r'сегодня',text,re.I):first=last=today
    else:
        m=re.search(r'(\d+)\s*(?:полн\w*\s*)?дн',text,re.I)
        days=int(m[1]) if m else 7 if re.search(r'недел',text,re.I) else 1 if re.search(r'вчера',text,re.I) else 3
        last=today-timedelta(days=1);first=last-timedelta(days=days-1)
    if not today-timedelta(days=60)<=first<=last<=today or (last-first).days>13:
        raise ValueError('Поддерживается от 1 до 14 дней, без будущих дат')
    return first,last

def finite(v):return type(v) in (float,int) and math.isfinite(v) and v>=0

def aggregate(inventory,campaigns,stats,labels,first,last):
    rows={};received=set();invalid=0
    for campaign in stats:
        cid=campaign.get('advertId')
        if cid not in inventory:raise ValueError('Неизвестная РК в ответе WB')
        currency=campaign.get('currency') or campaigns.get(cid,{}).get('currency')
        if currency!='CNY':raise ValueError('Валюта рекламных сумм не подтверждена как CNY')
        if cid in received:raise ValueError('Повторная РК в статистике')
        received.add(cid)
        for day in campaign.get('days',[]):
            date=day.get('date','')[:10]
            if not str(first)<=date<=str(last):raise ValueError('Статистика за пределами периода')
            for app in day.get('apps',[]):
                for n in app.get('nms',[]):
                    nm=n.get('nmId');spend,amount,orders=n.get('sum'),n.get('sum_price'),n.get('orders')
                    if type(nm)is not int or not all(finite(v) for v in (spend,amount,orders)) or orders!=int(orders):
                        invalid+=1;continue
                    key=(cid,nm)
                    row=rows.setdefault(key,dict(campaign_id=cid,nm_id=nm,article=labels.get(str(nm),'nmID '+str(nm)),spend=0,amount=0,orders=0))
                    row['spend']+=spend;row['amount']+=amount;row['orders']+=int(orders)
    values=list(rows.values());spend=sum(r['spend']for r in values);amount=sum(r['amount']for r in values)
    for row in values:
        row['drr_pct']=100*row['spend']/row['amount'] if row['amount'] and row['orders'] else None
        row['cpa_cny']=row['spend']/row['orders'] if row['orders'] else None
        row['excess_at_5pct']=row['spend']-.05*row['amount']
        row['drr_without_row']=100*(spend-row['spend'])/(amount-row['amount']) if amount>row['amount'] else None
    # Show the contributors to overall expense, not tiny rows with the largest %.
    values.sort(key=lambda r:(r['excess_at_5pct'],r['spend']),reverse=True)
    return dict(rows=values,spend=spend,amount=amount,drr_pct=100*spend/amount if amount else None,
                missing_campaign_ids=sorted(set(inventory)-received),invalid_rows=invalid,
                period_from=str(first),period_to=str(last),currency='CNY',wb_writes=0,paid_model_calls=0)

def collect(w,text):
    import requests
    first,last=window(w,text);key=ROOT+str(first)+':'+str(last)
    cached=w.get(key)
    if cached and 0<=(w.now-datetime.fromisoformat(cached['observed_at'])).total_seconds()<300:return cached
    token=os.environ['WB_TOKEN_3']
    def get(path,params=None):
        time.sleep(1.3)
        r=requests.get('https://advert-api.wildberries.ru'+path,headers={'Authorization':token},params=params,timeout=55)
        if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code))
        return r.json()
    catalog=get('/adv/v1/promotion/count');inventory={}
    if not isinstance(catalog.get('adverts'),list):raise ValueError('Не получен полный каталог рекламных кампаний')
    for group in catalog.get('adverts',[]):
        if group.get('status')==4:continue  # Never-launched drafts cannot spend.
        for a in group.get('advert_list',[]):
            if type(a.get('advertId'))is not int or a['advertId']<=0:raise ValueError('Не подтверждён ID РК')
            inventory[a['advertId']]=group.get('status')
    if len(inventory)>200:raise ValueError('Каталог РК превышает границу отчёта; нужен отдельный полный сбор')
    campaigns={};stats=[]
    ids=sorted(inventory)
    last_stats=None
    for start in range(0,len(ids),50):
        chunk=ids[start:start+50]
        details=get('/api/advert/v2/adverts',dict(ids=','.join(map(str,chunk))))
        for c in details.get('adverts',[]):
            if c.get('id')not in chunk:raise ValueError('Подмена РК в каталоге')
            campaigns[c['id']]=c
        if last_stats is not None:
            delay=21-(time.monotonic()-last_stats)
            if delay>0:time.sleep(delay)
        last_stats=time.monotonic()
        data=get('/adv/v3/fullstats',dict(ids=','.join(map(str,chunk)),beginDate=str(first),endDate=str(last)))
        if not isinstance(data,list):raise ValueError('WB не вернул полный массив статистики')
        stats.extend(data)
    result=aggregate(inventory,campaigns,stats,dict(w.catalog()),first,last)
    result.update(observed_at=w.now.isoformat(),source='WB fullstats, SKU/app; all historical campaign statuses except drafts')
    w.save(key,result);return result

def drr_answer(w,text):
    data=collect(w,text)
    def num(v):return 'нет данных' if v is None else f'{v:.2f}'
    overall=(num(data['drr_pct'])+'%') if data['drr_pct'] is not None else 'не определён'
    lines=[f'Реклама Китая · {data["period_from"]}–{data["period_to"]} · срез {data["observed_at"][:16]} UTC.',
           f'По полученным строкам: расход {data["spend"]:.2f} CNY, сумма рекламных заказов {data["amount"]:.2f} CNY; ДРР {overall}.',
           '| Артикул / РК | Расход CNY | Заказы | ДРР % | CPA CNY | Избыток расхода над 5% | Действие |',
           '|---|---:|---:|---:|---:|---:|---|']
    ranked=[r for r in data['rows']if r['spend']>0 and (r['drr_pct'] is None or r['excess_at_5pct']>0)]
    for r in ranked[:12]:
        label=r['article'].replace('|','/')
        lines.append(f'| {label} / {r["campaign_id"]} | {r["spend"]:.2f} | {r["orders"]} | {num(r["drr_pct"])} | {num(r["cpa_cny"])} | {r["excess_at_5pct"]:.2f} | Нет |')
    if not ranked:lines.append('В полученных строках нет расхода выше ориентира 5%; это не проверка прибыльности.')
    if data['missing_campaign_ids'] or data['invalid_rows']:
        lines.append(f'Покрытие неполное: без строк WB — {len(data["missing_campaign_ids"])} РК; неполных строк — {data["invalid_rows"]}. Пропуски не нули; итог относится только к полученным данным.')
    if data['period_to']==str(w.now.astimezone(MSK).date()):lines.append('Сегодня день неполный; его нельзя использовать как завершённое окно для снижения или исключения.')
    lines.append('Ранжирование по вкладу в лишний расход относительно ДРР 5%, а не только по максимальному проценту. При нуле заказов ДРР и CPA не определены. Это рекламная атрибуция WB, не общая конверсия и не закрытая прибыль.')
    lines.append('Ничего не исключено, ставки не менялись. До конкретного изменения нужно проверить завершённые дни после последнего изменения и текущую экономику. Запрос на дорогие товары не создаёт новый рекламный тест.')
    return '\n'.join(lines)

def minimum_answer(w,text):
    found=w.db('GET','telegram_api_cache',params={'cache_key':'like.china_agent:price_execution:v1:-1004342917488:*',
        'payload->minimum_prices':'not.is.null','payload->>status':'eq.done','select':'cache_key,payload,updated_at','order':'updated_at.desc','limit':1})or[]
    if not found:return 'Не найдена подтверждённая обычная цена с требованиями к минимумам. Установку минимумов и сохранение блокировок не подтверждаю.'
    record=found[0];state=record['payload']['minimum_prices']
    lines=['Минимумы автоакций · последняя запись '+record['updated_at'][:16]+' UTC.',
           '| Артикул | Требуемый минимум CNY | Проверка WB |','|---|---:|---|']
    for r in state.get('rows',[]):
        lines.append('| '+str(r.get('article','nmID '+str(r.get('nm_id')))).replace('|','/')+' | '+str(r.get('minimum_cny','нет данных'))+' | '+('Есть сохранённая квитанция' if state.get('minimums_wb_verified') else 'Не подтверждена')+' |')
    lines.append('Это требования после изменения обычной цены. Обычная ценовая квитанция не подтверждает минимум автоакций или сохранение блокировок.')
    if not state.get('minimums_wb_verified'):
        lines.append('Автоматическая установка не выполнена: проверенный маршрут здесь — официальный шаблон кабинета WB. Без выгрузки/readback минимумов, сроков и блокировок писать «сделано» нельзя. Сохранённые блокировки не менялись этим запросом.')
    return '\n'.join(lines)

def coverage_answer(w):
    today=str(w.now.astimezone(MSK).date());key='china_agent:advertising_full_growth:'+today+':v1:inputs'
    current=w.get(key)
    rows=(current or {}).get('economics',{}).get('rows',{})
    count=len(rows) if isinstance(rows,(dict,list)) else None
    found=w.db('GET','telegram_api_cache',params={'cache_key':'like.china_agent:advertising_full_growth:*:v1:inputs',
        'payload->>cabinet':'eq.token_3','payload->>status':'eq.complete','select':'cache_key,payload,updated_at','order':'updated_at.desc','limit':1})or[]
    if not current:
        text=f'На {today} ещё не сохранён полный дневной срез экономики. Это отсутствие готового среза за дату, а не подтверждённые «0 товаров» или недоступность всей экономики кабинета.'
    else:
        status=current.get('status','не указан')
        text=f'Срез экономики за {today}: статус {status}; строк экономики {count if count is not None else "не определено"}. Неполный сбор не заменяю нулевыми расходами.'
    if found:
        latest=found[0];p=latest['payload'];oldrows=(p.get('economics')or{}).get('rows',{})
        text+=f' Последний полный сохранённый срез: {p.get("observed_at",latest["updated_at"])}; строк экономики {len(oldrows) if isinstance(oldrows,(dict,list)) else "не определено"}. Его дату нужно учитывать, он не становится сегодняшним.'
    return text+' ДРР и расход можно проверять отдельно по рекламной статистике WB; для нового запуска необходима актуальная адресная экономика.'

def handle(w,job,history=()):
    kind=intent(job.get('request_text',''))
    if kind is None:return None
    try:
        answer=drr_answer(w,job['request_text']) if kind=='drr' else minimum_answer(w,job['request_text']) if kind=='minimums' else coverage_answer(w)
        w.save('china_agent:free_diagnostic:v1:'+str(job['id']),dict(kind=kind,status='answered',created_at=w.now.isoformat(),wb_writes=0,paid_model_calls=0))
        return answer
    except (ValueError,RuntimeError,KeyError,TypeError) as exc:
        # Explain the exact failed report, never invent a cabinet-wide outage.
        return ('Не удалось завершить '+{'drr':'расчёт ДРР по WB','minimums':'сверку минимумов и блокировок','coverage':'проверку покрытия экономики'}[kind]+
                ': '+str(exc)+'. Неполные данные не ноль. Изменений и новых рекламных тестов этот запрос не создавал.')
