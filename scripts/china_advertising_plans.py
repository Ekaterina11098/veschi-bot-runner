"""Typed conversational advertising proposals, reply-bound consent and isolated execution."""
import copy,math,re,json
from datetime import datetime,timedelta,timezone
from china_loss_control import CHAT,BOT,PLAN,APPROVAL,digest,is_all,marker
P='china_agent:advertising_dialog_plan:v1:'
B='china_agent:advertising_dialog_message:v1:'
A='china_agent:advertising_dialog_approval:v1:'
E='china_agent:advertising_dialog_execution:v1:'
def iso():return datetime.now(timezone.utc).isoformat()
def members(c):return {str(n['nm_id']):dict(subject=n['subject']['id'],bids=dict(n['bids_kopecks'])) for n in c['nm_settings']}
def economics(source,nm):
 p=next((p for p in source.get('products',[]) if int(p['nm_id'])==nm),None)
 if not p:raise ValueError('Нет собственного товарного расчёта')
 st=next((s for s in source.get('stock',[]) if s.get('article','').casefold()==p['sa_name'].casefold()),None)
 pr=next((v for v in source.get('prices',[]) if v['nmID']==nm),None)
 log=source.get('policy',{}).get('logistics_by_nm',{}).get(str(nm))
 if not st or st.get('stock') is None or st.get('reserve') is None or st['stock']-st['reserve']<=0:raise ValueError('Свободный остаток МСК не подтверждён')
 if not pr or pr.get('currencyIsoCode4217')!='CNY' or not log or st.get('price') is None:raise ValueError('Цена/COGS/собственная логистика не подтверждены')
 f=p.get('finished_orders');paid=p.get('is_payed');fee=p.get('total_commission_without_spp_in_sales')
 if not f or paid is None or fee is None or not p.get('sales_sum_without_spp') or not p.get('price_after_discount') or p.get('price_after_spp') is None:raise ValueError('Собственная завершённая выборка/комиссия неполна')
 price=pr['sizes'][0]['discountedPrice']
 expected=(paid/f)*(price*(1-fee/100-.05*p['price_after_spp']/p['price_after_discount'])-st['price']/1200)-log['delivery_cny']-10/12-.05*price
 if expected<=0:raise ValueError('При ДРР5% предварительная экономика отрицательная')
 return dict(article=p['sa_name'],subject_id=p['subject_id'],available=st['stock']-st['reserve'],paid=paid,finished=f,expected_cny_at5=round(expected,2),seller_price_cny=price,cogs_kopecks=st['price'],forecast=True,assumptions='FX12RUB/CNY, налог5%, обработка10RUB; WBPromotion не дублирован')
