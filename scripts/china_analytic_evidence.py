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
 if re.search(r'что решили|о ч[её]м договор|что обсуждал|напомни.*план',text,re.I):return None
 if re.search(r'что такое|что значит|объясни|напиши текст|переведи|запомни|напомни договор|почему важно',text,re.I):return None
 if re.search(r'подним|повысь|повысить|пониз|добав|убери|исключ|запуст|пополн|пауз|предлож|кандидат|делай|давай',text,re.I):return None
 if re.search(r'прибыл|себесто|логистик|резерв|остат',text,re.I):return None
 if re.search(r'реклам|(?<!\w)рк(?!\w)|показ|клик|ctr|cpc|дрр|ддр',text,re.I):return 'advertising'
 if re.search(r'выкуп|спп|цен[ауые]|рейтинг|отзыв',text,re.I):return 'products'
 if re.search(r'заказ|продаж',text,re.I):return 'orders'
 return None

def resolve_scope(catalog,text):
 """Resolve exact nm/article or an unambiguous short model number; never guess."""
 catalog=[(int(n),a) for n,a in catalog]
 exact={n for n,a in catalog if a.casefold() in text.casefold() or re.search(r'(?<!\d)'+str(n)+r'(?!\d)',text)}
 mentioned=re.findall(r'\b\d+-[a-z][\w-]*',text,re.I)
 unknown_exact=any(a.casefold() not in {v.casefold() for _,v in catalog} for a in mentioned)
 if exact:return sorted(exact),unknown_exact
 codes=set(re.findall(r'(?:модел\w*|артикул\w*|арт\.?|сумк\w*)\s*[№#]?\s*(\d{1,4})(?!\d)',text,re.I))
 codes.update(re.findall(r'(?<!\d)(\d{1,4})\s+(?:сумк\w*|модел\w*)(?!\w)',text,re.I))
 result=set();unresolved=bool(re.search(r'\b\d+-[a-z]',text,re.I))
 for code in codes:
  matches={n for n,a in catalog if a.split('-')[0].isdigit() and int(a.split('-')[0])==int(code)}
  if len(matches)==1:result.update(matches)
  else:unresolved=True
 return sorted(result),unresolved
def plan(w,job,history):
 text=job.get('request_text','');kind=topic(text);context=text
 economics=bool(re.search(r'экономик|в плюс|в минус|прибыл|себесто',text,re.I)) and not re.search(r'что такое|объясни|пополни|поставь|сделай',text,re.I)
 if economics:kind='products'
 if kind is None and re.search(r'а (?:за|если|эти|этих|в среднем)|сравн|почему хуже',text,re.I) and not re.search(r'цен|ставк|бюджет|пополн|прибыл',text,re.I):
  for h in reversed(history[-4:]):
   q=h.get('request_text','')
   if q==text:continue
   kind=topic(q)
   if kind:context=q+' '+text
   break
 if kind is None and re.search(r'^(?:и\s+)?выкуп',text,re.I):kind='products'
 if kind is None:return None
 own_ids,own_unknown=resolve_scope(w.catalog(),text)
 if not own_ids and not own_unknown and re.search(r'эт(?:ой|ого|и|им|им|у)|модел|^и выкуп',text,re.I):
  for h in reversed(history[-4:]):
   previous=h.get('request_text','')
   ids,unknown=resolve_scope(w.catalog(),previous)
   if ids or unknown:
    context=previous+' '+text;break
 # Ambiguous conversions belong to the dedicated funnel handler, not advertising.
 if re.search(r'конверс',context,re.I) and kind!='advertising':return None
 period_text=text
 if re.search(r'^и\s+выкуп|этой модели|этого артикула',text,re.I) and not re.search(r'сегодня|вчера|недел|дн|202\d-\d\d-\d\d',text,re.I):
  for h in reversed(history[-4:]):
   if re.search(r'сегодня|вчера|недел|дн|202\d-\d\d-\d\d',h.get('request_text',''),re.I):
    period_text=h['request_text'];break
 day=w.now.astimezone(MSK).date();last=day-timedelta(days=1);first=last
 if re.search(r'сегодня|сейчас|текущ',period_text,re.I):first=last=day
 elif re.search(r'позавчера',period_text,re.I):first=last=day-timedelta(days=2)
 elif re.search(r'недел',period_text,re.I):first=day-timedelta(days=7)
 else:
  n=re.search(r'(?:за\s+(?:последн\w*\s+)?)(\d{1,2})\s+дн',period_text,re.I)
  if n:
   if not 1<=int(n[1])<=30:return None
   first=day-timedelta(days=int(n[1]))
 explicit=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',period_text)
 if explicit:
  if len(explicit)>2:return None
  from datetime import date
  try:first=date.fromisoformat(explicit[0]);last=date.fromisoformat(explicit[-1])
  except ValueError:return None
  if first>last or last>day or (last-first).days>30:return None
 catalog=[(int(n),a) for n,a in w.catalog()]
 ids,unknown_article=resolve_scope(catalog,context)
 if economics and not ids:unknown_article=True
 campaigns=[int(x) for x in re.findall(r'(?<!\d)(4\d{7})(?!\d)',context)]
 if kind=='advertising' and campaigns:
  return dict(topic=kind,tool='get_saved_campaign',arguments=dict(campaign_id=campaigns[-1],date_from=str(first),date_to=str(last)),period_from=str(first),period_to=str(last),scope='selected_campaign',identity_unresolved=False,intraday=last==day)
 additional=[]
 if re.search(r'заказ',text,re.I) and re.search(r'выкуп',text,re.I):
  additional=[dict(topic='orders',nm_ids=ids,date_from=str(first),date_to=str(last))]
 if economics:
  # Own buyout cohort must use completed days; fresh price/stock are dated separately.
  last=day-timedelta(days=1);first=last-timedelta(days=29)
  additional=[dict(topic=k,nm_ids=ids,date_from=str(first),date_to=str(last)) for k in ['prices','stock']]
 result=dict(topic=kind,tool='get_live_data',arguments=dict(topic=kind,nm_ids=ids,date_from=str(first),date_to=str(last)),period_from=str(first),period_to=str(last),scope='selected_SKU' if ids else 'cabinet',identity_unresolved=unknown_article,intraday=last==day)
 if additional:result.update(additional_reads=additional,economics=economics)
 return result
