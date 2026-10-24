"""Clarify ambiguous reports before collection; durable, at-most-once feedback."""
import re
from datetime import timedelta, timezone

CHOICES = 'продажи и прибыль, реклама и ДРР, убыточные товары, цены или результаты изменений'
def normal(text):
    return re.sub(r'\s+', ' ', str(text or '').casefold().replace('ё', 'е')).strip()
def kind(text):
    s=normal(text)
    patterns=[('loss',r'убыточ|убытк'),('outcomes',r'результат.*изменен|контрол.*изменен|динамик.*прибыл'),
      ('sales',r'продаж|заказ|прибыл|падени|просад'),('advertising',r'реклам|\bрк\b|дрр|ддр|бюджет|ставк'),
      ('prices',r'цен[аыуе]|повышен.*цен|снижен.*цен'),('stock',r'остатк')]
    return next((k for k,p in patterns if re.search(p,s)),None)
def request(text):
    s=normal(text)
    if re.search(r'\bне\s+(?:готовь|делай|отправляй|присылай)|какие (?:есть |бывают |у нас )?отчет|что за отчет',s):
        return False
    report=bool(re.search(r'отчет|сводк|таблиц',s))
    return report and bool(re.search(r'дай|пришли|покаж|готов|сдела|состав|хочу|нуж|вчера|сегодня|за\s+\d|повтор|отправ|сейчас',s))
def marker(job):
    return next((e for e in job.get('tool_trace') or [] if e.get('name')=='china_saved_question'),{})
def resolved_job(job,history):
    """A short type selection keeps the original period, without a new job/action."""
    if kind(job.get('request_text')) and len(normal(job['request_text']))<100 and history:
        parent=history[-1]
        if str(parent.get('answer','')).startswith('Какой отчёт'):
            stated=re.search(r'\b\d{2}\.\d{2}\.\d{4}\b',parent.get('answer',''))
            period='\nСохранённый период: '+stated.group() if stated else ''
            return dict(job,request_text=parent['request_text']+period+'\nУточнение типа отчёта: '+job['request_text'])
    return job
def clarification(job,history,now):
    text=job.get('request_text','')
    if not request(text) or kind(text):return None
    quoted=marker(job).get('reply_text','')
    if kind(quoted):return None
    # History is not an implicit choice when multiple reports exist; use it only
    # when the person explicitly refers to the preceding report.
    if re.search(r'такой же|этот же|как выше|предыдущий',normal(text)) and history and kind(history[-1].get('answer')):
        return None
    s=normal(text);day=now.astimezone(timezone(timedelta(hours=3))).date()
    if 'вчера' in s:period=' за '+(day-timedelta(days=1)).strftime('%d.%m.%Y')
    elif 'сегодня' in s:period=' за '+day.strftime('%d.%m.%Y')
    else:
        explicit=re.search(r'\b\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\b',s)
        period=' за '+explicit.group() if explicit else ''
    suffix='' if period else ' Укажи также период.'
    return 'Какой отчёт'+period+' нужен: '+CHOICES+'?'+suffix
def acknowledgement_text(job):
    s=normal(job.get('request_text'))
    if request(s):return 'Принял, готовлю отчёт.'
    if re.search(r'разбери|проанализ|проверь|почему.*(?:упал|сниз|пад)|посчитай|рассчитай',s):
        return 'Принял, проверяю данные.'
    return None
def acknowledge(w,job):
    text=acknowledgement_text(job)
    if not text:return 'not_needed'
    try:
        return w.send_once('question_ack:'+str(job['id']),job['chat_id'],text)
    except Exception as ex:
        w.save('china_agent:question_feedback_error:v1:'+str(job['id']),{'kind':'ack','error':type(ex).__name__})
        return 'feedback_failed'
def failure_notice(w,job):
    try:
        return w.send_once('question_failure:'+str(job['id']),job['chat_id'],
            'Не удалось завершить обработку запроса. Сбой зафиксирован; готового отчёта пока нет.')
    except Exception as ex:
        w.save('china_agent:question_feedback_error:v1:'+str(job['id']),{'kind':'failure','error':type(ex).__name__})
        return 'feedback_failed'

