"""Explain only arithmetic supported by the exact parent's retained daily funnel."""
import re
from datetime import date


def explain(text, marker, history):
    if not re.search(r'почему|причин',text,re.I):return None
    parent=marker.get('parent_job_id')
    selected=[h for h in history if h.get('id')==parent] if parent else history[-1:]
    events=[(h,e) for h in selected for e in h.get('tool_trace') or []
            if e.get('name') in ('saved_conversion_history','saved_conversion_explanation')]
    if not events:
        if re.search(r'конверс',text,re.I):return ('Ответьте на сообщение с дневной воронкой нужного товара: без подтверждённого товара и периода объяснение не сформировано. Причина снижения не установлена.',[])
        return None
    h,event=events[-1];value=event.get('result') or {};args=event.get('arguments') or {}
    article=args.get('article');nm=str(args.get('nm_id',''))
    # Explicit reply must resolve to the exact stored job, never quoted text alone.
    if marker.get('reply_message_id') and not parent:return ('Не удалось подтвердить исходный отчёт по этому ответу. Укажите товар и период; причины не установлены.',[])
    rows=value.get('daily') or []
    try:
        start=date.fromisoformat(value['date_from']);end=date.fromisoformat(value['date_to'])
        valid=(value.get('source')=='MPStats' and value.get('cabinet')=='Китай' and value.get('article')==article
               and value.get('complete') is True and len(rows)==(end-start).days+1 and len(rows)>=2
               and len({r['date'] for r in rows})==len(rows))
        for r in rows:
            valid=valid and start<=date.fromisoformat(r['date'])<=end and str(r.get('nm_id'))==nm and r.get('article')==article and r.get('cabinet')=='token_3'
            valid=valid and all(type(r.get(k)) is int and r[k]>=0 for k in ('views','orders'))
        if not valid:raise ValueError('Daily evidence incomplete or scope mismatch')
    except (KeyError,ValueError,TypeError):
        return ('Дневные данные исходного ответа неполны или не подтверждены для одного товара и периода. Снижение и его причины по ним не установлены; пропуски не считаются нулями.',[])
    rows=sorted(rows,key=lambda r:r['date']);first,previous,last=rows[0],rows[-2],rows[-1]
    pct=lambda n:f'{n:.2f}'.replace('.',',')
    short=lambda d:date.fromisoformat(d).strftime('%d.%m')
    lines=[article+' · '+value['date_from']+'–'+value['date_to']+' · Китай',
           'Разберу, из каких цифр получилось изменение конверсии.']
    def comparison(a,b,title):
        result=[title+' ('+short(a['date'])+' → '+short(b['date'])+'):',
                f"Просмотры: {a['views']} → {b['views']}. Заказы воронки: {a['orders']} → {b['orders']}."]
        if not a['views'] or not b['views']:
            result.append('Конверсию сравнить нельзя: в одном из дней нет просмотров.');return result
        old,new=100*a['orders']/a['views'],100*b['orders']/b['views'];delta=new-old
        result.append('Конверсия: '+pct(old)+'% → '+pct(new)+'% ('+('+' if delta>0 else '')+pct(delta)+' п.п.).')
        if b['views']>a['views'] and b['orders']<a['orders']:
            result.append('Просмотров стало больше, а заказов меньше — поэтому отношение заказов к просмотрам снизилось. Это дневные итоги, а не путь одних и тех же покупателей.')
        elif new<old:result.append('Заказы на один просмотр сократились. Само изменение процента не устанавливает поведение каждого покупателя.')
        elif new>old:result.append('На этом сравнении доля заказов выросла; снижение здесь не подтверждается.')
        else:result.append('На этом сравнении доля заказов не изменилась.')
        return result
    lines+=comparison(previous,last,'Последние два дня')
    if first['date']!=previous['date']:lines+=['']+comparison(first,last,'От начала к концу периода')
    orders=[r['orders'] for r in rows]
    lines+=['',f"За день было от {min(orders)} до {max(orders)} заказов воронки. При таких количествах разница в несколько заказов заметно меняет процент. Один этот срез не доказывает устойчивое ухудшение.",
            'Вывод: сохранённая воронка показывает изменение просмотров и заказов. Почему покупатели реже оформляли заказ, этими данными не установлено. Связь с ценой, рекламой, фото или доставкой в этом срезе не проверена — приписывать им причину нельзя.',
            'Источник: сохранённая дневная воронка MPStats. Это заказы воронки, не фактические продажи WB. Новые сборы и изменения не запускались.']
    return '\n'.join(lines),[{'name':'saved_conversion_explanation','arguments':{'article':article,'nm_id':nm,'parent_job_id':h['id']},'result':value}]