def preflight(analyst,p):
 if not p:return None
 if p['identity_unresolved']:
  return dict(name='analytic_evidence_preflight',arguments=p,result=dict(available=False,note='Exact article unresolved; use find_products before collecting a different scope.'),read_only=True)
 try:
  args=p['arguments']
  value=analyst.campaign(**args) if p['tool']=='get_saved_campaign' else analyst.live(args['topic'],args['nm_ids'],args['date_from'],args['date_to'])
 except Exception as exc:value=dict(available=False,error=type(exc).__name__,note='Selected source read failed; use another read-only source or report this specific gap.')
 if p.get('additional_reads'):
  parts=[dict(arguments=p['arguments'],result=value)]
  for args in p['additional_reads']:
   try:r=analyst.live(args['topic'],args['nm_ids'],args['date_from'],args['date_to'])
   except Exception as exc:r=dict(available=False,error=type(exc).__name__,note='This input unavailable; other successful inputs remain usable.')
   parts.append(dict(arguments=args,result=r))
  value=dict(source='read-first question inputs',inputs=parts,coverage_complete=all(x['result'].get('available') is not False for x in parts),note='Sources and periods remain separate. Missing costs are not zero; cohort estimates are not final profit.')
  if p.get('economics'):
   policy=analyst.w.get('china_agent:new_ad_economics_policy:v1') or {}
   value['dated_economics_policy']={k:v for k,v in policy.items() if k!='logistics_by_nm'}
   value['dated_economics_policy']['logistics_by_nm']={str(n):policy.get('logistics_by_nm',{}).get(str(n)) for n in p['arguments']['nm_ids']}
 return dict(name='analytic_evidence_preflight',arguments=p,result=value,read_only=True)
def evidence(trace):
 result=[]
 for t in trace:
  r=t.get('result')
  if t.get('name') in MEMORY or t.get('name')=='calculate' or not isinstance(r,dict):continue
  if r.get('source')=='read-first question inputs':
   result+=evidence([dict(name='question_input',result=x.get('result')) for x in r.get('inputs',[])])
   continue
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
 if p.get('economics') and re.search(r'точно.{0,12}(?:в плюс|прибыл)|чистая прибыль|гарантирован.*прибыл',text,re.I) and not re.search(r'предвар|не подтверж|неподтверж|не доказ|нельзя',text,re.I):issues.append('Economics inputs do not establish closed-cohort net profit. State assumptions, missing costs and buyout sample; do not claim guaranteed profit.')
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
