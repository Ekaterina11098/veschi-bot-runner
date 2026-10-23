"""Owner-requested real analytical engine preview; no Telegram, jobs or WB mutations."""
import os,json,copy
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
from conversion_watches import runtime
from china_analytic_dialog import answer

KEY='china_agent:decline_preview:v2:2026-10-23'
REQUEST=('Разбери падение заказов вчера22.10 и сегодня23.10 по кабинету Китай. Сам собери свежие данные WB, MPStats и МоегоСклада. '
 'Вчера сравни с21.10, сегодня — с22.10 до того же часа МСК. Считай заказы, не выкупы. '
 'Найди артикулы, давшие основное снижение. Проверь общие клики, клик-заказ, отдельно рекламные показы/клики/ДРР, цену покупателя/СПП, остатки и проверенные даты изменений. '
 'Общие показы API недоступны: не заменяй рекламными, органику не выдумывай. При расхождении одинакового показателя приоритет WB. '
 'Посчитай общую расчётную прибыль кабинета за доступные сопоставимые периоды: налог5%, своя себестоимость из МоегоСклада, для нулевого остатка более ранний срез. '
 'Рекламу учитывай за тот же период один раз. get_wb_evidence даёт расчёт по опубликованным операциям WB: это не прибыль сегодняшних заказов; не смешивай даты операций и когорты. '
 'Для вчерашних/сегодняшних незавершённых заказов по возможности рассчитай отдельно ожидаемую общую прибыль на собственном завершённом выкупе. Если входов не хватает, конкретно назови пробел, не выдумывай сумму. '
 'Нужен полный краткий материал для PNG: сводка кабинета/общая прибыль и таблица проблемных артикулов с конкретной рекомендацией на сейчас. '
 'Укажи проверенную текущую ставку→новую, минимум/шаг и точную РК либо другой обоснованный следующий шаг. Уже отключённое без нужных действий не включай. '
 'Отдели подтверждённые причины от гипотез и учти память наших изменений. Не ограничивай ответ1200символами, но без длинных пояснений. '
 'Ничего не меняй. Только PNG-предпросмотр здесь в Codex, Telegram запрещён. Не создавай исполняемые планы, задания или расписания.')

def main():
 original=requests.sessions.Session.request;network=[]
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);method=method.upper();body=kw.get('json') or {}
  if u.hostname=='api.telegram.org':raise PermissionError('No Telegram preview')
  if u.hostname and u.hostname.endswith('wildberries.ru'):
   posts={'/api/analytics/v3/sales-funnel/products','/api/finance/v1/sales-reports/detailed','/api/advert/v1/bids/min','/api/v2/search-report/table/details','/api/v2/search-report/product/search-texts'}
   if method!='GET' and not (method=='POST' and u.path in posts):raise PermissionError('Marketplace mutation forbidden')
  if u.hostname==urlparse(os.environ['SUPABASE_URL']).hostname and method!='GET' and u.path not in ['/rest/v1/telegram_api_cache','/rest/v1/analytics_snapshots']:raise PermissionError('Preview cannot modify jobs or business state')
  network.append(dict(host=u.hostname,path=u.path,method=method))
  return original(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  w=runtime();old=w.get(KEY)
  if old and old.get('status')=='answered':print('already_answered');return
  job=dict(id=-2026102321,agent_id='china',chat_id=-1004342917488,sender_id=5122667182,request_text=REQUEST,tool_trace=[{'name':'china_saved_question','reply_text':''}],status='preview')
  w.save(KEY,dict(status='running',request=REQUEST,started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0))
  try:
   result,trace=answer(w,job,[])
   if not result:raise RuntimeError('Analyst returned no answer')
   value=dict(status='answered',answer=result,trace=trace,observed_at=datetime.now(timezone.utc).isoformat(),job_id=job['id'],network=network,wb_writes=0,telegram_sends=0)
  except Exception as ex:
   value=dict(status='blocked',error=type(ex).__name__,detail=str(ex)[:400] if isinstance(ex,(RuntimeError,ValueError,PermissionError)) else 'Transport failure',observed_at=datetime.now(timezone.utc).isoformat(),network=network,wb_writes=0,telegram_sends=0)
  w.save(KEY,value);print(json.dumps({k:value.get(k) for k in ['status','error','wb_writes','telegram_sends']}))
  if value['status']!='answered':raise SystemExit(1)
 finally:requests.sessions.Session.request=original

if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise SystemExit('Public runner only')
 main()

