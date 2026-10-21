"""Send one honest coverage limitation; no stale loss list or WB writes."""
from datetime import datetime,timezone
from china_price_apply import IO
io=IO();key='china_agent:loss_report:2026-10-21:v1'
e=io.get(key)
if e and e.get('status')=='delivered':print('already_delivered');raise SystemExit()
if e:raise RuntimeError('Existing delivery requires reconciliation; no blind retry')
text='Убыточные позиции · 21.10.2026\n\nРасчёт за 21.09–20.10 пока неполный: свежий срез товаров есть, но общие удержания и сверка логистики за этот же период не обновлены.\n\nВчерашний список не повторяю: цены уже менялись. Надёжно назвать текущий убыток и полную безубыточность пока нельзя.\n\nОхват: полный расчёт не подтверждён ни по одной позиции; это не означает отсутствие убыточных товаров.'
if io.tg('getMe',{}).get('id')!=8780468043:raise RuntimeError('Wrong bot')
e=dict(status='ready',day='2026-10-21',chat_id=-1004342917488,text=text,coverage='incomplete',product_snapshot_ids=[18862,18863],missing=['same_period_overhead','same_period_finance_reconciliation'],created_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
if not io.create(key,e):raise RuntimeError('Concurrent report')
e['status']='sending';io.put(key,e)
try:
 receipt=io.tg('sendMessage',dict(chat_id=e['chat_id'],text=text))
 if receipt.get('chat',{}).get('id')!=e['chat_id'] or type(receipt.get('message_id')) is not int:raise RuntimeError('Receipt mismatch')
 e.update(status='delivered',receipt=receipt,message_id=receipt['message_id'],completed_at=datetime.now(timezone.utc).isoformat());io.put(key,e)
except Exception:
 e['status']='uncertain';io.put(key,e);raise RuntimeError('Uncertain: do not blindly resend') from None
print('coverage_notice_delivered')
