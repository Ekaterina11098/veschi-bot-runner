"""Explicit catalog price commands: deterministic route, pending-only amendments, no WB writes."""
import copy,hashlib,json,re
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_HALF_UP
from zoneinfo import ZoneInfo
ROOT='china_agent:catalog_price_command:v1:'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def parse(text):
 text=text.strip()
 if re.search(r'не\s+подним\w*.*уже.*сегодня.*(?:поднимали|повышали).*\d+(?:[.,]\d+)?\s*%',text,re.I):
  n=re.findall(r'(\d+(?:[.,]\d+)?)\s*%',text)[-1]
  return dict(kind='exclude_earlier',percent=format(Decimal(n.replace(',','.')).normalize(),'f'))
 head=re.split(r'[.!?]\s+|\bи\s+завтра\b',text,maxsplit=1,flags=re.I)[0]
 if '?' in head or re.search(r'\b(?:не\s+(?:надо|подним\w*|повыш\w*|увелич\w*)|может|если|стоит\s+ли|можно|рассчитай|проверь|предложи)\b',head,re.I):return None
 if re.search(r'без\s+заказ',head,re.I):return None
 nums=re.findall(r'(\d+(?:[.,]\d+)?)\s*%',head)
 action=bool(re.search(r'подним|поднят|повысь|повыс|повыш|увелич|добавь',head,re.I))
 all_scope=bool(re.search(r'\bвс[еёехм]+\b',head,re.I) and re.search(r'товар|ассортимент|цен',head,re.I))
 fragment=re.search(r'(?:в\s+которых\s+есть|содержащ\w*|содержат)\s+([a-z0-9][a-z0-9_-]{1,60})',head,re.I)
 family=bool(re.search(r'\bвс[еёехм]+\s+(?:(?:товар|сумк|артикул)\w*\s+)?(?:noelbag|noel|ноэль|ноель)\b',head,re.I))
 if re.search(r'ставк|реклам|бюджет|пополн',head,re.I) and not re.search(r'цен',head,re.I):return None
 if not nums or not (action or re.fullmatch(r'все\s+товары\s*\+\s*\d+(?:[.,]\d+)?\s*%',head,re.I)):return None
 if len(nums)>1 and not re.search(r'не\s+на\s+\d.*\bа\s+на',head,re.I):raise ValueError('В команде неоднозначный процент')
 percent=Decimal(nums[-1].replace(',','.'))
 if not 0<percent<=100:raise ValueError('Процент должен быть от 0 до 100')
 if family and action:return dict(kind='contains',fragment='noelbag',percent=format(percent.normalize(),'f'))
 if fragment and action:return dict(kind='contains',fragment=fragment[1].casefold(),percent=format(percent.normalize(),'f'))
 if all_scope and (re.search(r'цен',head,re.I) or re.fullmatch(r'все\s+товары\s*\+\s*\d+(?:[.,]\d+)?\s*%',head,re.I)):return dict(kind='catalog',percent=format(percent.normalize(),'f'))
 return None
def resolve(text,history):
 parsed=parse(text)
 if parsed:return parsed
 if not re.fullmatch(r'(?:просто\s+)?(?:подними|поднимай|повысь|повышай)(?:\s+все)?\s+цен[уы][.! ]*',text.strip(),re.I):return None
 for h in reversed(history):
  value=parse(h.get('request_text',''))
  if value and value['kind']=='catalog':return value
 return None
def signature(p):
 return digest({k:p[k] for k in ['day','actor_user_id','source_channel','request_text','rules']})
def choose_percent(article,rules):
 matches=[r['percent'] for r in rules.get('overrides',[]) if r['fragment'].casefold() in article.casefold()]
 if len(set(matches))>1:raise ValueError('Пересекающиеся проценты для артикула')
 return matches[0] if matches else rules['default_percent']
