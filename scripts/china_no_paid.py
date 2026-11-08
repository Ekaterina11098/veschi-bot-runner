"""Deterministic China bot replies; paid model transport is deliberately blocked."""
import re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo

POLICY='china_agent:no_paid_ai:v1'
CHAT=-1004342917488
BOT=8780468043

def require_paid_api(policy=None):
    raise PermissionError('Paid model API disabled by owner on 8Nov; no request was sent')

def enabled(w):
    p=w.get(POLICY) or {}
    return p.get('enabled') is True and p.get('chat_id')==CHAT and p.get('bot_id')==BOT and p.get('paid_api_allowed') is False

HELP=('Платные обращения к ИИ отключены. Доступны расчёты и отчёты без модели:\n'
      '• «Конверсия сегодня по сравнению с неделей»;\n'
      '• «Конверсия АРТИКУЛ за последние 7 дней»;\n'
      '• «Покажи кандидатов для рекламы»;\n'
      '• «Отчёт по рекламе», «Бюджеты РК», «Результаты изменений»;\n'
      '• «Цены АРТИКУЛ», «Мои задания».\n'
      'Свободный ИИ-анализ в Telegram сейчас недоступен. Более сложный вопрос можно разобрать в этом чате без запуска внешнего API.')

def cells(value):
    return str(value).replace('|','/').replace('\n',' ')

def answer(w,job,history=()):
    text=re.sub(r'^/codex(?:@\w+)?\s*','',job.get('request_text',''),flags=re.I).strip()
    scoped=dict(job,request_text=text)
    if re.fullmatch(r'где\s+прежний\s+агент[?.!]*',text,re.I):
        return 'Отдельного «прежнего агента» нет — я неверно выразился. Пишите этому же боту без /codex. Команды к актуальному PNG передаются на исполнение с проверкой WB. Для нового запуска сначала нужны точные товары, ставки и бюджет; прошлое предложение ещё не подтверждает запуск.'
    from china_free_ads import handle as advertising
    advertising_reply=advertising(w,scoped)
    if advertising_reply is not None:return advertising_reply
    if re.search(r'^(?:/start|/help|помощь|что умеешь)|бесплат|платн|списани',text,re.I):
        return HELP
    from conversion_watches import intent,report
    command=intent(text)
    if command:
        if not w.authorized(job):return 'Управлять заданиями могут только действующие участники этой группы.'
        return w.command(scoped)
    from china_conversion_context import handle as conversion
    reply=conversion(w,scoped,history)
    if reply is not None:return reply[0]
    if re.search(r'конверс',text,re.I) and re.search(r'\d+-[A-Za-z]',text):
        nm,article=w.resolve(text)
        dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
        m=re.search(r'(?:за|последни\w*)\s+(\d+)\s+дн',text,re.I)
        days=int(m[1]) if m else 7
        if not 1<=days<=14:return 'Для истории одного товара укажите от 1 до 14 полных дней.'
        value=w.conversion_history(article,date_from=dates[0] if len(dates)==2 else None,date_to=dates[1] if len(dates)==2 else None,days=days,saved_only=True)
        rows=value.get('daily',[])
        lines=[f'Китай · {article} · {value["date_from"]}–{value["date_to"]} · полные дни',
               '| Дата | Просмотры | Заказы | Конверсия |','|---|---:|---:|---:|']
        for r in rows:
            v,n=r.get('views'),r.get('orders')
            cr=f'{100*n/v:.2f}%' if isinstance(v,(int,float)) and v>0 and isinstance(n,(int,float)) else 'нет данных'
            lines.append(f'| {r["date"]} | {v if v is not None else "нет данных"} | {n if n is not None else "нет данных"} | {cr} |')
        lines.append('Источник: сохранённая дневная воронка MPStats; пропуски не нули. '+('Период полный.' if value.get('complete') else 'Данные периода неполные.'))
        return '\n'.join(lines)
    if re.search(r'кандидат|кого.*реклам|добавить.*реклам|повышен.*став',text,re.I):
        from china_growth_candidates import collect
        scan=collect(w,days=3)
        rows=scan.get('rows',[])
        lines=[f'Кандидаты · {scan.get("period_from","?")}–{scan.get("period_to","?")} · срез {scan.get("observed_at","не указан")}',
               '| Артикул | РК | Предложение | Основание |','|---|---|---|---|']
        for r in rows[:30]:
            action='Добавление' if r.get('kind')=='ad_add_sku' else 'Проверка повышения'
            lines.append('| '+' | '.join(cells(x) for x in [r.get('article'),r.get('campaign_id'),action,r.get('reason','нет подтверждения')])+' |')
        if not rows:return 'По проверенному расчёту за три полных дня готовые кандидаты не получены. Это не доказывает отсутствие других возможностей; изменений нет.'
        lines.append(f'Показано {min(len(rows),30)} из {len(rows)}. Расчёт по правилам, без ИИ; перед исполнением нужны актуальные проверки. Ничего не запускалось.')
        return '\n'.join(lines)
    if re.search(r'безубыточ|минимальн.*цен',text,re.I):
        from china_break_even import answer as break_even
        reply=break_even(w,scoped,history)
        if reply is not None:return reply[0]
    if re.search(r'отч[её]т|бюджет|результат.*изменени',text,re.I):
        from china_agent_reports import make,catalog
        kind=('outcomes' if re.search(r'результат.*изменени',text,re.I) else
              'budgets' if re.search(r'бюджет',text,re.I) else
              'advertising' if re.search(r'реклам|дрр|расход',text,re.I) else None)
        if kind:
            value=make(w,scoped,kind,days=3)
            return value['marker']
        return 'Доступные отчёты:\n'+'\n'.join('• '+v['title'] for v in catalog()['reports'].values())
    if re.search(r'цен',text,re.I) and re.search(r'\d+-[A-Za-z]',text):
        nm,article=w.resolve(text)
        source=w.get('china_agent:prices:v1') or {}
        if source.get('cabinet')!='token_3':return 'Проверенного среза цен Китая нет.'
        rows=[r for r in source.get('rows',[]) if str(r.get('nmID'))==str(nm)]
        if len(rows)!=1:return 'Однозначная сохранённая цена этого варианта не найдена.'
        r=rows[0]
        return f'{article} · nmID {nm}\nЦена: {r.get("price","нет данных")} {r.get("currencyIsoCode4217","")}; скидка продавца: {r.get("discount","нет данных")}%.\nСрез: {source.get("observed_at","не указан")}. Это сохранённые данные, не новая проверка WB. Цена не менялась.'
    return 'Не удалось однозначно понять продолжение. Ответьте на нужное сообщение бота и уточните, что подготовить или проверить. Если подбор уже принят, повторно подтверждать расчёты не нужно.'

def safe_answer(w,job,history=()):
    try:
        result=answer(w,job,history)
        if not isinstance(result,str) or not 0<len(result)<=12000:raise ValueError('Reply outside bounds')
        if job.get('sender_id')==307200273 and len(result)>450 and not result.startswith('CHINA_'):
            # Pavel's existing policy requires long replies as PNG, including help.
            result='| Ответ |\n|---|\n'+'\n'.join('| '+cells(line)+' |' for line in result.splitlines() if line.strip())
        return result
    except Exception as exc:
        return ('Не удалось получить полный подтверждённый расчёт без ИИ ('+type(exc).__name__+'). '
                'Платный API не использовался, изменения не выполнялись. Доступные команды: «Помощь».')



