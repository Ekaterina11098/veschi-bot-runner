"""Existing scheduled task execution through cloud Codex, retaining watch identities and receipts."""
import json
from china_codex_analysis import Core,POLICY
from china_codex_cloud import Worker
from china_codex_read_broker import validate_read,collect
def enabled(io):return (io.get(POLICY)or{}).get('status')=='active'
def run_task(w,watch,receipt_key,force=False,core=None):
 core=core or Core()
 question=watch.get('task_text')or 'Кратко оцени общую воронку выбранного товара по сохранённым полным дням. Покажи точные данные и ограничения.'
 context=Worker(core.db).context(dict(job_id=0,sender_id=watch['owner_user_id'],request_text=question))
 if watch.get('kind')not in('task','once_task'):
  daily,_=w.load_days(watch);context['watch_daily']=daily
 evidence=[]
 def validate(v):
  if v.get('kind')=='read':return validate_read(v)
  if v.get('kind')!='answer' or not isinstance(v.get('answer'),str)or not 0<len(v['answer'])<=12000:raise ValueError('Scheduled cloud answer invalid')
  return v
 for turn in range(4):
  result,receipt=core.ask('watch:'+receipt_key+':'+str(turn),'scheduled_analysis',
   dict(question=question,watch=watch,dated_context=context,additional_evidence=evidence,instruction='Ничего не планируй и не меняй. Выполни один текущий запуск. При output_format png_table или once_task используй содержательную Markdown таблицу. Точные данные при нехватке запрашивай read; не подменяй samehour полным вчера.'),
   dict(kind='answer|read',answer='Краткий аналитический ответ по существу с точными данными',topic='catalogue|products|stock|prices|advertising|orders',nm_ids=[],date_from='YYYY-MM-DD',date_to='YYYY-MM-DD'),validate,force)
  if result['kind']=='answer':return result['answer'],receipt
  if turn==3:raise RuntimeError('Scheduled read budget exhausted')
  job=dict(id=0,agent_id='china',sender_id=watch['owner_user_id'],chat_id=watch['chat_id'],request_text=question,origin='scheduled')
  try:value=collect(w,job,result)
  except Exception as ex:value=dict(status='unavailable',error=type(ex).__name__,requested_scope=result)
  evidence.append(value)
 raise RuntimeError('No scheduled cloud answer')
