"""Read-first plans and deterministic evidence checks for analytical replies."""
import re,math,json
from datetime import timedelta
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
RULES=('Для числового рабочего ответа сначала прочитай источник из evidence_plan. Память и старый ответ не источник фактических метрик. '
'Каждую новую вычисленную цифру получай через calculate, используя только подтверждённые операнды. '
'Назови дату/период, источник и ограничения. Не смешивай рекламные заказы, все FBS-заказы, заказанные товары воронки и выкупы. '
'Неполные данные не ноль. ДРР=расход/сумма заказов, при отсутствии заказов не0%. '
'Сегодня можно описать, но сравнение с полными днями только как предварительный ориентир; не доказывай причинность. '
'Не утверждай отсутствие инструмента без выполненной попытки чтения. Коротко: вывод, 2–3 цифры, ограничение и обоснованное действие.')
MEMORY={'read_shared_memory','read_agreements','remember_work_note','remember_preference','search_chat_history','experience_context','free_analytic_dialog'}
NUMBER=re.compile(r'(?<![\w])[-+]?(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,]\d+)?')
def numbers(text):
 text=re.sub(r'\b\d+-[A-Za-z][\w-]+',' ',str(text))
 text=re.sub(r'\b\d{4}-\d{2}-\d{2}(?:T[\d:.+Z-]+)?|\b\d{1,2}\.\d{1,2}\.\d{2,4}|\b\d{1,2}:\d{2}\b',' ',str(text))
 return [float(re.sub(r'[ \u00a0\u202f]','',m[0]).replace(',','.')) for m in NUMBER.finditer(text)]
def topic(text):
 if re.search(r'что такое|что значит|объясни|напиши текст|переведи|запомни|напомни договор|почему важно',text,re.I):return None
 if re.search(r'подним|повысь|повысить|пониз|добав|убери|исключ|запуст|пополн|пауз|предлож|кандидат|делай|давай',text,re.I):return None
 if re.search(r'прибыл|себесто|логистик|резерв|остат',text,re.I):return None
 if re.search(r'реклам|(?<!\w)рк(?!\w)|показ|клик|ctr|cpc|дрр|ддр',text,re.I):return 'advertising'
 if re.search(r'выкуп|спп|цен[ауые]|рейтинг|отзыв',text,re.I):return 'products'
 if re.search(r'заказ|продаж',text,re.I):return 'orders'
 return None
def plan(w,job,history):
 text=job.get('request_text','');kind=topic(text);context=text
 if kind is None and re.search(r'а (?:за|если|эти|этих|в среднем)|сравн|почему хуже',text,re.I) and not re.search(r'цен|ставк|бюджет|пополн|прибыл',text,re.I):
  for h in reversed(history[-4:]):
   q=h.get('request_text','')
   if q==text:continue
   kind=topic(q)
   if kind:context=q+' '+text
   break
 if kind is None:return None
 # Ambiguous conversions belong to the dedicated funnel handler, not advertising.
 if re.search(r'конверс',context,re.I) and kind!='advertising':return None
 day=w.now.astimezone(MSK).date();last=day-timedelta(days=1);first=last
 if re.search(r'сегодня|сейчас|текущ',text,re.I):first=last=day
 elif re.search(r'позавчера',text,re.I):first=last=day-timedelta(days=2)
 elif re.search(r'недел',text,re.I):first=day-timedelta(days=7)
 else:
  n=re.search(r'за\s+(\d{1,2})\s+дн',text,re.I)
  if n:
   if not 1<=int(n[1])<=30:return None
   first=day-timedelta(days=int(n[1]))
 explicit=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
 if explicit:
  if len(explicit)>2:return None
  from datetime import date
  try:first=date.fromisoformat(explicit[0]);last=date.fromisoformat(explicit[-1])
  except ValueError:return None
  if first>last or last>day or (last-first).days>30:return None
 catalog=[(int(n),a) for n,a in w.catalog()]
 ids=sorted({n for n,a in catalog if a.casefold() in context.casefold() or re.search(r'(?<!\d)'+str(n)+r'(?!\d)',context)})
 unknown_article=bool(re.search(r'\b\d+-[a-z]',context,re.I) and not ids)
 campaigns=[int(x) for x in re.findall(r'(?<!\d)(4\d{7})(?!\d)',context)]
 if kind=='advertising' and campaigns:
  return dict(topic=kind,tool='get_saved_campaign',arguments=dict(campaign_id=campaigns[-1],date_from=str(first),date_to=str(last)),period_from=str(first),period_to=str(last),scope='selected_campaign',identity_unresolved=False,intraday=last==day)
 return dict(topic=kind,tool='get_live_data',arguments=dict(topic=kind,nm_ids=ids,date_from=str(first),date_to=str(last)),period_from=str(first),period_to=str(last),scope='selected_SKU' if ids else 'cabinet',identity_unresolved=unknown_article,intraday=last==day)