def selection(g,percent):
 if g.get('currencyIsoCode4217')!='CNY' or g.get('editableSizePrice') is not False:raise ValueError('Валюта/режим размеров не поддержаны')
 sizes=g.get('sizes') or []
 if not sizes or len({Decimal(str(s['price'])) for s in sizes})!=1 or len({Decimal(str(s['discountedPrice'])) for s in sizes})!=1:raise ValueError('Неоднозначные цены размеров')
 base=Decimal(str(sizes[0]['price']));old=Decimal(str(sizes[0]['discountedPrice']));discount=g.get('discount')
 if base<=0 or old<=0:raise ValueError('Исходная цена WB равна 0; процент не создаёт положительную цену')
 if type(discount)is not int or not 0<=discount<100:raise ValueError('Неизвестная скидка')
 factor=Decimal(100-discount)/100
 if base*factor!=old:raise ValueError('Цена WB не согласуется со скидкой')
 newbase=(base*(1+Decimal(percent)/100)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
 target=newbase*factor
 if target<=old:raise ValueError('Повышение меньше допустимого шага WB')
 return dict(nm_id=str(g['nmID']),article=g['vendorCode'],action='Повышение',current_cny=str(old),target_cny=str(target),base_cny=str(base),seller_discount=discount,club_discount=g.get('clubDiscount'),percent=percent,nominal_target_cny=str(old*(1+Decimal(percent)/100)),rounding_policy='nearest_WB_base_unit_preserve_discount')
def status_text(p):
 rules=p['rules'];summary='Все товары +'+rules['default_percent']+'%'
 if p.get('scope')=='single':
  pct=rules['default_percent'];summary=p['article']+': '+('+' if not pct.startswith('-') else '')+pct+'%'
 for r in rules.get('overrides',[]):summary+='; артикулы с '+r['fragment']+' +'+r['percent']+'% вместо общего процента'
 if rules.get('exclude_verified_percent_today'):summary+='; сегодняшние проверенные повышения на '+','.join(rules['exclude_verified_percent_today'])+'% исключены'
 status=p.get('status')
 if status in ['verified','partial']:
  return summary+'. WB подтвердил '+str(p.get('verified_count',0))+' из '+str(p.get('total_count',0))+' товаров. Не изменено/не подтверждено: '+str(p.get('total_count',0)-p.get('verified_count',0))+'. Повторное повышение не отправляю.'+(' Минимум автоакций: '+p.get('minimum_price_status','required_not_verified')+'.' if p.get('scope')=='single' else '')
 if status in ['uncertain','blocked']:return summary+'. Выполнение не подтверждено: '+p.get('reason','нужна сверка журнала')+'. Повторная запись не отправляется.'
 return 'Принято: '+summary+'. Зарегистрирован точный ценовой запрос; выполнение подтвержу только после сверки WB. Повторные сообщения не складывают проценты.'
def handle(w,job,history):
 from china_single_price_command import handle as single_handle
 single=single_handle(w,job,history)
 if single is not None:return single
 text=job.get('request_text','');parsed=resolve(text,history)
 today=w.now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat();key=ROOT+today;p=w.get(key)
 if parsed is not None and parse(text) is None and not p:
  return 'Для этого уточнения нет текущего ценового плана. Старое повышение автоматически не повторяю.',[dict(name='catalog_price_command',status='missing_current_plan')]
 if parsed is not None and re.fullmatch(r'все\s+товары\s*\+\s*\d+(?:[.,]\d+)?\s*%',text.strip(),re.I) and not p and not any(re.search(r'цен',h.get('request_text',''),re.I) and parse(h.get('request_text','')) for h in history):
  return 'Уточни, речь о ценах товаров или о рекламных ставках?',[dict(name='catalog_price_command',status='ambiguous_price_scope')]
 if parsed is None:
  marker=next((t for t in job.get('tool_trace',[]) if t.get('name')=='china_saved_question'),{})
  source_jobs={r.get('job_id') for r in (p or {}).get('source_refs',[]) if r.get('job_id') is not None}
  if p and marker.get('parent_job_id') in source_jobs and re.fullmatch(r'(?:согласен[.! ]*|да[.! ]*)?(?:делай|сделай|давай|применяй|подтверждаю)[.! ]*',text.strip(),re.I):
   return status_text(p)+' Это подтверждение сохранённого плана, не повторное повышение.',[dict(name='catalog_price_confirmation',command_key=key,duplicate_prevented=True,wb_writes=0)]
  from china_reply_evidence import status_answer
  return status_answer(w,job,history)
 if not w.authorized(job):return 'Изменять цены могут только действующие участники этой группы.',[dict(name='catalog_price_command',status='unauthorized')]
 if p:
  if job['id']<=p.get('last_human_job_id',0) or (parsed['kind']=='catalog' and parsed['percent']==p['rules']['default_percent']):
   return status_text(p),[dict(name='catalog_price_command',command_key=key,duplicate_prevented=True)]
  if p['status']!='requested':return status_text(p)+' Новый процент требует отдельного плана от исходных цен; поверх текущего результата его не прибавляю.',[dict(name='catalog_price_command',command_key=key,status='amendment_after_freeze_blocked')]
  p=copy.deepcopy(p)
 else:
  if parsed['kind']!='catalog':return 'Сначала нужна команда для всего каталога, к которой относится это исключение.',[dict(name='catalog_price_command',status='missing_base_scope')]
  p=dict(status='requested',day=today,actor_user_id=job['sender_id'],source_channel='telegram',request_text=text,job_id=job['id'],created_at=datetime.now(timezone.utc).isoformat(),expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),rules=dict(default_percent=parsed['percent'],overrides=[]))
 if parsed['kind']=='exclude_earlier':
  p['rules']['exclude_verified_percent_today']=sorted(set(p['rules'].get('exclude_verified_percent_today',[])+[parsed['percent']]))
 elif parsed['kind']=='contains':
  p['rules']['overrides']=[r for r in p['rules'].get('overrides',[]) if r['fragment']!=parsed['fragment']]+[dict(fragment=parsed['fragment'],percent=parsed['percent'])]
 else:p['rules']['default_percent']=parsed['percent']
 p['last_human_job_id']=job['id'];p.setdefault('source_refs',[]).append(dict(job_id=job['id'],request_text=text))
 p['signature']=signature(p)
 if w.get(key):w.save(key,p)
 else:w.save(key,p,insert=True)
 return status_text(w.get(key) or p),[dict(name='catalog_price_command',command_key=key,status='requested',wb_writes=0)]
