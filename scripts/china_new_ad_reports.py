"""On-demand candidate collection and two-purpose PNGs; no WB write endpoints."""
import base64,hashlib,json,os,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote
from china_loss_control import CHAT,BOT,PLAN,digest
from china_new_ads import REQUEST,LATEST,Transport,deliver,validate_plan
MSK=ZoneInfo('Europe/Moscow')

def source(io):
 import requests
 from analytics.mpstats_probe import discover
 from analytics.mpstats_gaps import execute_reads
 now=datetime.now(timezone.utc);today=now.astimezone(MSK).date();end=today-timedelta(days=1);start=end-timedelta(days=29)
 cache='china_agent:new_ad_source:v1:'+str(today);old=io.get(cache)
 from china_experience import decision_context
 experience=decision_context(io)
 if old and now-datetime.fromisoformat(old['observed_at'])<timedelta(hours=2):
  from china_ad_retest import attach
  return attach(io,dict(old,experience=experience,memory_used=True))
 policy=io.get('china_agent:new_ad_economics_policy:v1')
 if not policy or policy.get('fx_rub_cny')!=12 or not policy.get('logistics_by_nm'):raise ValueError('Нет проверенной собственной модели COGS/логистики. Нужен сбор расходов, не нулевая подстановка.')
 def get(url,token,params=None):
  r=requests.get(url,headers={'Authorization':token},params=params,timeout=60)
  if not r.ok:raise RuntimeError('Read source HTTP '+str(r.status_code))
  return r.json()
 base='https://api.moysklad.ru/api/remap/1.2';token='Bearer '+os.environ['MOYSKLAD_API_TOKEN']
 stores=get(base+'/entity/store',token,{'limit':1000}).get('rows',[])
 stores=[s for s in stores if s.get('name')=='МСК' and not s.get('archived')]
 if len(stores)!=1:raise ValueError('Склад МСК в МойСклад не найден однозначно')
 stock=[];offset=0
 while True:
  j=get(base+'/report/stock/all',token,{'filter':'store='+stores[0]['meta']['href'],'stockMode':'all','limit':1000,'offset':offset});part=j.get('rows',[]);stock+=part
  if offset+len(part)>=j.get('meta',{}).get('size',offset+len(part)):break
  if not part or offset>20000:raise ValueError('Неполная пагинация МойСклад')
  offset+=len(part)
 prices=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
 if len(prices)>=1000:raise ValueError('Нужна полная пагинация цен WB')
 from china_loss_ads import current
 campaigns=current(io)
 orders=[];cursor=0;cutoff=datetime.now(timezone.utc)
 begin=datetime.combine(today-timedelta(days=2),datetime.min.time(),MSK)
 seen=set()
 while True:
  j=get('https://marketplace-api.wildberries.ru/api/v3/orders',io.token,{'limit':1000,'next':cursor,'dateFrom':int(begin.timestamp()),'dateTo':int(cutoff.timestamp())})
  part=j.get('orders',[])
  for r in part:
   if r['id'] not in seen:orders.append({k:r.get(k) for k in ['id','nmId','article','createdAt']});seen.add(r['id'])
  nxt=j.get('next')
  if not part or not nxt:break
  if nxt==cursor or len(seen)>20000:raise ValueError('Неполная пагинация заказов WB')
  cursor=nxt
 observations=[]
 calls=[dict(cabinet='token_3',tool='lk_wb_products',key='new_ad_candidates:'+str(today),priority=80,arguments=dict(date_from=str(start),date_to=str(end),start_row=0,end_row=1000))]
 def persist(cabinet,obs):
  if cabinet=='token_3' and obs.get('status')=='received' and obs.get('scope_verified') is True:observations.append(obs)
 def extra(call,checks,known):return execute_reads(call,checks,known,calls,{},persist,max_requests=1)
 discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
 if len(observations)!=1:raise ValueError('Не получена свежая полная статистика MPStats кабинета Китай')
 products=observations[0].get('data',{}).get('data',{})
 rows=products.get('data',[])
 if products.get('need_update')!=0 or (products.get('total')!=len(rows) and products.get('pagination_complete') is not True):raise ValueError('Статистика MPStats неполная; пропуски не нули')
 protected=set()
 # Preserve completed exclusions even when they are outside today's active campaign catalogue.
 for prefix in ['china_agent:ad_rule_execution:','china_agent:loss_ad_execution:']:
  saved=io.db('telegram_api_cache?cache_key=like.'+quote(prefix+'*',safe='')+'&select=payload&limit=200')
  if len(saved)>=200:raise ValueError('Неполная история исключений SKU')
  for entry in saved:
   e=entry['payload']
   for item in e.get('items',[]):
    if item.get('status')!='verified':continue
    before={n['nm_id'] for n in (item.get('before') or {}).get('nm_settings',[])};after={n['nm_id'] for n in (item.get('after') or {}).get('nm_settings',[])}
    if item.get('after') is not None:protected.update(before-after)
   if e.get('status')=='verified' and isinstance(e.get('before'),dict) and isinstance(e.get('after'),dict):
    for cid,b in e['before'].items():
     a=e['after'].get(str(cid)) or e['after'].get(cid)
     if a:protected.update({n['nm_id'] for n in b.get('nm_settings',[])}-{n['nm_id'] for n in a.get('nm_settings',[])})
 result=dict(observed_at=now.isoformat(),period_from=str(start),period_to=str(end),cutoff_msk=cutoff.astimezone(MSK).isoformat(),stock=stock,prices=prices,campaigns=campaigns,orders=orders,products=rows,protected=sorted(protected),policy=policy,config=Transport(io).config(),experience=experience,memory_used=True,wb_writes=0)
 # PostgreSQL JSON objects return string keys; compare the same wire representation.
 result=json.loads(json.dumps(result,allow_nan=False))
 from china_ad_retest import attach
 result=attach(io,result)
 io.put(cache,result) if old else io.create(cache,result)
 return result