def preflight(analyst,p):
 if not p:return None
 if p['identity_unresolved']:
  return dict(name='analytic_evidence_preflight',arguments=p,result=dict(available=False,note='Exact article unresolved; use find_products before collecting a different scope.'),read_only=True)
 try:
  args=p['arguments']
  value=analyst.campaign(**args) if p['tool']=='get_saved_campaign' else analyst.live(args['topic'],args['nm_ids'],args['date_from'],args['date_to'])
 except Exception as exc:value=dict(available=False,error=type(exc).__name__,note='Selected source read failed; use another read-only source or report this specific gap.')
 return dict(name='analytic_evidence_preflight',arguments=p,result=value,read_only=True)
def evidence(trace):
 result=[]
 for t in trace:
  r=t.get('result')
  if t.get('name') in MEMORY or t.get('name')=='calculate' or not isinstance(r,dict):continue
  if r.get('available') is False or r.get('complete') is False or r.get('error') or r.get('cabinet') not in (None,'token_3'):continue
  if r.get('source') or r.get('source_key') or r.get('observed_at'):result.append(r)
 return result
def numeric_values(value):
 out=[]
 if isinstance(value,bool) or value is None:return out
 if isinstance(value,(float,int)):
  if math.isfinite(value):out.append(float(value))
 elif isinstance(value,list):
  for v in value:out+=numeric_values(v)
 elif isinstance(value,dict):
  for k,v in value.items():
   if k not in {'note','instruction','text','answer','question','source','source_key','error','monitoring','history','agreements','wb_writes','wb_reads','mpstats_reads','status_code'}:out+=numeric_values(v)
 return out
def supported(n,pool):
 return any(any(abs(n-round(x,d))<1e-7 for d in range(5)) for x in pool)
def zero_drr(v):
 if isinstance(v,list):return any(zero_drr(x) for x in v)
 if not isinstance(v,dict):return False
 spend=v.get('spend_cny',v.get('spend',v.get('sum')))
 amount=v.get('order_amount_cny',v.get('amount',v.get('sum_price')))
 if type(spend) in (int,float) and spend==0 and type(amount) in (int,float) and amount>0:return True
 return any(zero_drr(x) for x in v.values() if isinstance(x,(dict,list)))
def review(text,trace,p,question=''):
 if not p:return []
 facts=evidence(trace)
 if not facts:return ['No successful metric-source evidence; memory/calculator alone cannot support current facts.']
 pool=numeric_values(facts)+numeric_values(p['arguments'])
 # Calculations must themselves use evidenced operands; a calculator is not an independent source.
 for t in trace:
  if t.get('name')!='calculate':continue
  expr=t.get('arguments',{}).get('expression','')
  operands=numbers(expr)
  if not operands or not all(x in (0,1,100) or supported(x,pool) for x in operands):continue
  pool+=numeric_values(t.get('result',{}))
 unknown=[n for n in numbers(text) if not supported(n,pool)]
 issues=[]
 if not numbers(text) and numeric_values(facts):issues.append('The source contains numeric facts. Answer the metric question with the relevant supported values, or name the exact missing field; do not return an empty acknowledgement.')
 if p.get('intraday') and re.search(r'упал|сниз|хуже|лучше|вырос|увелич',text,re.I) and not re.search(r'предвар|ориентир|неполн|догруж|до того же часа|сопоставим',text,re.I) and not any(f.get('matched_clock') is True or f.get('yesterday_same_clock') is not None for f in facts):issues.append('Incomplete-day comparison needs matched-clock evidence or an explicit preliminary benchmark limitation.')
 if unknown:issues.append('Unsupported numeric claims: '+','.join(str(n) for n in sorted(set(unknown))[:12])+'. Read evidence or calculate from grounded operands.')
 if re.search(r'(?:инструмент|доступ).{0,30}(?:нет|отсутств)|нет.{0,25}инструмент',text,re.I):issues.append('Do not claim no tools: a metric source has been attempted; report its actual outcome.')
 if re.search(r'дрр\s*(?:=|—|:)?\s*0(?:[.,]0+)?\s*%',text,re.I) and not zero_drr(facts):issues.append('DRR zero requires positive order amount and measured zero spend; otherwise unknown. Show operands.')
 return issues
def fallback(p,trace):
 facts=evidence(trace)
 label=p['topic']+' '+p['period_from']+'–'+p['period_to']
 if facts:
  return 'Данные выбранного источника за '+label+' получены, но числовой вывод не прошёл проверку подтверждений. Неподтверждённые цифры не отправляю; изменений нет.'
 return 'Проверка источника '+label+' не дала подтверждённых метрик для этого ответа. Это конкретный пробел выбранного источника, не отсутствие всех инструментов. Неизвестное не ноль; изменений нет.'