def prepare(w,job,kind,nm_ids):
 from china_group_permissions import allowed
 if not allowed(w,job):raise ValueError('Предложение доступно участникам группы')
 if kind not in ['add','raise'] or not 1<=len(nm_ids)<=12 or len(set(nm_ids))!=len(nm_ids):raise ValueError('Нужен точный список до12 товаров')
 from china_growth_saved import saved
 scan=saved(w,'both',3);rows=scan.get('rows',[])
 day=str(w.now.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date())
 source=w.get('china_agent:new_ad_source:v1:'+day) or {}
 if not source.get('observed_at') or w.now-datetime.fromisoformat(source['observed_at'].replace('Z','+00:00'))>timedelta(hours=24):raise ValueError('Свежая собственная экономика отсутствует; нужен конкретный сбор, не нули')
 current=w.get('china_agent:advertising_midday_source:'+day+':v2') or {}
 cs={c['id']:c for b in current.get('batches',{}).values() for c in b.get('campaigns',{}).get('adverts',[])}
 for cid,key in (w.get('china_agent:verified_campaign_state:v1') or {}).items():
  r=w.get(key) or {}
  if r.get('status')=='verified' and str(r.get('after',{}).get('id'))==cid:cs[int(cid)]=r['after']
 recent=set()
 for key in (w.get('china_agent:verified_campaign_state:v1') or {}).values():
  receipt=w.get(key) or {};at=receipt.get('verified_at')
  try:changed=datetime.fromisoformat(at.replace('Z','+00:00'))
  except (AttributeError,TypeError,ValueError):continue
  if w.now-changed<timedelta(days=3):
   for item in receipt.get('items',[]):
    if item.get('nm_id'):recent.add(item['nm_id'])
 from china_growth_candidates import excluded_history
 protected=set(source.get('protected',[]))|excluded_history(w,cs)
 cfg=current.get('config') or {};step=cfg.get('cpcStep')
 if cfg.get('currency')!='CNY' or type(step)is not int or step<=0:raise ValueError('Шаг/валюта ставок не подтверждены')
 items=[];blocked=[]
 for nm in nm_ids:
  try:
   econ=economics(source,nm)
   if kind=='raise' and nm in recent:raise ValueError('Недавнее подтверждённое изменение: нужен результат текущего теста, повторное повышение не предлагаю')
   if nm in protected:raise ValueError('Товар требует отдельной проверки истории исключения')
   candidates=[r for r in rows if r['nm_id']==nm and r['placement']=='recommendations']
   if not candidates:raise ValueError('Нет подтверждённой рекомендации с рекламной статистикой')
   r=max(candidates,key=lambda r:(r.get('previous_full_days') or {}).get('orders',0))
   past=r.get('previous_full_days') or {};today=r.get('today') or {}
   if kind=='raise':
    if past.get('orders',0)<3 or r.get('previous_drr') is None or r['previous_drr']>4 or not today.get('orders') or r.get('today_drr') is None or r['today_drr']>5:raise ValueError('Нет достаточного запаса по рекламе за3дня и сегодня')
    cid=r['campaign_id'];old=r['current_minor'];target=math.ceil(old*1.10/step)*step
    if type(old)is not int or target<=old or target>cfg.get('cpcMaxBid',0):raise ValueError('Ставка не определена')
    items.append(dict(kind='ad_raise_bid',campaign_id=cid,nm_id=nm,article=econ['article'],placement='recommendations',old_minor=old,target_minor=target,economics=econ,evidence=r,test_additional_cny=20))
   else:
    if any(c.get('status')==9 and c['settings']['placements'].get('search') and nm in [n['nm_id'] for n in c['nm_settings']] for c in cs.values()):raise ValueError('Уже в действующем поиске; повтор не нужен')
    suitable=[c for c in cs.values() if c.get('status')==9 and c.get('currency')=='CNY' and c['settings'].get('placements')==dict(search=True,recommendations=False) and c.get('bid_type')=='manual' and c['settings']['payment_type']=='cpc' and {n['subject']['id'] for n in c['nm_settings']}=={econ['subject_id']} and len(c['nm_settings'])<50]
    suitable.sort(key=lambda c:c['id'])
    cid=suitable[0]['id'] if suitable else None
    reference=min([n['bids_kopecks']['search'] for n in suitable[0]['nm_settings'] if n['bids_kopecks'].get('search',0)>0],default=0) if suitable else r['current_minor']
    if type(reference)is not int or reference<=0:raise ValueError('Нет обоснованной тестовой ставки')
    items.append(dict(kind='ad_add_sku' if cid else 'ad_create_search_draft',campaign_id=cid,nm_id=nm,subject_id=econ['subject_id'],article=econ['article'],placement='search',target_minor=reference,economics=econ,evidence=r,test_additional_cny=20))
  except (ValueError,KeyError,TypeError) as ex:blocked.append(dict(nm_id=nm,reason=str(ex)))
 if not items:return dict(status='blocked',items=[],blocked=blocked,note='Готового плана нет; это не подтверждение действий')
 pid='dialog-ads-'+str(job['id'])+'-'+kind
 p=dict(plan_id=pid,execution_kind='advertising_dialog_v1',job_id=job['id'],sender_id=job['sender_id'],chat_id=CHAT,bot_id=BOT,items=items,plan_sha256=digest(items),created_at=iso(),expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),report_message_ids=[],blocked=blocked,source_observed_at=scan.get('observed_at'),price_changes=False,budget_writes=False)
 lines=['Предлагаю точный рекламный тест:']
 for i in items:
  action=('РК '+str(i['campaign_id'])+': '+str(i['old_minor']/100)+' → '+str(i['target_minor']/100)+' ¥ в рекомендациях') if kind=='raise' else ('добавить в поиск РК '+str(i['campaign_id']) if i['campaign_id'] else 'создать поисковый черновик без пополнения и запуска')+'; ставка '+str(i['target_minor']/100)+' ¥'
  r=i['evidence'];econ=i['economics']
  lines.append(i['article']+' (WB '+str(i['nm_id'])+') — '+action+'. ДРР3дня '+str(r.get('previous_drr'))+'%, сегодня '+str(r.get('today_drr'))+'%; свой выкуп '+str(econ['paid'])+'/'+str(econ['finished'])+'.')
 if blocked:lines.append('Не вошли: '+'; '.join(str(x['nm_id'])+' — '+x['reason'] for x in blocked))
 lines+=['Срез: '+str(scan.get('observed_at'))+'. Экономика предварительная, FX12/налог5%/обработка10₽ — допущения.','Дополнительный тестовый расход: до '+str(sum(x['test_additional_cny'] for x in items))+' ¥ — плановый предел, не автоматический лимит WB. Пополнений и пауз нет.','Ответьте на это сообщение «Делай» или «Давай добавляй». Перед записью проверю текущий состав, ставки и минимумы; затем сообщу результат.','План рекламы: '+pid]
 p['text']='\n'.join(lines)
 if len(p['text'])>3400:raise ValueError('План слишком длинный; разделить на меньшие точные наборы')
 if not w.save(P+pid,p,insert=True):
  prior=w.get(P+pid)
  if not prior or prior['plan_sha256']!=p['plan_sha256']:raise ValueError('План изменился; нужен новый identity')
  p=prior
 return dict(status='ready',plan_id=pid,text=p['text'],items=items,blocked=blocked,wb_writes=0)
