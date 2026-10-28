"""Reconcile unsent catalog-price replies against durable readback receipts. No external I/O."""
import copy,re
from datetime import datetime
from decimal import Decimal,InvalidOperation
from zoneinfo import ZoneInfo
ROOT='china_agent:catalog_price_command:v1:'
DELIVERY='china_agent:conversion_watch_delivery:v1:'
PLAN_KEY=re.compile(re.escape(ROOT)+r'\d{4}-\d{2}-\d{2}$')
STATUS=re.compile(r'поднял.*цен|цен.*(?:поднял|повысил|изменил|готов|выполн)|статус.*цен|как\s+там.*задач',re.I)
CLARIFY=re.compile(r'(?:не понимаю|что (?:именно )?значит проверено|что именно проверено|ответь да или нет|да или нет)[?!. ]*$',re.I)
def marker(job):
 return next((x for x in job.get('tool_trace',[]) if x.get('name')=='china_saved_question'),{})
def keys(trace):
 return [x['command_key'] for x in reversed(trace or []) if x.get('name','').startswith('catalog_price_') and PLAN_KEY.fullmatch(str(x.get('command_key','')))]
def valid_plan(p):
 return isinstance(p,dict) and isinstance(p.get('rules'),dict) and 'default_percent' in p['rules'] and p.get('status') is not None
def percent_matches(p,text):
 explicit=set(re.findall(r'(\d+(?:[.,]\d+)?)\s*%',text))
 if not explicit:return True
 wanted={Decimal(p['rules']['default_percent'])}|{Decimal(x['percent']) for x in p['rules'].get('overrides',[])}
 return bool({Decimal(x.replace(',','.')) for x in explicit}&wanted)
def choose(w,job,history,trace=(),allow_command=False):
 text=job.get('request_text','');status=bool(STATUS.search(text));clarify=bool(CLARIFY.fullmatch(text.strip()))
 from china_catalog_price_command import parse as parse_command
 try:command=parse_command(text) is not None
 except (ValueError,TypeError):command=False
 command=command or bool(re.fullmatch(r'(?:просто\s+)?(?:подними|поднимай|повысь|повышай)(?:\s+все)?\s+цен[уы][.! ]*',text.strip(),re.I))
 confirmation=bool(re.fullmatch(r'(?:согласен[.! ]*|да[.! ]*)?(?:делай|сделай|давай|поднимай|применяй|подтверждаю)[.! ]*',text.strip(),re.I))
 if re.search(r'показ|клик|корзин|диагност|проанализ|почему.*прода|что.*сделать',text,re.I) and not re.search(r'ответь.*да.*или.*нет',text,re.I) and not command:return None
 if allow_command and not(status or clarify or command or confirmation):return None
 if not(status or clarify or allow_command):return None
 current=ROOT+w.now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
 candidates=keys(trace)+keys(job.get('tool_trace'))
 # Explicit reply lineage outranks recency; a morning cohort is a different operation.
 parent=marker(job).get('parent_job_id')
 context=[h for h in history if h.get('id')==parent] if parent else history[-1:]
 for h in reversed(context):
  found=keys(h.get('tool_trace'))
  if found:candidates+=found;break
  if any(x.get('name','').startswith('zero_order_price') for x in h.get('tool_trace',[])):
   if not candidates and not re.search(r'\d+(?:[.,]\d+)?\s*%',text):return None
   break
 candidates.append(current)
 seen=set()
 for key in candidates:
  if key in seen:continue
  seen.add(key);p=w.get(key)
  if not valid_plan(p) or not percent_matches(p,text):continue
  source={r.get('job_id') for r in p.get('source_refs',[]) if r.get('job_id') is not None}|({p['job_id']} if p.get('job_id') is not None else set())
  bound=job.get('id') in source or parent in source or key in keys(trace)+keys(job.get('tool_trace'))
  contextual=any(h.get('id') in source or key in keys(h.get('tool_trace')) for h in context)
  if bound or contextual and (status or clarify) or status and re.search(r'цен',text,re.I) and not parent:return key,p
 if status and re.search(r'цен',text,re.I) and not parent and hasattr(w,'db'):
  rows=w.db('GET','telegram_api_cache',params={'cache_key':'like.'+ROOT+'*','select':'cache_key,payload','order':'updated_at.desc','limit':20}) or []
  for row in rows:
   key=row.get('cache_key','');p=row.get('payload')
   if PLAN_KEY.fullmatch(key) and valid_plan(p) and percent_matches(p,text):return key,p
 return None
