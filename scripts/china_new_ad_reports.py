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
 if old and now-datetime.fromisoformat(old['observed_at'])<timedelta(hours=2):return old
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
 result=dict(observed_at=now.isoformat(),period_from=str(start),period_to=str(end),cutoff_msk=cutoff.astimezone(MSK).isoformat(),stock=stock,prices=prices,campaigns=campaigns,orders=orders,products=rows,protected=sorted(protected),policy=policy,config=Transport(io).config(),wb_writes=0)
 io.put(cache,result) if old else io.create(cache,result)
 return result

def choose(s,maximum=12):
 active={n['nm_id'] for c in s['campaigns'].values() for n in c.get('nm_settings',[])};protected=set(s['protected'])
 prices={p['nmID']:p for p in s['prices']};stocks={};counts={}
 for st in s['stock']:
  if st.get('article'):stocks.setdefault(st['article'].casefold(),[]).append(st)
 for o in s['orders']:counts[o['nmId']]=counts.get(o['nmId'],0)+1
 policy=s['policy'];groups={'orders':[],'demand':[]};rejected=0
 for row in s['products']:
  nm=int(row['nm_id']);article=row['sa_name'];p=prices.get(nm);st=stocks.get(article.casefold(),[]);log=policy['logistics_by_nm'].get(str(nm))
  if nm in active or nm in protected or not p or len(st)!=1 or not log:continue
  st=st[0];f=row.get('finished_orders');paid=row.get('is_payed');views=row.get('open_card_count');orders=row.get('funnel_orders_count')
  if not f or f<3 or paid is None or not views or orders is None or st.get('stock') is None or st.get('reserve') is None or st.get('price') is None:rejected+=1;continue
  free=max(0,st['stock']-st['reserve']);price=p['sizes'][0]['discountedPrice'];buyout=paid/f;cr=orders/views*100
  ratio=(row.get('price_after_spp') or 0)/(row.get('price_after_discount') or 1)
  if free<5 or ratio<=0:continue
  expected=buyout*(price*12*(1-.20-.05*ratio)-st['price']/100)-log['delivery_cny']*12-10-.05*price*12
  # Do not propose automatic reinstatement of previously advertised, now absent SKUs.
  if expected<=0 or row.get('advertisement') is None or row['advertisement']>0:continue
  group='orders' if counts.get(nm,0)>0 else 'demand'
  if group=='orders' and (f<5 or cr<1):continue
  if group=='demand' and cr<.5:continue
  bid=policy.get('category_minimum_minor',{}).get(str(row.get('subject_id')))
  if type(bid) is not int:continue
  groups[group].append(dict(nm_id=nm,article=article,bid_minor=bid,stock=free,paid=paid,finished=f,conversion=round(cr,2),recent_orders=counts.get(nm,0),expected_rub_per_order=round(expected,2),price_cny=price,history_advertisement=row['advertisement']))
 groups['orders'].sort(key=lambda r:(r['recent_orders'],r['finished'],r['stock']),reverse=True)
 groups['demand'].sort(key=lambda r:(r['finished'],r['stock']),reverse=True)
 # Reserve at most half the requested total for speculative demand tests; no profit/order ranking.
 n=min(len(groups['demand']),maximum//2);groups['orders']=groups['orders'][:maximum-n];groups['demand']=groups['demand'][:maximum-len(groups['orders'])]
 return groups,rejected

def render(p,rows,period,stock_at):
 from PIL import Image,ImageDraw,ImageFont
 import io
 def f(n,b=False):
  for root,name in [('/usr/share/fonts/truetype/dejavu/','DejaVuSans'+('-Bold' if b else '')+'.ttf'),('C:/Windows/Fonts/','arialbd.ttf' if b else 'arial.ttf')]:
   try:return ImageFont.truetype(root+name,n)
   except OSError:pass
  return ImageFont.load_default(size=n)
 pages=[]
 for camp in p['items']:
  for off in range(0,len(camp['skus']),12):
   batch=camp['skus'][off:off+12];im=Image.new('RGB',(1700,400+len(batch)*100),'#f2f6fa');d=ImageDraw.Draw(im)
   d.rectangle((0,0,1700,140),fill='#203c50');d.text((25,20),'Китай · '+('товары с заказами' if camp['group']=='orders' else 'проверка спроса'),font=f(34,True),fill='white');d.text((25,80),'Бюджет '+str(camp['budget_cny'])+' ¥ · без автопополнения · запуск только после подтверждения',font=f(23),fill='white')
   for x,h in [(25,'Артикул'),(500,'Выкуп / спрос'),(1150,'МойСклад'),(1430,'CPC, ¥')]:d.text((x,165),h,font=f(24,True),fill='#243d50')
   for i,item in enumerate(batch):
    r=rows[item['nm_id']];y=215+i*100;d.rectangle((15,y,1685,y+94),fill='white');d.text((25,y+20),r['article'],font=f(23,True),fill='#243d50');d.text((500,y+12),str(r['paid'])+'/'+str(r['finished'])+'; клик → заказ '+str(r['conversion'])+'%',font=f(22),fill='#243d50');d.text((500,y+48),'Заказы за недавний период: '+str(r['recent_orders']),font=f(21),fill='#657985');d.text((1180,y+22),str(r['stock']),font=f(24),fill='#243d50');d.text((1430,y+22),str(item['bid_minor']/100),font=f(24,True),fill='#243d50')
   for i,line in enumerate(['Выкуп/конверсия: '+period+'; остатки МойСклад: '+stock_at[:16]+'. Выборки малы.', 'Клик → заказ: заказы воронки / клики (открытия страницы товара) MPStats. ДРР от заказов 5%; прибыль предварительная.', 'Лимит — на РК, не на SKU. При нуле заказов ДРР неопределена. Пауза возможна досрочно.', 'Все части связаны с одним планом двух РК. Ответ «делай» на любую часть подтверждает весь план.']):d.text((25,im.height-145+i*31),line,font=f(19),fill='#657985')
   b=io.BytesIO();im.save(b,format='PNG');pages.append(b.getvalue())
 return pages

def process_requests(io):
 requests_=io.db('telegram_api_cache?cache_key=like.'+quote(REQUEST+'*',safe='')+'&payload->>status=eq.pending&select=cache_key,payload&limit=20')
 for entry in requests_:
  req=entry['payload'];key=entry['cache_key'];io.put(key,dict(req,status='collecting'))
  try:
   s=source(io);number=re.search(r'(\d+)\s*(?:арт|товар|кандидат)',req['request_text'],re.I);maximum=min(50,max(2,int(number[1]))) if number else 12
   groups,unassessed=choose(s,maximum)
   if not all(groups.values()):raise ValueError('Недостаточно обоснованных кандидатов для обеих целей; неполные или убыточные позиции не добавляю ради количества')
   minimum=max(s['config'].get('minTopUp',0),s['config'].get('minDailyLimit',0))
   if s['config'].get('currency')!='CNY' or minimum<=0 or minimum%100:raise ValueError('Минимум бюджета CNY не подтверждён')
   budget=minimum//100
   if budget>100:raise ValueError('Минимальный бюджет вырос выше согласованных 100 ¥ — требуется отдельное согласование')
   stamp=datetime.now(timezone.utc);pid='new-ad-test-'+str(req['job_id']);items=[]
   for group,rows in groups.items():items.append(dict(id=group,kind='ad_create_campaign',group=group,name='Китай тест '+str(req['job_id'])+' '+group,skus=[{k:r[k] for k in ['nm_id','article','bid_minor']} for r in rows],payment_type='cpc',bid_type='manual',placements=['recommendations'],budget_cny=budget,daily_limit_minor=budget*100,carry_over_enabled=False,auto_topup=False))
   p=dict(plan_id=pid,chat_id=CHAT,bot_id=BOT,execution_kind='ad_create_campaigns',items=items,plan_sha256=digest(items),created_at=stamp.isoformat(),expires_at=(stamp+timedelta(hours=6)).isoformat(),report_message_ids=[],price_changes=False,unassessed=unassessed,source_observed_at=s['observed_at'])
   validate_plan(p);rows={r['nm_id']:r for g in groups.values() for r in g};images=render(p,rows,s['period_from']+' — '+s['period_to'],s['observed_at'])
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

