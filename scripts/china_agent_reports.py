"""Shared report recipes: scheduled generators, explicit repeats and scoped PNG variants.

Preparing an image never creates marketplace execution authority. Existing scheduled
delivery identities are separate from request/job identities.
"""
import base64,copy,hashlib,io,json,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow');PREFIX='CHINA_AGENT_REPORT:'
RECIPES={
 'advertising':dict(title='ДРР и расходы',schedule='07:30 МСК',generator='china_advertising_daily',formats=['png'],period='3 полных дня; группировка по РК'),
 'budgets':dict(title='Бюджеты РК',schedule='07:30 МСК',generator='china_advertising_daily',formats=['png'],period='срез с фактическим временем'),
 'loss':dict(title='Товары, требующие внимания',schedule='после подтверждённой утренней рекламной пары',generator='china_agent_reports',formats=['png'],period='30 полных дней; динамика с даты оценки'),
 'price_morning':dict(title='Утренние предложения по ценам',schedule='10:30 МСК',generator='china_morning_pair',formats=['text','png'],period='действующая методика 4 полных дней'),
 'price_control':dict(title='Контроль изменений цен',schedule='10:30 МСК',generator='china_morning_pair',formats=['text','png'],period='равные полные периоды до/после'),
 'price_day':dict(title='Дневные предложения по ценам',schedule='15:00 МСК',generator='china_coverage_worker',formats=['text','png'],period='3 полных дня + неполный сегодня'),
 'growth':dict(title='Кандидаты в РК / повышение ставок',schedule='по запросу; без автоматического применения',generator='china_growth_candidates',formats=['png'],period='2–14 полных дней'),
 'ad_trend':dict(title='Последовательный рост стоимости заказа',schedule='по запросу',generator='china_ad_cost_png',formats=['png'],period='2–90 полных дней')}
RECIPES['actions']=dict(title='Выполненные изменения',schedule='по запросу',generator='china_experience',formats=['png'],period='фактические даты проверенного исполнения')
RECIPES['outcomes']=dict(title='Результаты изменений цен и рекламы',schedule='в существующем ежедневном отчёте; отдельно по запросу',generator='china_change_observation',formats=['png'],period='равные полные периоды; прогноз и закрытая прибыль раздельно')

def catalog():return dict(reports=RECIPES,timezone='Europe/Moscow',schedules_unchanged=True,repeat='Явная просьба создаёт отдельный request identity; плановые квитанции не сбрасываются',changes='Только подтверждённый конкретный план, не сам отчёт')