def verified_items(w,p):
 selections={str(s['nm_id']):s for s in p.get('selections',[])}
 approvals={x['key'] for x in p.get('batch_approvals',[])}
 verified=set()
 for key in p.get('executions',[]):
  e=w.get(key) or {}
  if e.get('approval_key') not in approvals:continue
  for x in e.get('items',[]):
   s=x.get('selection') or {};rb=x.get('readback') or {};request=x.get('request') or {};nm=str(s.get('nm_id'))
   if s!=selections.get(nm) or x.get('status') not in ('applied','already_at_target'):continue
   try:
    target=Decimal(s['target_cny']);sizes=rb.get('sizes') or []
    ok=(target.is_finite() and target>0 and str(rb.get('nmID'))==nm and str(request.get('nmID'))==nm and
        rb.get('currencyIsoCode4217')=='CNY' and rb.get('vendorCode')==s['article'] and
        rb.get('discount')==s['seller_discount']==request.get('discount') and rb.get('clubDiscount')==s.get('club_discount') and
        sizes and all(Decimal(str(z['discountedPrice']))==target and Decimal(str(z['price']))==Decimal(str(request['price'])) for z in sizes))
    if ok:verified.add(nm)
   except (KeyError,TypeError,ValueError,InvalidOperation):continue
 return len(verified)
def render(w,key,p,text):
 from china_catalog_price_command import status_text
 view=copy.deepcopy(p);n=verified_items(w,p);total=p.get('total_count')
 if type(total) is not int or total<0:total=len(p.get('selections',[]))+sum(r.get('status')=='blocked' and not r.get('selection') for r in p.get('rows',[]))
 claimed=p.get('verified_count',0);mismatch=claimed!=n
 view.update(verified_count=n,total_count=total)
 if n: view['status']='verified' if n==total else 'partial'
 elif p['status'] in ('verified','partial'):
  view.update(status='uncertain',reason='нет полных квитанций WB для заявленного результата')
 answer=status_text(view)
 if n:answer=('Да. ' if n==total else 'Да, частично. ')+answer
 if CLARIFY.fullmatch(text.strip()):
  answer+=' «Проверено» означает: WB вернул цену, совпавшую с точной целевой ценой и сохранёнными скидками; регистрация команды сама по себе этого не подтверждает.'
 if n and any((w.get(k) or {}).get('minimum_price_policy')=='seller_discounted_floor_preserve_blocks_v1' and (w.get(k) or {}).get('minimum_prices',{}).get('status')!='verified' for k in p.get('executions',[])):
  answer+=' Минимальные цены для автоакций ещё не подтверждены; это отдельный обязательный шаг с сохранением блокировок.'
 if n and mismatch:answer+=' Счётчик плана расходится с квитанциями; показываю только подтверждённое WB.'
 return answer,[dict(name='catalog_price_status',command_key=key,status=view['status'],wb_verified=n,total=total,receipt_mismatch=mismatch,wb_writes=0,telegram_sends=0)]
def status_answer(w,job,history):
 found=choose(w,job,history)
 return render(w,*found,job.get('request_text','')) if found else None
def reconcile(w,job,history,answer,trace):
 # Once any first-part receipt exists, preserve send_once identity and partial delivery.
 # Sent/uncertain messages are never edited or resent by reconciliation.
 if w.get(DELIVERY+'question:'+str(job['id'])+':0'):return answer,trace
 found=choose(w,job,history,trace,allow_command=True)
 if not found:return answer,trace
 fresh,proof=render(w,*found,job.get('request_text',''))
 if fresh==answer:return answer,trace
 return fresh,list(trace or [])+[dict(proof[0],name='reply_evidence_reconciled',prepared_answer_replaced=True)]