def bind(w,text,message_id):
 m=re.search(r'План рекламы: (dialog-ads-[0-9]+-(?:add|raise))\s*$',text)
 if not m:return
 p=w.get(P+m[1])
 if not p or p.get('text')!=text or digest(p['items'])!=p['plan_sha256']:raise ValueError('Текст плана не совпал')
 if message_id not in p['report_message_ids']:p['report_message_ids'].append(message_id);w.save(P+p['plan_id'],p)
 w.save(B+str(message_id),dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],chat_id=CHAT),insert=True)
def handle(w,job,history=()):
 if not is_all(job.get('request_text','')):return None
 m=marker(job);b=w.get(B+str(m.get('reply_message_id')))
 if not b:return None
 from china_group_permissions import allowed
 if not allowed(w,job) or m.get('bot_id')!=BOT or m.get('forwarded'):return ('Подтверждение доступно действующим участникам ответом на исходный план.',[])
 p=w.get(P+b['plan_id'])
 if not p or p['plan_sha256']!=digest(p['items']) or b['plan_sha256']!=p['plan_sha256'] or m['reply_message_id'] not in p['report_message_ids']:raise ValueError('Привязанный план изменился')
 if w.now>datetime.fromisoformat(p['expires_at']):return ('План устарел. Подготовлю свежий; прежнюю команду повторно не исполняю.',[])
 key=A+p['plan_id']
 a=dict(status='approved',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],job_id=job['id'],update_id=job['update_id'],sender_id=job['sender_id'],chat_id=CHAT,bot_id=BOT,input_message_id=m['message_id'],reply_message_id=m['reply_message_id'],created_at=job['created_at'],price_changes=False)
 if not w.save(key,a,insert=True):return ('Этот план уже принят; повторных изменений не будет.',[dict(name='advertising_dialog_approval',plan_id=p['plan_id'],duplicate=True)])
 return ('Принято: '+str(len(p['items']))+' точных действий плана. Проверю параметры WB, затем пришлю подтверждённый результат или конкретный блокер. Пополнений нет.',[dict(name='advertising_dialog_approval',plan_id=p['plan_id'])])

