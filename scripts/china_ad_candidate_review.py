"""A candidate review is not an executable advertising plan or approval binding."""
import base64,hashlib
from datetime import datetime,timezone
from china_loss_control import CHAT,BOT
ROOT='china_agent:new_ad_candidate_review:v1:'

def build(s,maximum=20,nm_ids=()):
    from china_ad_retest import assess
    rows=[r for r in assess(s,nm_ids) if 'Отдельный запрет владельца' not in r['requires_review']]
    rows.sort(key=lambda r:(r['eligible'],(r.get('retest') or {}).get('status')=='improved',
                            ((r.get('retest') or {}).get('after') or {}).get('orders',0),r['finished']),reverse=True)
    return dict(rows=rows[:maximum],total=len(rows),eligible=sum(r['eligible'] for r in rows),
                improved=sum((r.get('retest') or {}).get('status')=='improved' for r in rows),
                source_observed_at=s['observed_at'],source_period=[s['period_from'],s['period_to']],
                wb_writes=0,paid_model_calls=0,execution_authorized=False)

def deliver_review(io,req,s,maximum=20,nm_ids=()):
    raise RuntimeError('Owner8Nov: intermediate candidate delivery disabled; complete final checks before delivery')
    # Historical implementation retained below for audit; build() remains internal-only.
    from china_table_png import render
    key=ROOT+str(req['job_id']);saved=io.get(key)
    if saved:
        review=saved['review'];images=[base64.b64decode(x) for x in saved['images']]
    else:
        review=build(s,maximum,nm_ids);table=[]
        for r in review['rows']:
            e=r.get('retest') or {};b,a=e.get('before') or {},e.get('after') or {}
            cr=(f'{b["cr_pct"]:.2f}% ({b["orders"]}/{b["views"]}) {b["period_from"]}–{b["period_to"]}\n'
                f'→ {a["cr_pct"]:.2f}% ({a["orders"]}/{a["views"]}) {a["period_from"]}–{a["period_to"]}') if b and a else 'Нет полного сопоставления после отключения'
            status='; '.join(r['requires_review']) or 'Сигнал для проверки ставки и условий; нужен отдельный точный план'
            table.append([r['article']+'\nnmID '+str(r['nm_id']),cr,str(r['stock']),
                          f'+{r["expected_rub_per_order"]:.0f} ₽/заказ при ДРР 5%',status])
        if not table:table=[['Нет позиций с полным положительным сценарным расчётом','Пропуски не считаются нулями','—','—','Это не доказательство отсутствия возможностей; нужны недостающие данные']]
        title=f'Китай · {review["total"]} кандидатов к проверке; показано {len(review["rows"])}'
        table.append(['Ограничения','Общая воронка, не рекламный CR; рост не доказывает причину или результат будущей РК.',
                      'Срез '+s['observed_at'][:16],'30-дневный собственный выкуп; комиссия/налог/логистика/COGS учтены по модели. Неизвестные общие расходы не ноль.',
                      'Для списка кандидатов не требуются обе цели теста одновременно. Это анализ, не план запуска.'])
        images=render(['Артикул','Конверсия до / после отключения','МСК свободно','Сценарная прибыль','Что ещё требуется'],table,title)
        saved=dict(status='frozen',job_id=req['job_id'],chat_id=CHAT,review=review,images=[base64.b64encode(b).decode() for b in images],execution_authorized=False)
        if not io.create(key,saved):raise RuntimeError('Candidate review already frozen; use existing delivery state')
    if io.tg('getMe',{}).get('id')!=BOT:raise ValueError('Wrong bot')
    for index,blob in enumerate(images):
        receipt=key+':delivery:'+str(index);prior=io.get(receipt)
        if prior:
            if prior.get('status')=='sent':continue
            raise RuntimeError('Uncertain candidate-review delivery; no resend')
        sha=hashlib.sha256(blob).hexdigest()
        if not io.create(receipt,dict(status='sending',chat_id=CHAT,sha256=sha)):raise RuntimeError('Delivery claim lost')
        try:
            import requests
            caption=f'Кандидатов к проверке: {review["total"]}; улучшение конверсии: {review["improved"]}. Аналитический список — запуск не подтверждает. Страница {index+1}/{len(images)}.'
            result=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',
                                 data=dict(chat_id=CHAT,caption=caption,reply_parameters=__import__('json').dumps(dict(message_id=req['reply_message_id'],allow_sending_without_reply=True))),
                                 files={'photo':('candidate-review.png',blob,'image/png')},timeout=45).json()
            if not result.get('ok') or result['result'].get('chat',{}).get('id')!=CHAT:raise RuntimeError('Photo receipt missing')
            io.put(receipt,dict(status='sent',chat_id=CHAT,sha256=sha,message_id=result['result']['message_id'],sent_at=datetime.now(timezone.utc).isoformat()))
        except Exception:
            io.put(receipt,dict(status='uncertain',chat_id=CHAT,sha256=sha));raise
    return {k:v for k,v in review.items() if k!='rows'}