def font(size,bold=False):
 from PIL import ImageFont
 for path in ['/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if bold else '')+'.ttf','C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf')]:
  try:return ImageFont.truetype(path,size)
  except OSError:pass
 return ImageFont.load_default(size=size)

def pages(title,subtitle,rows,footer):
 from PIL import Image,ImageDraw
 lines=[]
 scratch=ImageDraw.Draw(Image.new('RGB',(1500,100)))
 for row in rows:
  line=''
  for word in str(row).split():
   trial=(line+' '+word).strip()
   if scratch.textlength(trial,font=font(23))>1410 and line:lines.append(line);line=word
   else:line=trial
  lines.append(line);lines.append('')
 if not lines:lines=['Действий, требующих внимания, не выявлено.']
 result=[]
 for offset in range(0,len(lines),48):
  part=lines[offset:offset+48];im=Image.new('RGB',(1500,300+len(part)*36),'#eff5f9');d=ImageDraw.Draw(im)
  d.rectangle((0,0,1500,140),fill='#203c50');d.text((28,22),title,font=font(33,True),fill='white');d.text((28,83),subtitle,font=font(22),fill='white')
  for i,line in enumerate(part):d.text((30,170+i*36),line,font=font(23),fill='#263f53')
  d.text((28,im.height-75),footer[:120],font=font(18),fill='#687e8b');d.text((28,im.height-43),'Рекомендации не применены. Повтор отчёта не является подтверждением изменений.',font=font(18),fill='#687e8b')
  b=io.BytesIO();im.save(b,format='PNG');result.append(b.getvalue())
 return result

def freeze(w,job,kind,images,meta):
 if job.get('chat_id')!=-1004342917488 or not images:raise ValueError('Report scope')
 key='china_agent:requested_report:v1:'+str(job['id'])+':'+kind
 stored=w.get(key)
 value=dict(status='frozen',job_id=job['id'],chat_id=job['chat_id'],kind=kind,meta=meta,files=[dict(data=base64.b64encode(b).decode(),sha256=hashlib.sha256(b).hexdigest()) for b in images],execution_authorized=False)
 if stored is None:w.save(key,value,insert=True);stored=w.get(key)
 if not stored or stored['job_id']!=job['id'] or stored['chat_id']!=job['chat_id']:raise ValueError('Frozen report scope')
 return dict(status='ready',marker='\n[[ПРЕДЛОЖЕНИЯ]]\n'.join(PREFIX+key+':'+str(i) for i in range(len(stored['files']))),**meta,wb_writes=0,execution_authorized=False)

def photo(w,chat,text):
 if not text.startswith(PREFIX):return None
 key,index=text[len(PREFIX):].rsplit(':',1);p=w.get(key)
 if not p or p['status']!='frozen' or p['chat_id']!=chat or p['job_id']!=getattr(w,'active_question_id',None):raise PermissionError('Requested report scope')
 part=p['files'][int(index)];data=base64.b64decode(part['data'],validate=True)
 if hashlib.sha256(data).hexdigest()!=part['sha256']:raise ValueError('Report image hash')
 return data,RECIPES[p['kind']]['title']+' · '+p['meta'].get('period','')+' · '+('повтор исходного среза' if p['meta'].get('repeat') else 'по запросу')+'. Изменения не применены.'+(' Только просмотр; для исполнения нужен ежедневный PNG.' if p['meta'].get('actions_not_bound') else '')

def archive(w,kind,day):
 if kind in ['advertising','budgets']:
  p=w.get('china_agent:advertising_artifacts:'+day+':v2') or w.get('china_agent:advertising_artifacts:'+day+':v1') or {};which='drr' if kind=='advertising' else 'budgets';parts=[f for f in p.get('files',[]) if f.get('kind','').split(':')[0]==which]
  if not parts:raise ValueError('Исходный PNG за '+day+' недоступен')
  return [base64.b64decode(f['b64'],validate=True) for f in parts],dict(period=p.get('bundle',{}).get('period',day),repeat=True,source_key='china_agent:advertising_artifacts:'+day+':v1')
 if kind=='loss':
  key='china_agent:loss_report:'+day+':v2';p=w.get(key) or {};parts=p.get('files',[])
  if not parts:raise ValueError('Исходный отчёт внимания за '+day+' недоступен')
  result=[]
  for part in parts:
   b=base64.b64decode(part['data'],validate=True)
   if hashlib.sha256(b).hexdigest()!=part['sha256']:raise ValueError('Archived PNG hash')
   result.append(b)
  return result,dict(period=day,repeat=True,source_key=key)
 if kind.startswith('price_'):
  commands={'price_morning':['/china_morning_pair_candidates','/china_price_daily_report'],'price_control':['/china_morning_pair_control'],'price_day':['/china_price_intraday_raise']}
  start=datetime.fromisoformat(day).replace(tzinfo=MSK);end=start+timedelta(days=1)
  rows=w.db('GET','business_agent_jobs',params={'agent_id':'eq.china','chat_id':'eq.-1004342917488','status':'eq.done','created_at':'gte.'+start.isoformat(),'and':'(created_at.lt.'+end.isoformat()+')','select':'id,request_text,answer,tool_trace','order':'id.desc','limit':200}) or []
  matches=[r for r in rows if r['request_text'] in commands[kind] and r.get('answer')]
  if not matches:raise ValueError('Доставленный ценовой отчёт за '+day+' не найден')
  r=matches[0];return pages(RECIPES[kind]['title'],day+' · исходная методика',r['answer'].splitlines(),'Исходный сохранённый ответ; не новая проверка цены'),dict(period=day,repeat=True,source_job_id=r['id'])
 raise ValueError('Этот вид отчёта пересчитывается по запросу, а не копируется')

def make(w,job,kind,days=3,nm_ids=(),repeat=False,report_day=None):
 if kind=='outcomes':
  from china_change_observation import MANIFEST,ROOT as OUTCOME
  from china_table_png import render
  manifest=w.get(MANIFEST) or {};table=[]
  for eid in reversed(manifest.get('event_ids',[])):
   record=w.get(OUTCOME+eid) or {}
   for row in record.get('rows',[]):
    if nm_ids and row['nm_id'] not in nm_ids:continue
    b,a=row['before'],row['after'];r=row['result'];change=record.get('action',{});before,after=change.get('before'),change.get('after')
    fmt=lambda v:'нет данных' if v is None else str(round(v,2))
    result='Ожидаемая/предварительная: '+fmt(b['expected'].get('value'))+' → '+fmt(a['expected'].get('value'))+' ₽\nФактическая закрытая: '+('нет данных' if b['actual'].get('value') is None or a['actual'].get('value') is None else fmt(b['actual']['value'])+' → '+fmt(a['actual']['value'])+' ₽')
    metrics='Все показы '+fmt(b.get('general_traffic',{}).get('total_impressions'))+' → '+fmt(a.get('general_traffic',{}).get('total_impressions'))+'; все клики '+fmt(b.get('views'))+' → '+fmt(a.get('views'))+'; заказы '+str(b['orders'])+' → '+str(a['orders'])+'; клик-заказ '+fmt(b['click_order_pct'])+' → '+fmt(a['click_order_pct'])+'%; ДРР '+fmt(b['actual_drr_pct'])+' → '+fmt(a['actual_drr_pct'])+'%; выкуп '+fmt(b['outcomes']['buyout_pct'])+' → '+fmt(a['outcomes']['buyout_pct'])+'%'
    ab,aa=b.get('advertising_funnel',{}),a.get('advertising_funnel',{})
    metrics+='\nРеклама отдельно: показы '+fmt(ab.get('views'))+' → '+fmt(aa.get('views'))+'; клики '+fmt(ab.get('clicks'))+' → '+fmt(aa.get('clicks'))+'; CTR '+fmt(ab.get('ctr_pct'))+' → '+fmt(aa.get('ctr_pct'))+'%'
    kind_=change.get('kind');label='Цена '+str(before)+' → '+str(after)+' ¥' if kind_=='price_change' else 'Ставка '+str(before/100)+' → '+str(after/100)+' ¥' if kind_=='bid_change' else 'Исключение SKU из РК '+str(change.get('campaign_id')) if kind_=='sku_exclusion' else 'Запуск РК '+str(change.get('campaign_id'))
    at=datetime.fromisoformat(record['started_at'].replace('Z','+00:00')).astimezone(MSK).strftime('%d.%m.%Y %H:%M МСК')
    table.append([row['article'],label+'\n'+at+'\n'+b['period_from']+'–'+b['period_to']+' → '+a['period_from']+'–'+a['period_to'],result,metrics,r['recommendation']])
  if not table:table=[['Все зарегистрированные изменения','До даты оценки блок не публикуется','Нет завершённого сравнения','Нет данных ≠ 0','Сроки и пробелы сохранены; автоматических изменений нет']]
  images=render(['Артикул','Изменение / периоды','Общая прибыль','Показатели','Рекомендация'],table,'Китай · результаты изменений')
  return freeze(w,job,kind,images,dict(period=manifest.get('checked_day','нет свежего среза'),repeat=False,source_key=MANIFEST))
 if kind not in RECIPES:raise ValueError('Неизвестный отчёт; сначала list_reports')
 if type(days) is not int or not 1<=days<=90:raise ValueError('Период1–90дней')
 today=w.now.astimezone(MSK).date();day=report_day or str(today)
 if datetime.fromisoformat(day).date()>today:raise ValueError('Будущего отчёта нет')
 if repeat:
  images,meta=archive(w,kind,day);return freeze(w,job,kind,images,meta)
 if kind in ['advertising','budgets']:
  if days!=3:raise ValueError('Согласованный новый формат — 3 полных дня; другой период требует отдельного расчёта')
  from china_price_apply import IO
  from china_advertising_v2 import prepare
  from china_advertising_v2_png import render as grouped_render
  intraday=day==str(today) and bool(re.search(r'сейчас|текущ|сегодня|до вечера|на данный',job['request_text'],re.I))
  if intraday:
   from china_advertising_intraday import prepare as current_report
   b=current_report(IO(),day)
  else:b=prepare(IO(),day)
  if nm_ids:
   for c in b['campaigns']:c['focus']=[r for r in c['focus'] if r['nm'] in nm_ids]
  family='drr' if kind=='advertising' else 'budgets';parts=[f['bytes'] for f in grouped_render(b) if f['family']==family or intraday]
  return freeze(w,job,kind,parts,dict(period=b['days'][0]+' — '+b['days'][-1],repeat=False,format_version=b['version'],actions_not_bound=True,note='Просмотр; исполнение только по привязанному ежедневному PNG'))
 if kind=='actions':
  from china_experience import decision_context
  events=decision_context(w,nm_ids)['experiences'];labels=dict(w.catalog());lines=[]
  for e in events:
   a=e.get('action') or {}
   if e.get('record_type')!='verified_action':continue
   at=datetime.fromisoformat(e['started_at'].replace('Z','+00:00')).astimezone(MSK)
   if (today-at.date()).days>=days:continue
   names=', '.join(a.get('article') or labels.get(str(n),str(n)) for n in a.get('nm_ids',[]))
   if a['kind']=='bid_change':action=str(a['before']/100)+' → '+str(a['after']/100)+' ¥'
   elif a['kind']=='sku_exclusion':action='отключено от рекламы'
   elif a['kind']=='new_campaign':action='создана и запущена РК'
   else:action=str(a.get('before'))+' → '+str(a.get('after'))+' · цена'
   lines.append(names+' · '+action+' · '+at.strftime('%d.%m %H:%M МСК')+(' · РК '+str(a['campaign_id']) if a.get('campaign_id') else ''))
  meta=dict(period=str(today-timedelta(days=days-1))+' — '+str(today),repeat=False,memory_used=True)
  return freeze(w,job,kind,pages('Китай · выполненные изменения',meta['period'],lines,'Только проверенные квитанции. Исполнение не означает улучшение прибыли.'),meta)
 if kind=='growth':
  from china_growth_candidates import collect
  scan=collect(w,days=days);rows=[r for r in scan['rows'] if not nm_ids or r['nm_id'] in nm_ids]
  lines=[r['article']+' · РК '+str(r['campaign_id'])+' · '+('добавить' if r['kind']=='ad_add_sku' else str(r['old_minor']/100)+' →')+' '+str(r['target_minor']/100)+' ¥ · '+r['reason'] for r in rows]
  meta=dict(period=scan['period_from']+' — '+scan['period_to'],observed_at=scan['observed_at'],memory_used=True,repeat=False)
  return freeze(w,job,kind,pages(RECIPES[kind]['title'],meta['period']+' · цель ДРР5%',lines,'Свежие минимумы WB; экономика предварительная, прошлый опыт не гарантия'),meta)
 if kind=='ad_trend':
  from china_ad_cost_png import answer
  value=answer(w,dict(job,request_text='Покажи стоимость рекламного заказа за '+str(days)+' полных дней'),[])
  if value is None:raise ValueError('Отчёт тренда не сформирован')
  return dict(status='ready',marker=value[0],wb_writes=0,repeat=False)
 if kind=='advertising':
  from china_three_day_ads import load,build
  from china_ad_rule import campaign_rows,minimums
  from china_price_apply import IO
  from china_loss_ads import current
  sources=load(w,days);report=build(sources,today,dict(w.catalog()),days);rows=[r for r in report['rows'] if not nm_ids or int(r['nm']) in nm_ids]
  lines=[];io_=IO();live=current(io_);scoped=campaign_rows(sources,dict(w.catalog()))
  for r in rows:
   if r['drr'] is None or r['drr']>5 or r['rising_all_days']:
    actions=[]
    for cid,c in live.items():
     member=next((n for n in c.get('nm_settings',[]) if str(n['nm_id'])==r['nm']),None)
     stat=next((v for v in scoped if v['campaign_id']==cid and v['nm']==r['nm']),None)
     if not member or not stat or stat['drr'] is None or stat['drr']<=5:continue
     if cid==41155909:actions.append('РК '+str(cid)+': отдельная оценка безубыточности119');continue
     old=member.get('bids_kopecks',{}).get('recommendations');minimum=minimums(io_,cid,{int(r['nm'])})[int(r['nm'])]
     if stat['drr']>10 or old is not None and old<=minimum:action='исключить только этот SKU' if len(c['nm_settings'])>1 else 'согласовать отдельное решение для РК из одного SKU'
     elif old is not None:action='ставка '+str(old/100)+' → '+str(minimum/100)+' ¥'
     else:action='не подтверждена текущая ставка; требуется проверка'
     actions.append('РК '+str(cid)+': '+action)
    if not actions:continue # Already disconnected/no action is not an attention item.
    values=' → '.join('н/д' if x['drr'] is None else ('%.2f%%'%x['drr']).replace('.',',') for x in r['daily']);lines.append(r['article']+' · ДРР по дням: '+values+' · заказов '+str(sum(x['orders'] for x in r['daily']))+' · '+'; '.join(actions))
  meta=dict(period=report['days'][0]+' — '+report['days'][-1],repeat=False)
  return freeze(w,job,kind,pages('Китай · ДРР по дням',meta['period']+' · только требует внимания',lines,'Рекламная атрибуция, не все WBзаказы; без заказов ДРР неопределена'),meta)
 if kind=='loss':
  images,meta=fresh_loss(w,nm_ids);return freeze(w,job,kind,images,meta)
 # Point-in-time budgets and rule-based price reports must keep their original methodology.
 images,meta=archive(w,kind,day);meta['note']='Исходный срез с указанной датой, не новый пересчёт';return freeze(w,job,kind,images,meta)

def fresh_loss(w,nm_ids=()):
 from china_price_apply import IO
 from china_new_ad_reports import source
 from china_growth_candidates import economics,review
 io_=IO();s=source(io_);active={n['nm_id'] for c in s['campaigns'].values() for n in c.get('nm_settings',[])};prices={p['nmID']:p for p in s['prices']};stocks={r.get('article','').casefold():r for r in s['stock']};rows=[];unassessed=0
 for r in s['products']:
  nm=int(r['nm_id']);article=r['sa_name']
  if nm_ids and nm not in nm_ids:continue
  if nm in active:continue # Current advertising problems are already covered by the RC report.
  p=prices.get(nm);st=stocks.get(article.casefold());f=r.get('finished_orders') or 0
  if not p or not st or f<5:unassessed+=1;continue
  if not r.get('orders_sum') or r.get('advertisement') is None:unassessed+=1;continue
  expected=economics(r,p['sizes'][0]['discountedPrice'],st,s['policy'],drr=r['advertisement']/r['orders_sum'])
  if expected is None:unassessed+=1;continue
  if expected>=0:continue
  rv=review(io_,nm,r)
  if not rv['complete']:unassessed+=1;continue
  # An excluded SKU is not itself a new action: only a fresh verified quality signal qualifies.
  evidence=[e for e in rv.get('negative',[]) if e.get('rating') is not None and e['rating']<=3 and s['period_from']<=str(e.get('date') or '')[:10]<=str(w.now.astimezone(MSK).date())]
  if not evidence:continue
  latest=evidence[0];reason=(latest.get('text') or latest.get('cons') or 'Низкая оценка качества')[:260]
  if not re.search(r'качеств|брак|шов|ворс|мех|замш|слом|дыр|дефект|материал|фурнитур|подклад',reason,re.I):continue
  rows.append(article+' · выкуп '+str(r['is_payed'])+'/'+str(f)+' завершённых. Отзыв '+latest.get('date','')[:10]+': «'+reason+'». Рекомендация: проверить 3 экземпляра партии по указанному дефекту; после проверки — предметный ответ. Реклама отключена, повторное отключение не предлагается.')
 period=s['period_from']+' — '+s['period_to'];meta=dict(period=period,observed_at=s['observed_at'],repeat=False,unassessed=unassessed,memory_used=True)
 # Do not print the non-informative waiting block before the actual evaluation date.
 from china_experience import decision_context
 due=[e for e in decision_context(w)['experiences'] if 'loss-20261022-107' in e.get('source_key','') and e.get('comparison',{}).get('evaluate_from','9999')<=str(w.now.astimezone(MSK).date())]
 cohort=w.get('china_agent:loss_cohort:v1') or {}
 from china_change_observation import compact,MANIFEST,ROOT as OUTCOME
 observation_manifest=w.get(MANIFEST)
 if observation_manifest:
  rows+=compact(w)
  if observation_manifest.get('status')!='complete_coverage':rows.append('Контроль изменений неполон: '+str(observation_manifest.get('counts',{}))+'. Недостающие расходы/когорты не заменены нулём; вывод об отсутствии проблем не сформирован.')
  covered=set()
  for eid in observation_manifest.get('event_ids',[]):
   observed=w.get(OUTCOME+eid) or {}
   if observed.get('window',{}).get('final'):covered.update(r['nm_id'] for r in observed.get('rows',[]))
  remaining=[int(i['nm_id']) for i in cohort.get('items',[]) if int(i['nm_id']) not in covered and (not nm_ids or int(i['nm_id']) in nm_ids)]
  if remaining and cohort.get('evaluate_from','9999')<=str(w.now.astimezone(MSK).date()):rows+=loss_dynamics(w,s,cohort,remaining)
  due=[]
 elif cohort.get('evaluate_from','9999')<=str(w.now.astimezone(MSK).date()):
  rows+=loss_dynamics(w,s,cohort,nm_ids);due=[]
 for event in due:
  observations=event.get('observations') or [];result=observations[-1] if observations else {};before=result.get('before') or {};after=result.get('after') or {};b,a=before.get('total_profit'),after.get('total_profit');nm=event.get('action',{}).get('nm_ids',[None])[0];article=event.get('action',{}).get('article') or next((r['sa_name'] for r in s['products'] if int(r['nm_id'])==nm),'Артикул не определён')
  if b is None or a is None:rows.append(article+' · общая прибыль: нет данных. Нужны сопоставимые закрытые расходы и результат за '+event['comparison']['before_from']+' — '+event['comparison']['before_to']+' и '+event['comparison']['after_from']+' — '+event['comparison']['after_to']+'. Нулём не заменяем.')
  else:rows.append(article+' · общая прибыль '+str(b)+' → '+str(a)+' '+str(after.get('currency'))+'; Δ '+str(a-b)+'. Метод: '+str(after.get('profit_method'))+'.')
 footer='Экономика предварительная; источник МойСклад/WB/MPStats. Не оценено: '+str(unassessed)+'. Динамика — с даты оценки.'
 return pages('Китай · что ещё требует внимания',period+' · только новые необходимые действия',rows,footer),meta

def loss_dynamics(w,source,cohort,nm_ids=()):
 """Approved constant-DRR expected method, never a claimed closed-cohort profit."""
 from china_analytic_dialog import Analyst
 from china_growth_candidates import economics
 ids=[int(x['nm_id']) for x in cohort['items'] if not nm_ids or int(x['nm_id']) in nm_ids];reader=Analyst(w,{},[]);periods=[]
 for a,b in [(cohort['before_from'],cohort['before_to']),(cohort['after_from'],cohort['after_to'])]:
  try:periods.append({int(r['nm_id']):r for r in reader.live('products',ids,a,b)['rows']})
  except Exception:periods.append({})
 products={int(r['nm_id']):r for r in source['products']};prices={p['nmID']:p for p in source['prices']};stocks={r.get('article','').casefold():r for r in source['stock']};lines=[]
 for item in cohort['items']:
  nm=int(item['nm_id']);article=item['article']
  if nm not in ids:continue
  values=[]
  for period in periods:
   row=period.get(nm);own=products.get(nm);p=prices.get(nm);stock=stocks.get(article.casefold())
   if not row or not own or not p or not stock:values.append(None);continue
   counts=[row.get('orders_count'),row.get('funnel_orders_count')];spark=row.get('sparkline_orders')
   if not isinstance(spark,list) or counts[0] is None or counts[0]!=counts[1] or counts[0]!=sum(spark) or not row.get('orders_sum') or row.get('advertisement') is None:values.append(None);continue
   expected=economics(own,p['sizes'][0]['discountedPrice'],stock,source['policy'],drr=row['advertisement']/row['orders_sum'])
   values.append(expected*counts[0] if expected is not None else None)
  if any(v is None for v in values):lines.append(article+' · общая прибыль: нет данных · нужны сопоставимые счётчики заказов и расходы; не0.');continue
  b,a=values;lines.append(article+' · ожидаемая общая прибыль '+str(round(b))+' → '+str(round(a))+' ₽ · Δ '+str(round(a-b))+' ₽ · проверить итог после закрытия расходов'+(' (без нашего отключения)' if item.get('no_new_ad_change') else '')+'.')
 lines.append('Динамика '+cohort['before_from']+'–'+cohort['before_to']+' → '+cohort['after_from']+'–'+cohort['after_to']+'. Предварительная ожидаемая оценка: общий объём × экономика при текущей цене, собственном завершённом выкупе и ДРР каждого периода. Курс12₽/¥; неизвестные общие удержания исключены, не0. Это не закрытая чистая прибыль и не доказательство эффекта рекламы.')
 return lines

def daily_loss():
 """Run after actual advertising pair delivery; share the existing daily receipt."""
 from conversion_watches import runtime,saved_network_guard
 from china_analytic_dialog import reading
 from china_price_apply import IO
 import requests
 w=runtime();day=str(w.now.astimezone(MSK).date());key='china_agent:loss_report:'+day+':v2'
 prior=w.get(key)
 if prior and prior.get('status') in ['delivered','sending','uncertain']:return prior['status']
 pair=w.get('china_agent:advertising_delivery:'+day+':v1') or {}
 if pair.get('status')!='delivered' or {p.get('kind','').split(':')[0] for p in pair.get('parts',[]) if p.get('status')=='sent' and p.get('message_id')}!={'drr','budgets'}:return 'waiting_for_advertising_pair'
 if prior and prior.get('status') not in ['frozen']:return 'requires_review'
 if not prior:
  with saved_network_guard(),reading():images,meta=fresh_loss(w)
  prior=dict(status='frozen',report_date=day,chat_id=-1004342917488,bot_id=8780468043,format='attention_only_combined_v3',meta=meta,files=[dict(data=base64.b64encode(b).decode(),sha256=hashlib.sha256(b).hexdigest()) for b in images],parts=[],wb_writes=0)
  if not w.save(key,prior,insert=True):return 'concurrent_generation'
 io_=IO();me=io_.tg('getMe',{})
 if me.get('id')!=8780468043:raise PermissionError('Report bot identity')
 for index,part in enumerate(prior['files']):
  if index<len(prior['parts']) and prior['parts'][index].get('status')=='sent':continue
  data=base64.b64decode(part['data'],validate=True)
  if hashlib.sha256(data).hexdigest()!=part['sha256']:raise ValueError('Frozen daily report hash')
  prior['status']='sending';prior['parts'].append(dict(status='sending',sha256=part['sha256']));w.save(key,prior)
  try:
   response=requests.post('https://api.telegram.org/bot'+io_.bot+'/sendPhoto',data=dict(chat_id=-1004342917488,caption='Китай · требует внимания · '+day+'. Рекомендации не применены.'),files={'photo':('china-attention.png',data,'image/png')},timeout=40).json()
   if not response.get('ok'):raise RuntimeError('Telegram delivery not confirmed')
   receipt=response['result']
   if receipt.get('chat',{}).get('id')!=-1004342917488 or receipt.get('from',{}).get('id')!=8780468043 or not receipt.get('message_id'):raise RuntimeError('Unexpected receipt')
   prior['parts'][index]=dict(status='sent',sha256=part['sha256'],message_id=receipt['message_id'],receipt=receipt,sent_at=datetime.now(timezone.utc).isoformat());prior['status']='frozen';w.save(key,prior)
  except Exception:
   prior['status']='uncertain';w.save(key,prior);raise RuntimeError('Daily report delivery uncertain; blind retry blocked') from None
 prior['status']='delivered';prior['delivered_at']=datetime.now(timezone.utc).isoformat();w.save(key,prior);return 'delivered'

if __name__=='__main__':
 import sys,os
 if sys.argv[1:]!=['--daily-loss']:raise SystemExit('Expected --daily-loss')
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise SystemExit('Public main only')
 print(json.dumps(dict(status=daily_loss(),wb_writes=0)))


