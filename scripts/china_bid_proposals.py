"""Reply-bound CPC bid proposals. Saved evidence first; bounded reads only for a concrete plan."""
import copy,math,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
POLICY='china_agent:bid_proposals:policy:v1'
def timestamp(value):
 try:
  at=datetime.fromisoformat(value.replace('Z','+00:00'));return at if at.tzinfo else at.replace(tzinfo=MSK)
 except (AttributeError,ValueError,TypeError):return None
def request_options(job,default_percent=10,default_count=5):
 text=job.get('request_text','')
 percent=re.search(r'(?:на|по)\s*(\d+(?:[.,]\d+)?)\s*%',text,re.I)
 count=re.search(r'(?:выбер\w*|подбер\w*|выбра\w*|выбрать|поднять|повысить)\s+(\d+)\s+(?:товар|артикул|сум)',text,re.I) or re.search(r'(\d+)\s+(?:товар|артикул|сум)',text,re.I)
 return (float(percent[1].replace(',','.')) if percent else default_percent,min(int(count[1]),12) if count else default_count)
def sources(w):
 day=str(w.now.astimezone(MSK).date());history=w.get('china_agent:advertising_source:'+day+':v2') or {}
 available=[history,w.get('china_agent:advertising_midday_source:'+day+':v2') or {},w.get('china_agent:advertising_intraday:'+day+':v1') or {}]
 available=[s for s in available if s.get('batches') or s.get('campaigns')]
 available.sort(key=lambda s:timestamp(s.get('observed_at') or s.get('completed_at')) or datetime.min.replace(tzinfo=timezone.utc))
 latest=available[-1] if available else {}
 campaigns={};stats={};config={}
 for source in available:
  config=source.get('config') or config
  for batch in source.get('batches',{}).values():
   for c in batch.get('campaigns',{}).get('adverts',[]):campaigns[c['id']]=c
   for r in batch.get('stats',[]):stats[r['advertId']]=r
  for c in source.get('campaigns',[]) if isinstance(source.get('campaigns'),list) else []:campaigns[c['id']]=c
  for batch in source.get('ad_batches',[]):
   for r in batch.get('data',[]):stats[r['advertId']]=r
 records=list(history.get('executions',[]))
 if callable(getattr(w,'db',None)):
  from china_experience import read_rows
  prices=read_rows(w,'china_agent:price_execution:v1:',limit=100)
  cutoff=w.now-timedelta(days=4)
  if len(prices)>=100 and (timestamp(prices[-1].get('updated_at')) or w.now)>=cutoff:raise ValueError('Недавняя история цен обрезана; сначала уточнить последние изменения')
  prices=[r for r in prices if (timestamp(r.get('updated_at')) or w.now)>=cutoff]
  records+=prices
 for cid,key in (w.get('china_agent:verified_campaign_state:v1') or {}).items():
  r=w.get(key) or {};after=r.get('after') or {}
  if r.get('status')=='verified' and str(after.get('id'))==str(cid):
   campaigns[int(cid)]=after;records.append(dict(cache_key=key,payload=r))
   if r.get('parent'):
    parent=w.get(r['parent']) or {}
    if parent.get('status') in ['verified','attention']:records.append(dict(cache_key=r['parent'],payload=parent))
 from china_advertising_v2 import history as normalize
 changes=normalize(records)
 for record in history.get('experience',[]):
  event=record.get('payload',record);act=event.get('action',{})
  if act.get('kind')=='price_change' and event.get('started_at'):
   for nm in act.get('nm_ids',[]):changes.append(dict(cid=None,nm=int(nm),kind='price',at=event['started_at']))
 for c in campaigns.values():
  at=c.get('timestamps',{}).get('started') or c.get('timestamps',{}).get('created')
  if at:
   for n in c.get('nm_settings',[]):changes.append(dict(cid=c['id'],nm=n['nm_id'],kind='added',at=at))
 return dict(day=day,history=history,latest=latest,campaigns=campaigns,stats=stats,changes=changes,config=config,observed_at=latest.get('observed_at') or latest.get('completed_at'))
