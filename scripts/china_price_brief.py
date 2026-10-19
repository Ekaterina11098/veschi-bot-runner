"""Compact notifications only; decisions and delivery identities stay in existing workers."""
import re
from decimal import Decimal, InvalidOperation

def price(value):
    try:
        number=Decimal(str(value).replace(',', '.'))
    except InvalidOperation:
        raise RuntimeError('Invalid proposal price')
    if not number.is_finite() or number<=0:
        raise RuntimeError('Invalid proposal price')
    return format(number.normalize(), 'f').replace('.', ',')

def raising(answer, mode):
    number=r'([0-9]+(?:[.,][0-9]+)?)'
    if mode=='morning':
        heading=re.search(r'ПЕРВОЕ ПОВЫШЕНИЕ \+10%: (\d+)', answer)
        if not heading: raise RuntimeError('Missing morning proposal count')
        section=answer.split('Повторное повышение',1)[0]
        pattern=r'(?m)^([^\n]+)\nЗаказы по дням:[^\n]*\nЦена продавца после скидки: '+number+r' → '+number+r' ¥\.'
    else:
        heading=re.search(r'Первое повышение \+10%: (\d+) кандидатов',answer)
        if not heading: raise RuntimeError('Missing intraday proposal count')
        section=answer.split('Ближайшие кандидаты',1)[0]
        pattern=r'(?m)^• ([^:\n]+): заказы [^\n]+\n  Предложение: '+number+r' → '+number+r' ¥ после скидки'
    rows=re.findall(pattern,section)
    if len(rows)!=int(heading[1]) or len({r[0] for r in rows})!=len(rows):
        raise RuntimeError('Proposal count mismatch')
    return [(a,price(old),price(new)) for a,old,new in rows]

def lowering(review, day):
    if (not isinstance(review,dict) or review.get('report_date')!=str(day)
        or review.get('status')!='complete_disclosed_forecast_model'
        or review.get('model_version')!='wb_four_day_baseline_daily_means_v3'):
        return None
    rows=[]
    for item in review['products']:
        if item.get('result',{}).get('status')!='rollback_review':continue
        if item.get('full_days',0)<4:raise RuntimeError('Premature rollback')
        old=price(item['after_price']);new=price(item['before_price'])
        if Decimal(old.replace(',','.'))<=Decimal(new.replace(',','.')):
            raise RuntimeError('Rollback is not a decrease')
        rows.append((item['article'],old,new))
    return sorted(set(rows))

def catalogue_ids(catalogue):
    if not isinstance(catalogue,dict) or catalogue.get('cabinet')!='token_3':
        raise RuntimeError('China catalogue unverified')
    result={}
    for row in catalogue.get('rows',[]):
        article=row.get('vendorCode')
        nm=str(row.get('nmID',''))
        if not article or not nm.isdigit() or int(nm)<=0:
            continue
        key=article.casefold()
        if key in result and result[key]!=nm:
            raise RuntimeError('Ambiguous WB article')
        result[key]=nm
    return result

def article_entities(text):
    """Telegram entity offsets use UTF-16 units, not Python characters."""
    entities=[]
    for match in re.finditer(r'(?m)^Артикул WB: ([0-9]+)$',text):
        start=match.start(1)
        entities.append(dict(type='text_link',url='https://www.wildberries.ru/catalog/'+match[1]+'/detail.aspx',offset=len(text[:start].encode('utf-16-le'))//2,
                             length=len(match[1])))
    return entities

def render(answer, mode, review, day, catalogue, buyer=None):
    up=raising(answer,mode);down=lowering(review,day)
    ids=catalogue_ids(catalogue)
    def row(article,old,new):
        nm=ids.get(article.casefold())
        if not nm:raise RuntimeError('Exact WB article missing')
        text=article+': '+old+' → '+new+' ¥\nАртикул WB: '+nm
        if buyer is not None:
            from china_agent.buyer_price_forecast import forecast
            amount=forecast(buyer,nm,article,old,new,day)
            text+='\nЦена покупателя (прогноз): '+(format(amount,',').replace(',',' ')+' ₽' if amount is not None else 'нет данных')
        return text
    def section(title,rows):
        if rows is None:return title+'\nНет данных'
        return title+'\n'+('\n'.join(row(a,old,new) for a,old,new in rows) if rows else 'Нет')
    return section('Рекомендации к повышению:',up)+'\n\n'+section('Рекомендации к снижению:',down)

def render_table(answer,mode,review,day,catalogue,buyer=None):
    from china_agent.buyer_price_forecast import forecast
    up=raising(answer,mode);down=lowering(review,day)
    ids=catalogue_ids(catalogue)
    headers=['Действие','Арт','Цена продавца, ¥','Цена покупателя, ₽ (новая — прогноз)']
    rows=[]
    for action,offers in (('Повышение',up),('Снижение',down or [])):
        for article,old,new in offers:
            nm=ids.get(article.casefold())
            if not nm:raise RuntimeError('Exact WB article missing')
            if any(c in article for c in ('|','\n','\r')):raise RuntimeError('Invalid table article')
            before=forecast(buyer or {},nm,article,old,old,day)
            after=forecast(buyer or {},nm,article,old,new,day)
            rub=lambda value:'нет данных' if value is None else format(value,',').replace(',',' ')
            rows.append([action,article,old+' → '+new,rub(before)+' → '+rub(after)])
    widths=[max(len(row[i]) for row in [headers]+rows) for i in range(len(headers))]
    def line(row):
        return ' | '.join(value.ljust(widths[i]) if i<2 else value.rjust(widths[i]) for i,value in enumerate(row)).rstrip()
    lines=['Рекомендации по ценам • '+str(day),'',line(headers),
           '-+-'.join('-'*width for width in widths)]+[line(row) for row in rows]
    if not up:lines+=['','Рекомендации к повышению: нет.']
    if down is None:lines+=['','Рекомендации к снижению: нет данных.']
    elif not down:lines+=['','Рекомендации к снижению: нет.']
    return '\n'.join(lines)

def table_payload(text,catalogue):
    """Link each article cell inside the table; no separate navigation keyboard."""
    if not text.startswith('Рекомендации по ценам • ') and not re.search(r'(?m)^(?:Повышение|Снижение)\s+\|',text):return None
    ids=catalogue_ids(catalogue)
    entities=[]
    for match in re.finditer(r'(?m)^(?:Повышение|Снижение)[^\n]*$',text):
        line=match[0];cells=line.split('|')
        if len(cells)!=4:continue
        article=cells[1].strip()
        nm=ids.get(article.casefold())
        if not nm:raise RuntimeError('Table product mapping missing')
        first_pipe=line.index('|')
        cell_start=first_pipe+1
        start=match.start()+cell_start+len(cells[1])-len(cells[1].lstrip())
        entities.append(dict(type='text_link',url='https://www.wildberries.ru/catalog/'+nm+'/detail.aspx',
                             offset=len(text[:start].encode('utf-16-le'))//2,
                             length=len(article.encode('utf-16-le'))//2))
    return dict(entities=entities,reply_markup=dict(inline_keyboard=[]),
                link_preview_options=dict(is_disabled=True))