def execute(io,a,p):
 from china_cloud_cost_control import WB
 io.validate_owner(a)
 if p.get('execution_kind')!='advertising_dialog_v1' or p['plan_sha256']!=digest(p['items']) or a['plan_sha256']!=p['plan_sha256'] or a['plan_id']!=p['plan_id']:raise ValueError('План/подтверждение не совпали')
 b=io.get(B+str(a['reply_message_id']))
 if not b or b['plan_id']!=p['plan_id'] or b['plan_sha256']!=p['plan_sha256']:raise ValueError('Нет привязки к исходному сообщению')
 key=E+p['plan_id'];e=io.get(key)
 if e:return e # accepted/uncertain NEVER repeated; readback must be reconciled separately
 e=dict(status='running',items=[],steps={},wb_writes=0,created_at=iso(),plan_sha256=p['plan_sha256'])
 if not io.create(key,e):return io.get(key)
 w=WB()
 def save():io.put(key,json.loads(json.dumps(e)))
 def write(step,path,method,body):
  if step in e['steps']:raise ValueError('Повтор WB-записи запрещён')
  if datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('План истёк перед записью')
  e['steps'][step]=dict(status='submitting',path=path,method=method,body=body);save()
  try:
   if path=='/adv/v2/seacat/save-ad':
    import requests
    r=requests.post('https://advert-api.wildberries.ru'+path,headers={'Authorization':w.token},json=body,timeout=50)
    if not r.ok:raise RuntimeError('WB create HTTP '+str(r.status_code))
    result=r.json()
   else:result=w.req(path,method,body,write=True)
  except Exception:e['steps'][step]['status']='uncertain';save();raise
  e['steps'][step].update(status='accepted',response=result);e['wb_writes']+=1;save();return result
 try:
  # Identity, price and available stock are refreshed narrowly before changes.
  prices=io.prices([str(i['nm_id']) for i in p['items']])
  import requests,os
  headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN']}
  root='https://api.moysklad.ru/api/remap/1.2'
  r=requests.get(root+'/entity/store',headers=headers,params={'limit':1000},timeout=45)
  if not r.ok:raise RuntimeError('МойСклад: склад недоступен')
  stores=[s for s in r.json().get('rows',[]) if s.get('name')=='МСК' and not s.get('archived')]
  if len(stores)!=1:raise ValueError('Склад МСК неоднозначен')
  r=requests.get(root+'/report/stock/all',headers=headers,params={'filter':'store='+stores[0]['meta']['href'],'stockMode':'all','limit':1000},timeout=55)
  if not r.ok:raise RuntimeError('МойСклад: остаток недоступен')
  stock=r.json()
  if stock.get('meta',{}).get('size',len(stock.get('rows',[])))>len(stock.get('rows',[])):raise ValueError('Остатки неполны')
  for i in p['items']:
   pr=prices.get(str(i['nm_id']),{});st=[x for x in stock.get('rows',[]) if x.get('article','').casefold()==i['article'].casefold()]
   if pr.get('sizes',[{}])[0].get('discountedPrice')!=i['economics']['seller_price_cny'] or len(st)!=1 or st[0].get('price')!=i['economics']['cogs_kopecks']:raise ValueError('Цена/себестоимость изменились; пересчитать экономику')
   if pr.get('vendorCode')!=i['article'] or pr.get('currencyIsoCode4217')!='CNY' or len(st)!=1 or st[0].get('stock') is None or st[0].get('reserve') is None or st[0]['stock']-st[0]['reserve']<=0:raise ValueError('Товар/цена/свободный остаток изменились: '+i['article'])
  for index,i in enumerate(p['items']):
   state=dict(index=index,item=copy.deepcopy(i),status='preflight');e['items'].append(state);save()
   try:
    cid=i.get('campaign_id')
    if cid:
     before=w.campaigns([cid])[str(cid)];state['before']=before;save()
     if before['status']!=9 or before['currency']!='CNY' or before['bid_type']!='manual' or before['settings']['payment_type']!='cpc':raise ValueError('РК больше не подходит')
     wanted=dict(search=i['placement']=='search',recommendations=i['placement']=='recommendations')
     if before['settings']['placements']!=wanted:raise ValueError('Зона показов изменилась')
     ns={n['nm_id']:n for n in before['nm_settings']}
     if i['kind']=='ad_raise_bid':
      if i['nm_id'] not in ns:raise ValueError('Артикул исключён')
      old=ns[i['nm_id']]['bids_kopecks'][i['placement']]
      if old==i['target_minor']:state.update(status='verified',already_done=True,after=before);save();continue
      if old!=i['old_minor']:raise ValueError('Ставка изменилась; нужен новый план')
      day=datetime.now().astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()
      stats=w.req('/adv/v3/fullstats?ids='+str(cid)+'&beginDate='+day+'&endDate='+day)
      nsr=[n for c in stats for d in c.get('days',[]) for app in d.get('apps',[]) for n in app.get('nms',[]) if n['nmId']==i['nm_id']]
      spend=sum(n['sum'] for n in nsr);amount=sum(n['sum_price'] for n in nsr)
      if not amount or spend/amount>.05:raise ValueError('Свежая ДРР не допускает повышение')
     elif i['kind']=='ad_add_sku':
      if i['nm_id'] in ns:state.update(status='verified',already_done=True,after=before);save();continue
      if {n['subject']['id'] for n in ns.values()}!={i['subject_id']} or len(ns)>=50:raise ValueError('Категория/число SKU изменились')
     else:raise ValueError('Недопустимый вид действия')
    elif i['kind']=='ad_create_search_draft':
     name='Китай поиск '+p['plan_id']+' '+str(i['nm_id'])
     result=write(str(index)+':create','/adv/v2/seacat/save-ad','POST',dict(name=name,nms=[i['nm_id']],bid_type='manual',payment_type='cpc',placement_types=['search']))
     cid=result if type(result)is int else result.get('advertId') if isinstance(result,dict) else None
     if type(cid)is not int:raise ValueError('Нет точного ID созданного черновика; не повторять')
     state['campaign_id']=cid;save();before=w.campaigns([cid])[str(cid)]
     if before['status']!=4 or before['currency']!='CNY' or before['settings']['placements']!=dict(search=True,recommendations=False) or set(members(before))!={str(i['nm_id'])}:raise ValueError('Черновик не подтверждён')
     state['before']=before;e['steps'][str(index)+':create']['status']='verified';save()
    else:raise ValueError('РК не определена')
    state['campaign_id']=cid
    if i['kind']=='ad_add_sku':
     write(str(index)+':add','/adv/v0/auction/nms','PATCH',dict(nms=[dict(advert_id=cid,nms=dict(add=[i['nm_id']],delete=[]))]))
     after=w.campaigns([cid])[str(cid)]
     if set(members(after))!=set(members(before))|{str(i['nm_id'])} or any(members(after)[k]!=v for k,v in members(before).items()) or after['settings']!=before['settings']:raise ValueError('Добавление/сохранение прежних ставок не подтверждено')
     e['steps'][str(index)+':add']['status']='verified';state['after_membership']=after;save()
    minimum=w.minimums(cid,[i['nm_id']],i['placement'])[i['nm_id']]
    if minimum>i['target_minor']:raise ValueError('Минимум WB выше подтверждённой ставки')
    write(str(index)+':bid','/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm_id'],bid_kopecks=i['target_minor'],placement=i['placement'])])]))
    after=w.campaigns([cid])[str(cid)];state['after']=after
    if after['settings']!=before['settings'] or after['status']!=before['status']:raise ValueError('Настройки/статус после записи изменились')
    expected=members(state.get('after_membership',before));expected[str(i['nm_id'])]['bids'][i['placement']]=i['target_minor']
    if members(after)!=expected:raise ValueError('Точное изменение ставки не подтверждено')
    e['steps'][str(index)+':bid']['status']='verified';state['status']='verified';save()
   except Exception as ex:
    state.update(status='uncertain' if any(v['status']in ['submitting','accepted','uncertain'] for k,v in e['steps'].items() if k.startswith(str(index)+':')) else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__);save()
    if state['status']=='uncertain':break
  e['status']='verified' if len(e['items'])==len(p['items']) and all(s['status']=='verified' for s in e['items']) else 'attention'
 except Exception as ex:e.update(status='blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__)
 finally:
  e['completed_at']=iso();save()
  registry=io.get('china_agent:verified_campaign_state:v1') or {}
  for state in e['items']:
   if state.get('status')=='verified':
    cid=str(state['after']['id']);k=E+p['plan_id']+':'+str(state['index'])
    io.put(k,dict(status='verified',before=state.get('before'),after=state['after'],items=[state['item']],verified_at=e['completed_at'],parent=key));registry[cid]=k
  io.put('china_agent:verified_campaign_state:v1',registry)
 return e
def process(io):
 rows=io.db('telegram_api_cache?cache_key=like.'+A+'*&select=payload&limit=100')
 if len(rows)>=100:raise RuntimeError('Список подтверждений неполон')
 for row in rows:
  a=row['payload'];p=io.get(P+a['plan_id'])
  if a.get('status')!='approved' or not p:continue
  e=execute(io,a,p);key='china_agent:advertising_dialog_result:v1:'+p['plan_id']
  if io.get(key):continue
  lines=['Результат рекламного плана:']
  for s in e.get('items',[]):
   i=s['item'];label=i['article']+' · РК '+str(s.get('campaign_id') or i.get('campaign_id'))
   lines.append(label+': '+('уже выполнено, повтор не нужен' if s.get('already_done') else 'создан поисковый черновик; без пополнения/запуска' if s['status']=='verified' and i['kind']=='ad_create_search_draft' else 'выполнено, проверено WB' if s['status']=='verified' else 'не завершено: '+s.get('reason',s['status'])))
  if e.get('reason'):lines.append('Блокер: '+e['reason'])
  if len(e.get('items',[]))<len(p['items']):lines.append('Оставшиеся действия не выполнялись.')
  text='\n'.join(lines)
  if not io.create(key,dict(status='sending',text=text)):continue
  try:
   r=io.tg('sendMessage',dict(chat_id=CHAT,text=text,reply_parameters=dict(message_id=a['input_message_id'],allow_sending_without_reply=True)))
   io.put(key,dict(status='sent',message_id=r['message_id'],chat_id=CHAT,text=text))
  except Exception:io.put(key,dict(status='uncertain',text=text))