def daily(raw,nm):
 if raw and raw.get('currency') not in (None,'CNY'):raise ValueError('Статистика рекламы не в CNY')
 out={}
 for d in (raw or {}).get('days',[]):
  v=dict(spend=0,amount=0,orders=0,clicks=0)
  for app in d.get('apps',[]):
   for n in app.get('nms',[]):
    if n['nmId']==nm:
     for k,f in [('spend','sum'),('amount','sum_price'),('orders','orders'),('clicks','clicks')]:v[k]+=n.get(f,0)
  out[d['date'][:10]]=v
 return out
def candidates(w,view,economy,nm_ids=()):
 from china_advertising_plans import economics
 last=w.now.astimezone(MSK).date()-timedelta(days=1)
 dates=[str(last-timedelta(days=i)) for i in range(2,-1,-1)]
 rows=[];blocked=[];wanted=set(nm_ids);labels={int(p['nm_id']):p.get('sa_name') for p in economy.get('products',[])}
 for c in view['campaigns'].values():
  if c.get('status')!=9 or c.get('currency')!='CNY' or c.get('bid_type')!='manual' or c.get('settings',{}).get('payment_type')!='cpc':continue
  zone='search' if c['settings']['placements'].get('search') else 'recommendations'
  for n in c.get('nm_settings',[]):
   nm=n['nm_id']
   if wanted and nm not in wanted:continue
   try:
    econ=economics(economy,nm)
    from china_experience import assess_candidate
    context=economy.get('experience') or {}
    experiences=list(context.get('experiences',[])) if isinstance(context,dict) else list(context)
    experiences+= [x.get('payload',x) for x in view.get('history',{}).get('experience',[])]
    assessment=assess_candidate(experiences,nm,dict(seller_price=econ['seller_price_cny'],stock_available=econ['available']))
    if assessment['needs_review']:raise ValueError('Негативный прошлый опыт требует проверки изменившихся условий')
    changes=[x for x in view['changes'] if x.get('nm')==nm and x.get('cid') in (None,c['id']) and timestamp(x.get('at'))]
    changes.sort(key=lambda x:timestamp(x['at']))
    changed=timestamp(changes[-1]['at']).astimezone(MSK).date() if changes else None
    full=[d for d in dates if changed is None or d>str(changed)]
    if not full:raise ValueError('После последнего изменения ещё нет полного дня; сначала завершить следующий день МСК')
    values=daily(view['stats'].get(c['id']),nm)
    if any(d not in values for d in full):raise ValueError('Рекламная статистика полных дней неполна')
    past={k:sum(values[d][k] for d in full) for k in ['spend','amount','orders','clicks']}
    if past['amount']<=0 or past['orders']<3 or past['clicks']<20 or past['spend']<=0:raise ValueError('Недостаточная собственная рекламная выборка')
    drr=past['spend']/past['amount']*100
    if drr>=4:raise ValueError('Недостаточный запас до цели ДРР5%')
    if econ['finished']<5:raise ValueError('Малая завершённая выборка выкупа')
    today=values.get(view['day']);tdrr=today['spend']/today['amount']*100 if today and today['amount'] else None
    if tdrr is not None and tdrr>5:raise ValueError('Сегодня ДРР выше5%')
    if today and not today['amount'] and today['spend']>=econ['seller_price_cny']*.05:raise ValueError('Сегодня существенный расход без рекламных заказов')
    if changes and changes[-1]['kind']=='bid' and changes[-1].get('old',0)>changes[-1].get('target',0) and len(full)<3:raise ValueError('После снижения ставки сначала три полных дня проверки, не повторять прежнее повышение')
    old=n.get('bids_kopecks',{}).get(zone)
    if type(old)is not int or old<=0:raise ValueError('Текущая ставка неизвестна')
    rows.append(dict(campaign_id=c['id'],nm_id=nm,article=econ['article'],placement=zone,current_minor=old,economics=econ,previous_full_days=past,previous_drr=round(drr,2),today=today,today_drr=round(tdrr,2) if tdrr is not None else None,decision_days=full,last_change=changes[-1] if changes else None))
   except (ValueError,KeyError,TypeError) as ex:
    blocked.append(dict(nm_id=nm,article=labels.get(nm,'WB '+str(nm)),reason=str(ex)))
 rows.sort(key=lambda r:(-r['previous_full_days']['orders'],r['previous_drr']))
 # A product may be in search and recommendations. Propose one placement per product.
 unique=[];seen=set()
 for r in rows:
  if r['nm_id'] not in seen:unique.append(r);seen.add(r['nm_id'])
 return unique,blocked
