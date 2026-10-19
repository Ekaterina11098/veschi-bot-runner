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

def render(answer, mode, review, day):
    up=raising(answer,mode);down=lowering(review,day)
    def section(title,rows):
        if rows is None:return title+'\nНет данных'
        return title+'\n'+('\n'.join(a+': '+old+' → '+new+' ¥' for a,old,new in rows) if rows else 'Нет')
    return section('Повышение:',up)+'\n\n'+section('Снижение:',down)