def choose(s,maximum=12,nm_ids=(),manual_review=False):
 if s.get('memory_used') is not True:raise ValueError('Память действий не проверена; подбор заблокирован')
 from china_ad_retest import assess
 rows=assess(s,nm_ids,manual_review);groups={'orders':[],'demand':[]};rejected=0
 for row in rows:
  if row['eligible']:groups[row['group']].append(row)
  else:rejected+=1
 # Verified operational lesson: WB rejects a draft mixing different categories.
 # This existing recipe proposes exactly two purposes/budgets, so keep one
 # evidenced category per purpose and disclose omitted candidates, never fund extras.
 for group,candidates in groups.items():
  categories={r['subject_id'] for r in candidates if r['subject_id'] is not None}
  if not categories:groups[group]=[];continue
  category=max(categories,key=lambda cat:(sum(r['recent_orders'] for r in candidates if r['subject_id']==cat),sum(r['finished'] for r in candidates if r['subject_id']==cat),-int(cat)))
  rejected+=sum(r['subject_id']!=category for r in candidates);groups[group]=[r for r in candidates if r['subject_id']==category]
 groups['orders'].sort(key=lambda r:(r['recent_orders'],r['finished'],r['stock']),reverse=True)
 groups['demand'].sort(key=lambda r:(r['finished'],r['stock']),reverse=True)
 # Reserve at most half the requested total for speculative demand tests; no profit/order ranking.
 n=min(len(groups['demand']),maximum//2);groups['orders']=groups['orders'][:maximum-n];groups['demand']=groups['demand'][:maximum-len(groups['orders'])]
 return groups,rejected

def quote_groups(io,s,groups):
 # Owner8Nov: China is FBS. Availability is MoySklad MSK minus reserve;
 # published WB stock is not a prerequisite and this reader never publishes it.
 day=datetime.now(MSK).date().isoformat()
 memory=io.get('china_agent:advertising_full_growth:'+day+':v1:inputs')or{}
 if memory.get('cabinet')!='token_3':raise ValueError('Нет сохранённых минимумов кабинета Китай')
 out={};blocked=[]
 for group,rows in groups.items():
  ready=[r for r in rows if type(r.get('stock'))in(int,float) and r['stock']>0]
  blocked += [dict(nm_id=r['nm_id'],reason='Свободный остаток МойСклад МСК минус резерв не подтверждён')for r in rows if r not in ready]
  if not ready:continue
  refs=[c for c in s['campaigns'].values()if c.get('status')==9 and c.get('currency')=='CNY' and c.get('settings',{}).get('placements')==dict(search=False,recommendations=True) and {n['subject']['id']for n in c.get('nm_settings',[])}=={ready[0]['subject_id']}]
  if not refs:
   blocked += [dict(nm_id=r['nm_id'],reason='Нет подтверждённой категории РК для чтения минимальной ставки')for r in ready];continue
  reference=min(refs,key=lambda c:c['id']);cid=reference['id'];subject=ready[0]['subject_id']
  members={n['nm_id']for n in reference['nm_settings']if n['subject']['id']==subject}
  saved=memory.get('minimums',{}).get(str(cid),{}).get('bids',[])
  values={b['value']for n in saved if n.get('nm_id')in members for b in n.get('bids',[])if b.get('type')=='recommendation'and b.get('currency')=='CNY'and type(b.get('value'))is int}
  if len(values)!=1:
   blocked += [dict(nm_id=r['nm_id'],reason='В памяти нет однозначного минимума для РК '+str(cid)+', категории '+str(subject)+' и рекомендаций')for r in ready];continue
  remembered=next(iter(values));minimum={r['nm_id']:remembered for r in ready};step=s['config'].get('cpcStep')
  if type(step)is not int or step<=0:raise ValueError('Шаг CPC не подтверждён')
  quoted=[]
  for r in ready:
   bid=minimum.get(r['nm_id'])
   if type(bid)is not int or bid<=0 or bid%step or bid>s['config'].get('cpcMaxBid',0):blocked.append(dict(nm_id=r['nm_id'],reason='Точная минимальная ставка не подтверждена'));continue
   quoted.append(dict(r,bid_minor=bid,availability_basis='MoySklad_MSK_stock_minus_reserve',minimum_verified=True,minimum_source='saved_campaign_category_placement',minimum_reference_campaign_id=cid,minimum_subject_id=subject))
  if quoted:out[group]=quoted
 return out,blocked

def proposal_lines(camp,item,r,period):
 detail=r.get('economics_detail')or{}
 money=lambda v: 'нет данных' if v is None else f'{v:.2f}'
 return [
  r['article']+' · nmID '+str(item['nm_id'])+' · категория '+str(r.get('subject_id')),
  'Предложение: новая РК «'+camp['name']+'», рекомендации CPC; '+str(item['bid_minor']/100)+' CNY/клик.',
  'РК ещё не создана: ID появится после подтверждения. Минимум из памяти РК '+str(r.get('minimum_reference_campaign_id','?'))+'.',
  'Цена '+money(r.get('price_cny'))+' CNY; COGS '+money(detail.get('cogs_rub'))+' RUB; логистика '+money(detail.get('delivery_cny'))+' CNY.',
  'Свой выкуп '+str(r['paid'])+'/'+str(r['finished'])+'; МСК свободно '+str(r['stock'])+'; период '+period+'.',
  'Сценарий ДРР 5%: предварительный остаток '+money(r.get('expected_rub_per_order'))+' RUB/созданный заказ.',
  'Комиссия 20%, налог по модели 5%, FX 12 RUB/CNY, обработка 10 RUB; общие/обратные расходы неизвестны.',
  'Бюджет '+str(camp['budget_cny'])+' CNY на РК; лимит/день '+str(camp['daily_limit_minor']/100)+'; без автопополнения.'
 ]

def proposal_table(camp,rows):
 header=['Артикул','Цена, CNY','COGS, RUB','Свой выкуп','МСК свободно','При ДРР 5%, RUB/заказ','Рекомендация']
 table=[]
 for item in camp['skus']:
  r=rows[item['nm_id']];cost=(r.get('economics_detail')or{}).get('cogs_rub')
  table.append([r['article'],f"{r['price_cny']:.2f}",'нет данных' if cost is None else f'{cost:.0f}',
                str(r['paid'])+'/'+str(r['finished']),str(r['stock']),f"{r['expected_rub_per_order']:+.2f}",
                'Добавить; CPC '+f"{item['bid_minor']/100:.2f}"+' CNY'])
 return header,table

def render(p,rows,period,stock_at):
 from china_table_png import render as table_png
 from PIL import Image,ImageDraw,ImageFont
 import io
 def font():
  for path in ['C:/Windows/Fonts/arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
   try:return ImageFont.truetype(path,22)
   except OSError:pass
  return ImageFont.load_default(size=22)
 pages=[]
 for camp in p['items']:
  header,table=proposal_table(camp,rows)
  title='Китай · новая РК · рекомендации · '+str(len(camp['skus']))+' товаров'
  notes=[
   'РК «'+camp['name']+'». Бюджет '+str(camp['budget_cny'])+' CNY; лимит '+str(camp['daily_limit_minor']//100)+'/день; резерв на 3 дня '+str(camp['daily_limit_minor']*3//100)+' CNY.',
   'Свой выкуп: '+period+'. Цена/МСК: '+stock_at[:16]+' UTC. Минимум: память РК '+str(rows[camp['skus'][0]['nm_id']].get('minimum_reference_campaign_id','?'))+'.',
   'Экономика предварительная: сценарий ДРР 5%, не доказанная прибыль. Неизвестные расходы не ноль; выборка выкупа указана.',
   'Оценка после первого полного дня МСК вслед за запуском. Без автопополнения. Запуск — отдельным подтверждением нового PNG.'
  ]
  for blob in table_png(header,table,title):
   original=Image.open(io.BytesIO(blob)).convert('RGB');image=Image.new('RGB',(original.width,original.height+155),'#eff4f8');image.paste(original,(0,0));draw=ImageDraw.Draw(image)
   for i,line in enumerate(notes):draw.text((24,original.height+8+i*34),line,font=font(),fill='#526879')
   output=io.BytesIO();image.save(output,format='PNG');pages.append(output.getvalue())
 return pages

def process_requests(io,job_id=None):
 request_filter='eq.'+quote(REQUEST+str(job_id),safe='') if job_id is not None else 'like.'+quote(REQUEST+'*',safe='')
 requests_=io.db('telegram_api_cache?cache_key='+request_filter+'&payload->>status=eq.pending&select=cache_key,payload&limit=20')
 for entry in requests_:
  req=entry['payload'];key=entry['cache_key']
  if job_id is not None and req.get('job_id')!=job_id:continue
  io.put(key,dict(req,status='collecting'))
  try:
   s=source(io);number=re.search(r'(\d+)\s*(?:арт|товар|кандидат|штук)',req['request_text'],re.I);maximum=min(50,max(1,req.get('maximum_count')or int(number[1]))) if req.get('maximum_count')or number else 12
   nm_ids=req.get('nm_ids',[])
   if nm_ids:maximum=min(50,max(2,len(nm_ids)))
   if req.get('subject_ids'):
    s=dict(s,products=[r for r in s['products'] if r.get('subject_id') in req['subject_ids']])
   from china_proposal_final_review import complete
   s,groups,final_review,final_review_key=complete(io,s,req)
   unassessed=sum(v for k,v in final_review['counts'].items()if k!='ready')
   groups={k:v for k,v in groups.items()if v}
   if not groups:raise ValueError('Полная проверка завершена: готовых действий нет. Причины сохранены в итоговом журнале '+final_review_key)
   groups,quote_blockers=quote_groups(io,s,groups)
   if quote_blockers:raise ValueError('Итоговый подбор не отправлен: точные условия не подтверждены для '+str(quote_blockers))
   if not groups:raise ValueError('Нет подтверждённых ставок и совместимых РК для итогового подбора')
   minimum=max(s['config'].get('minTopUp',0),s['config'].get('minDailyLimit',0))
   if s['config'].get('currency')!='CNY' or minimum<=0 or minimum%100:raise ValueError('Минимум бюджета CNY не подтверждён')
   budget=minimum//100
   if budget>100:raise ValueError('Минимальный бюджет вырос выше согласованных 100 ¥ — требуется отдельное согласование')
   stamp=datetime.now(timezone.utc);pid='new-ad-test-'+str(req['job_id']);items=[]
   revision=req.get('revision')
   if revision:
    if not re.fullmatch(r'[a-z0-9-]{1,40}',revision):raise ValueError('Invalid proposal revision')
    pid+='-'+revision
   for group,rows in groups.items():items.append(dict(id=group,kind='ad_create_campaign',group=group,name='Китай тест '+str(req['job_id'])+' '+group,skus=[{k:r[k] for k in ['nm_id','article','bid_minor']} for r in rows],payment_type='cpc',bid_type='manual',placements=['recommendations'],budget_cny=budget,daily_limit_minor=budget*100,carry_over_enabled=False,auto_topup=False))
   p=dict(plan_id=pid,chat_id=CHAT,bot_id=BOT,execution_kind='ad_create_campaigns',group_policy='available_qualified_groups',requested_maximum=maximum,selected_count=sum(len(v)for v in groups.values()),candidate_evidence={str(r['nm_id']):r for rows in groups.values()for r in rows},final_review_key=final_review_key,final_checks_complete=final_review['status']=='complete',scope_counts=final_review['counts'],quote_blockers=quote_blockers,items=items,plan_sha256=digest(items),created_at=stamp.isoformat(),expires_at=(stamp+timedelta(hours=2)).isoformat(),report_message_ids=[],price_changes=False,unassessed=unassessed,source_observed_at=s['observed_at'])
   for row in p['candidate_evidence'].values():
    stock=next((v for v in s['stock'] if str(v.get('article','')).casefold()==row['article'].casefold()),{})
    if row.get('economics_detail'):continue
    row['economics_detail']=dict(cogs_rub=stock.get('price')/100 if type(stock.get('price'))in(int,float) else None,delivery_cny=(s['policy']['logistics_by_nm'].get(str(row['nm_id']))or{}).get('delivery_cny'),fx_rub_cny=12,scenario_drr_pct=5,unknown_costs=True)
   validate_plan(p);rows={int(n):r for n,r in p['candidate_evidence'].items()};images=render(p,rows,s['period_from']+' — '+s['period_to'],s['observed_at'])
   # Multi-page reports share one immutable plan; each delivered image binds the same scope.
   p['png_sha256']=hashlib.sha256(images[0]).hexdigest();io.create(PLAN+pid,p)
   for idx,blob in enumerate(images):
    if idx==0:deliver(io,p,blob)
    else:
     # Reuse the same delivery state machine through a per-part alias, then bind to the parent.
     from china_new_ads import BIND
     parent=io.get(PLAN+pid);part=dict(parent,plan_id=pid+'-page-'+str(idx),report_message_ids=[],png_sha256=hashlib.sha256(blob).hexdigest());io.create(PLAN+part['plan_id'],part)
     delivered=deliver(io,part,blob)
     if delivered.get('status')!='sent':raise ValueError('Часть PNG не доставлена достоверно; повторная отправка заблокирована')
     mid=delivered['message_id'];io.put(BIND+str(mid),dict(plan_id=pid,plan_sha256=parent['plan_sha256'],chat_id=CHAT,png_sha256=part['png_sha256']));parent['report_message_ids']=sorted(set(parent['report_message_ids']+[mid]));io.put(PLAN+pid,parent)
   io.put(key,dict(req,status='done',plan_id=pid));io.create(LATEST,dict(plan_id=pid)) if not io.get(LATEST) else io.put(LATEST,dict(plan_id=pid))
  except Exception as ex:
   reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__
   io.put(key,dict(req,status='blocked',reason=reason))
   notice='Рекламный тест не подготовлен: '+reason+'. Ничего не запущено; старые данные свежими не подменены.'
   delivery=key+':blocker'
   if io.create(delivery,dict(status='sending')):
    try:r=io.tg('sendMessage',dict(chat_id=CHAT,text=notice,reply_parameters=dict(message_id=req['reply_message_id'],allow_sending_without_reply=True)));io.put(delivery,dict(status='sent',message_id=r['message_id']))
    except Exception:io.put(delivery,dict(status='uncertain'))