def prepare(w,job,nm_ids=(),raise_percent=None,count=None,refresh=None):
 from china_group_permissions import allowed
 from china_advertising_plans import P,digest,iso
 if not allowed(w,job):raise ValueError('Команда доступна действующим участникам рабочей группы')
 policy=w.get(POLICY) or {}
 if policy.get('enabled') is not True:return dict(status='blocked',items=[],blocked=[],note='Подготовка предложений ставок выключена владельцем')
 percent,n=request_options(job,policy.get('default_raise_percent',10),policy.get('default_count',5))
 percent=percent if raise_percent is None else raise_percent;n=n if count is None else count
 if not 0<percent<=30 or not 1<=n<=12 or len(nm_ids)>12:raise ValueError('Нужен тест до12товаров и повышение не более30%')
 from china_advertising_plans import P
 prior=w.get(P+'dialog-ads-'+str(job['id'])+'-raise')
 if prior and (prior.get('invalidated_at') or prior.get('status') in ['revoked','invalidated'] or timestamp(prior.get('expires_at')) and datetime.now(timezone.utc)>timestamp(prior['expires_at'])):
  return dict(status='blocked',items=[],blocked=[],note='Этот план отозван или устарел; нужен новый запрос')
 if prior and prior.get('items') and not prior.get('invalidated_at'):
  return dict(status='ready',plan_id=prior['plan_id'],text=prior['text'],items=prior['items'],blocked=prior.get('blocked',[]),wb_writes=0)
 view=sources(w);economy=w.get('china_agent:new_ad_source:v1:'+view['day']) or {}
 at=timestamp(economy.get('observed_at'))
 if not at or not timedelta(0)<=w.now-at<=timedelta(hours=24):
  # Preparation is read-only; replenish missing economics only when necessary.
  if refresh:
   economy=refresh('economics',None,None)
  else:
   from china_new_ad_reports import source
   from china_price_apply import IO
   economy=source(IO())
  at=timestamp(economy.get('observed_at'))
  if not at or not timedelta(0)<=w.now-at<=timedelta(hours=24):raise ValueError('Свежая экономика отсутствует; неизвестное не0')
 rows,blocked=candidates(w,view,economy,nm_ids)
 if not rows:return dict(status='blocked',items=[],blocked=blocked[:12],note='Подходящих товаров пока нет: '+('; '.join(dict.fromkeys(x['reason'] for x in blocked))[:900] or 'нет сохранённого состава/статистики'))
 selected=rows[:n]
 # Narrow current reads only after cached economic/history screening, at most12 campaigns.
 ids=sorted({r['campaign_id'] for r in selected})
 cache_key='china_agent:bid_proposal_source:v1:'+str(job['id'])
 cached=w.get(cache_key)
 cache_at=timestamp((cached or {}).get('observed_at'))
 if cached and cache_at and timedelta(0)<=w.now-cache_at<=timedelta(minutes=10):
  fresh=copy.deepcopy(cached);fresh['campaigns']={int(k):v for k,v in fresh['campaigns'].items()};fresh['stats']={int(k):v for k,v in fresh['stats'].items()}
 elif refresh:
  fresh=refresh('campaigns',ids,view)
 else:
  from china_price_apply import IO
  from china_cloud_cost_control import WB
  io=IO();wb=WB()
  cs=wb.campaigns(ids)
  stat=wb.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate='+str(w.now.astimezone(MSK).date()-timedelta(days=3))+'&endDate='+view['day'])
  cfg=io_config(io)
  fresh=dict(campaigns={int(k):v for k,v in cs.items()},stats={r['advertId']:r for r in stat},config=cfg,minimums={},observed_at=iso())
  for cid in ids:
   for zone in ['search','recommendations']:
    ns=[r['nm_id'] for r in selected if r['campaign_id']==cid and r['placement']==zone]
    if ns:fresh['minimums'].update({str(cid)+':'+str(nm):v for nm,v in wb.minimums(cid,ns,zone).items()})
 w.save(cache_key,fresh)
 view=copy.deepcopy(view);view['campaigns'].update(fresh['campaigns']);view['stats'].update(fresh['stats'])
 cfg=fresh['config'];step=cfg.get('cpcStep')
 if cfg.get('currency')!='CNY' or type(step)is not int or step<=0:raise ValueError('Минимальный шаг/валюта WB не подтверждены')
 # Fresh results can invalidate a cached candidate; never silently replace its campaign.
 fresh_rows,fresh_blocked=candidates(w,view,economy,[r['nm_id'] for r in selected]);blocked+=fresh_blocked
 selected_keys={(r['campaign_id'],r['nm_id']) for r in selected};items=[]
 for r in fresh_rows:
  if (r['campaign_id'],r['nm_id']) not in selected_keys:continue
  old=r['current_minor'];target=int(math.floor(old*(1+percent/100)/step+.5))*step
  minimum=fresh['minimums'].get(str(r['campaign_id'])+':'+str(r['nm_id']))
  if type(minimum)is not int or not old<target<=cfg.get('cpcMaxBid',0) or target<minimum:
   blocked.append(dict(nm_id=r['nm_id'],reason='Повышение не соответствует свежему минимуму/шагу WB'));continue
  items.append(dict(kind='ad_raise_bid',campaign_id=r['campaign_id'],nm_id=r['nm_id'],article=r['article'],placement=r['placement'],old_minor=old,target_minor=target,minimum_minor=minimum,economics=r['economics'],evidence=r,test_additional_cny=20))
 if not items:return dict(status='blocked',items=[],blocked=blocked[:12],note='После свежей проверки готовых повышений нет')
 pid='dialog-ads-'+str(job['id'])+'-raise';created=iso()
 plan=dict(plan_id=pid,execution_kind='advertising_dialog_v1',job_id=job['id'],sender_id=job['sender_id'],chat_id=job['chat_id'],bot_id=8780468043,items=items,plan_sha256=digest(items),created_at=created,expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),report_message_ids=[],blocked=blocked[:12],source_observed_at=fresh['observed_at'],price_changes=False,budget_writes=False,raise_percent=percent)
 lines=['Предлагаю повысить ставки на '+format(percent,'g')+'% (округление по шагу WB):']
 for i in items:
  r=i['evidence'];past=r['previous_full_days'];today=r['today'];t='нет заказов' if r['today_drr'] is None and today else 'нет свежих данных' if today is None else str(r['today_drr'])+'%'
  lines.append(i['article']+' · РК'+str(i['campaign_id'])+' '+('поиск' if i['placement']=='search' else 'рекомендации')+': '+format(i['old_minor']/100,'.2f')+' → '+format(i['target_minor']/100,'.2f')+' ¥; полных дней '+str(len(r['decision_days']))+': '+str(past['orders'])+' заказов, ДРР '+str(r['previous_drr'])+'%; сегодня '+t+'.')
 if len(items)<n:lines.append('Подошло '+str(len(items))+' из запрошенных '+str(n)+': остальные не прошли историю, экономику или свежие результаты.')
 lines+=['Срез '+fresh['observed_at']+'. Экономика предварительная: собственный выкуп/COGS/историческая логистика; FX12, налог5%, обработка10₽ — допущения; общие удержания могут быть неполны. Нет гарантии ДРР5% или роста заказов.','Ответьте «делай» или «поднимай» на это сообщение. Выполню только указанные ставки, затем проверю WB. Пополнений и пауз нет.','План рекламы: '+pid]
 plan['text']='\n'.join(lines)
 if len(plan['text'])>4000:raise ValueError('План слишком длинный; запросите меньший набор')
 if not w.save(P+pid,plan,insert=True):
  old=w.get(P+pid)
  if not old or old.get('plan_sha256')!=plan['plan_sha256']:raise ValueError('План для этого сообщения уже подготовлен; используйте новый запрос')
  plan=old
 return dict(status='ready',plan_id=pid,text=plan['text'],items=plan['items'],blocked=blocked[:12],wb_writes=0)
def io_config(io):
 import requests
 r=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':io.token},timeout=40)
 if not r.ok:raise RuntimeError('Конфигурация ставок WB HTTP '+str(r.status_code))
 return r.json()

