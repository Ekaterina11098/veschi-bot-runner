"""Bounded read orchestration for article diagnostics; snapshots only, never action plans."""
import copy,hashlib,json,re
from datetime import datetime,timedelta,timezone
from china_article_diagnostic import MSK,FIELDS,fresh,at,evaluate,render,scope,requested,number
PREFIX='china_agent:article_diagnostic:v1:'
def safe_error(ex):
 code=re.search(r'HTTP\s*(\d{3})',str(ex))
 return 'HTTP '+code[1] if code else type(ex).__name__
def price_changes(w,ids):
 since=(w.now-timedelta(days=4)).isoformat()
 rows=w.db('GET','telegram_api_cache',params={'cache_key':'like.china_agent:price_execution:v1:*','updated_at':'gte.'+since,'select':'cache_key,payload','order':'updated_at.desc','limit':100}) or []
 if len(rows)>=100:raise ValueError('История цен обрезана')
 out=[]
 for row in rows:
  p=row['payload'];when=p.get('completed_at') or p.get('verified_at')
  if p.get('status')!='done' or not at(when):continue
  for x in p.get('items',[]):
   s=x.get('selection') or {};rb=x.get('readback') or {}
   try:nm=int(s['nm_id']);target=float(s['target_cny'])
   except (KeyError,TypeError,ValueError):continue
   if nm not in ids or x.get('status')!='applied' or rb.get('nmID')!=nm or rb.get('currencyIsoCode4217')!='CNY' or rb.get('vendorCode')!=s.get('article'):continue
   sizes=rb.get('sizes') or []
   if sizes and all(number(z.get('discountedPrice')) and z['discountedPrice']==target for z in sizes):
    out.append(dict(nm=nm,cid=None,kind='price',at=when,verified=True,source_key=row['cache_key']))
 return out
def unresolved(w,ids):
 rows=w.db('GET','telegram_api_cache',params={'or':'(cache_key.like.china_agent:price_execution:v1:*,cache_key.like.china_agent:advertising_dialog_execution:v1:*,cache_key.like.china_agent:owner_*:execution,cache_key.like.china_agent:bid_resume:*,cache_key.like.china_agent:ad_rule_execution:*)','payload->>status':'in.(uncertain,submitting,submitted,accepted,preflight,running)','updated_at':'gte.'+(w.now-timedelta(days=4)).isoformat(),'select':'cache_key,payload','limit':100}) or []
 if len(rows)>=100:raise ValueError('Незавершённая история обрезана')
 found=set()
 def visit(x):
  if isinstance(x,list):
   for z in x:visit(z)
  elif isinstance(x,dict):
   for name in ['nm','nm_id','nmId','nmID']:
    try:
     if int(x.get(name)) in ids:found.add(int(x[name]))
    except (TypeError,ValueError):pass
   for k,v in x.items():
    if k not in ['before','after','nm_settings']:visit(v)
 for row in rows:visit(row.get('payload') or {})
 return found

def availability_statements(analyst,ids):
 out=[];history=analyst.history or []
 for index,h in enumerate(history+[analyst.job]):
  text=h.get('request_text','')
  if not re.search(r'(?:вернул|постав|пополнил|восстановил)\w*.*остат|остат.*(?:вернул|постав|пополнил|восстановил)',text,re.I):continue
  when=at(h.get('created_at')) if index<len(history) else analyst.w.now
  if when is None:continue
  context=scope(analyst.w,h,history[:index])
  if len(context)!=1:continue
  if context[0] not in ids:continue
  if re.search(r'вчера',text,re.I):when-=timedelta(days=1)
  out.append(dict(nm=context[0],at=when.isoformat(),source='human_statement',quote=text[:500]))
 return out

def completed_rows(raw,nm,first,last):
 out={}
 for day in (raw or {}).get('days',[]):
  date=day.get('date','')[:10]
  if not first<=date<=last:continue
  found=[r for app in day.get('apps',[]) for r in app.get('nms',[]) if r.get('nmId')==nm]
  if not found:continue
  values=dict(date=date)
  for target,source in zip(FIELDS,['views','clicks','atbs','orders','sum','sum_price']):
   parts=[r.get(source) for r in found]
   values[target]=sum(parts) if all(number(x) and x>=0 for x in parts) else None
  out[date]=values
 return list(out.values())
def visibility(w,nm,article,today):
 direct=w.get('china_agent:article_visibility:v1:'+str(nm))
 if direct:return direct
 old=w.get('china_agent:owner_funnel36_visibility:'+today+':v1') or {}
 if old.get('status','').startswith('verified'):
  found=next((r for r in old.get('items',[]) if r.get('nm')==nm and r.get('article','').casefold()==article.casefold()),None)
  if found:return dict(observed_at=old.get('observed_at'),orderable=found.get('orderable'),rating=found.get('displayed_rating'),review_count=found.get('displayed_rating_count'),source='WB buyer UI, dated direct page; not search/ad rank',search_or_ad_rank_verified=False)
 return {}
def collect(analyst,nm_ids,days=3,raise_percent=10,campaign_ids=(),reader=None):
 w=analyst.w;ids=sorted(set(nm_ids));labels={int(n):a for n,a in w.catalog()}
 if not 1<=len(ids)<=10 or any(type(n)is not int or n not in labels for n in ids):raise ValueError('Нужны1–10точных nmID Китая')
 if not 2<=days<=14 or not number(raise_percent) or not 0<raise_percent<=30:raise ValueError('Период2–14полныхдней; повышение1–30%')
 if len(campaign_ids)>10 or any(type(c)is not int or c<=0 for c in campaign_ids):raise ValueError('Нужны точные РК')
 day=w.now.astimezone(MSK).date();last=day-timedelta(days=1);first=last-timedelta(days=days-1)
 key=PREFIX+str(analyst.job['id'])+':'+hashlib.sha256(json.dumps([ids,days,raise_percent,sorted(campaign_ids),analyst.job.get('request_text','')],ensure_ascii=False).encode()).hexdigest()[:16]
 cached=w.get(key)
 if cached and fresh(cached,w.now,600):return dict(cached,cached=True)
 source=w.get('china_agent:new_ad_source:v1:'+str(day)) or {};gaps=[];history_checked=True
 try:
  from china_bid_proposals import sources
  view=sources(w)
 except Exception as ex:view={};history_checked=False;gaps.append('Журнал/сохранённый состав: '+safe_error(ex))
 if campaign_ids:view=dict(view,campaigns={cid:c for cid,c in view.get('campaigns',{}).items() if cid in campaign_ids},requested_campaign_ids=list(campaign_ids))
 changes=[dict(x,verified=True) for x in view.get('changes',[])]
 try:changes+=price_changes(w,ids)
 except Exception as ex:history_checked=False;gaps.append('Квитанции цен: '+safe_error(ex))
 # No new collection to select another change before the first full post-change day.
 availability=availability_statements(analyst,ids)
 wait={n for n in ids if any(x.get('nm')==n and x.get('verified') is True and at(x.get('at')) and at(x['at']).astimezone(MSK).date()>=last for x in changes)}
 wait|={x['nm'] for x in availability if at(x['at']).astimezone(MSK).date()>=last}
 try:pending=unresolved(w,ids)
 except Exception as ex:pending=set(ids);gaps.append('Незавершённые операции: '+safe_error(ex))
 wait|=pending
 fresh_inputs={}
 if len(wait)!=len(ids):
  try:fresh_inputs=(reader or read_current)(analyst,[n for n in ids if n not in wait],view,str(first),str(last))
  except Exception as ex:gaps.append('Текущие источники: '+safe_error(ex))
 economies={int(p['nm_id']):p for p in source.get('products',[])}
 prices={int(p.get('nmID',p.get('nm_id',0))):p for p in fresh_inputs.get('prices',[])}
 stocks=fresh_inputs.get('stock',[]);camps=fresh_inputs.get('campaigns',{})
 rows=[];facts=[]
 for nm in ids:
  article=labels[nm];p=economies.get(nm,{})
  card=visibility(w,nm,article,str(day))
  if nm not in wait and not fresh(card,w.now,900):
   try:
    from china_article_offer import read as read_offer
    from china_analytic_dialog import reading
    with reading():card=read_offer(w,nm)
    w.save('china_agent:article_visibility:v1:'+str(nm),card)
   except Exception as ex:card=dict(available=False,reason='Витрина WB: '+safe_error(ex))
  quality=dict(observed_at=card.get('observed_at'),rating=card.get('rating'),review_count=card.get('review_count'))
  if not card:
   rv=w.get('china_agent:growth_review:v1:'+str(nm)) or {}
   quality=dict(observed_at=rv.get('observed_at'),rating=rv.get('rating') if rv.get('rating') else None,review_count=None,source='Seller feedback counts do not prove merged-card review count')
  stock_rows=[s for s in stocks if (s.get('article') or '').casefold()==article.casefold()]
  st=stock_rows[0] if len(stock_rows)==1 else {}
  pr=prices.get(nm,{})
  matched=[c for c in camps.values() if any(n.get('nm_id')==nm for n in c.get('nm_settings',[]))]
  # Saved membership is informative when changes already require observation.
  if not matched:matched=[c for c in view.get('campaigns',{}).values() if any(n.get('nm_id')==nm for n in c.get('nm_settings',[]))]
  if campaign_ids:matched=[c for c in matched if c.get('id') in campaign_ids]
  if not matched:matched=[{}]
  for c in matched:
   member=next((n for n in c.get('nm_settings',[]) if n.get('nm_id')==nm),{})
   placements=[z for z in ['search','recommendations'] if c.get('settings',{}).get('placements',{}).get(z) is True] or [None]
   for zone in placements:
    f=dict(nm_id=nm,article=article,unresolved_action=nm in pending,history_checked=history_checked,gaps=list(gaps)+fresh_inputs.get('gaps',[]),
     stock=dict(observed_at=fresh_inputs.get('stock_at'),available=st['stock']-st['reserve'] if number(st.get('stock')) and number(st.get('reserve')) and st['reserve']>=0 else None,cogs_cny=st['cost_rub']/12 if number(st.get('cost_rub')) else None),
     price=dict(observed_at=fresh_inputs.get('price_at'),currency=pr.get('currency'),seller_cny=pr.get('seller_price')),
     campaign=dict(id=c.get('id'),status=c.get('status'),currency=c.get('currency'),payment_type=c.get('settings',{}).get('payment_type'),placement=zone,bid_minor=member.get('bids_kopecks',{}).get(zone),minimum_minor=fresh_inputs.get('minimums',{}).get(str(c.get('id'))+':'+str(nm)+':'+str(zone)),step_minor=fresh_inputs.get('config',{}).get('cpcStep'),maximum_minor=fresh_inputs.get('config',{}).get('cpcMaxBid'),budget_cny=fresh_inputs.get('budgets',{}).get(str(c.get('id'))),observed_at=fresh_inputs.get('campaign_at')),
     quality=quality,visibility=card,changes=[x for x in changes if x.get('nm')==nm],availability_events=[x for x in availability if x['nm']==nm],
     daily=completed_rows(fresh_inputs.get('stats',view.get('stats',{})).get(c.get('id')),nm,str(first),str(last)))
    finished=p.get('finished_orders');paid=p.get('is_payed');policy=source.get('policy',{});log=policy.get('logistics_by_nm',{}).get(str(nm),{})
    valid_buyout=number(finished) and finished>0 and number(paid) and 0<=paid<=finished
    f['all_source']=fresh_inputs.get('general',{}).get(nm)
    f['economy']=dict(observed_at=source.get('observed_at'),buyout=paid/finished if valid_buyout else None,completed_sample=finished,commission_pct=p.get('total_commission_without_spp_in_sales'),logistics_cny=log.get('delivery_cny'),logistics_source=log.get('delivery_source'),tax_pct=policy.get('tax_pct'),handling_cny=policy.get('handling_rub',10)/policy.get('fx_rub_cny',12),own_period=[source.get('period_from'),source.get('period_to')])
    if not fresh(source,w.now,86400):f['gaps'].append('Собственная экономика старше24часов или дата неизвестна')
    today_rows=completed_rows(fresh_inputs.get('stats',view.get('stats',{})).get(c.get('id')),nm,str(day),str(day))
    if today_rows:f['today_observation']=dict(date=str(day),observed_at=fresh_inputs.get('campaign_at') or view.get('observed_at'),counters=today_rows[0],incomplete_day=True,used_for_selection=False)
    if card.get('reason'):f['gaps'].append('Витрина WB: '+str(card['reason']))
    if nm in pending:f['gaps'].append('Незавершённая или uncertain операция по SKU; повтор заблокирован')
    facts.append(f);rows.append(evaluate(f,w.now,days,raise_percent))
 seen_actions=set()
 for row in rows:
  if row['action'] and row['nm_id'] in seen_actions:row.update(action=None,recommendation='Нет',reason='Для SKU уже выделен один проект теста в другой РК; одновременное повышение не предлагается')
  elif row['action']:seen_actions.add(row['nm_id'])
 result=dict(status='complete' if all(r['stage'] not in ['incomplete','unknown','uncertain_action'] for r in rows) else 'partial',observed_at=w.now.isoformat(),period_from=str(first),period_to=str(last),rows=rows,facts=facts,execution_authorized=False,wb_writes=0,telegram_sends=0,source_key=key,cached=False)
 result['text']=render(result);w.save(key,result);return result
def read_current(analyst,ids,view,first,last):
 from china_analytic_dialog import reading
 from china_price_apply import IO
 from china_cloud_cost_control import WB
 from china_loss_ads import http,current
 w=analyst.w;result=dict(gaps=[],campaigns={},prices=[],stock=[],minimums={},budgets={},general={})
 def run(name,fn):
  try:return fn()
  except Exception as ex:result['gaps'].append(name+': '+safe_error(ex));return None
 def current_value(topic):
  value=analyst.live(topic,ids,None,None)
  if fresh(value,w.now):return value
  if analyst.fresh_reads>=3:raise ValueError('Лимит свежих источников; устаревшее не текущие данные')
  analyst.fresh_reads+=1
  with reading():data=analyst.collect(topic,[],__import__('datetime').date.fromisoformat(first),__import__('datetime').date.fromisoformat(last))
  return dict(data,observed_at=w.now.isoformat())
 stock=run('МойСклад МСК/COGS',lambda:current_value('stock'))
 price=run('Цена WB',lambda:current_value('prices'))
 if stock:result.update(stock=stock.get('rows',[]),stock_at=stock.get('observed_at'))
 if price:result.update(prices=price.get('rows',[]),price_at=price.get('observed_at'))
 # WB total funnel and advertising attribution remain separate; never subtract them as organic.
 with reading():
  try:
   from china_wb_evidence import Reports
   general=Reports(w).funnel(first,last)
   if general.get('complete'):
    result['general']={p['nm_id']:dict(p['selected'],source=general.get('source'),observed_at=general.get('observed_at'),period_from=first,period_to=last,scope='all_sources') for p in general.get('rows',[]) if p.get('nm_id') in ids}
  except Exception:pass
 if not all(nm in result['general'] for nm in ids):
  try:
   from china_saved_products import saved_products
   saved=saved_products(w,__import__('datetime').date.fromisoformat(first),__import__('datetime').date.fromisoformat(last),ids)
   for p in (saved or {}).get('rows',[]):
    nm=p['nm_id']
    if nm not in result['general']:result['general'][nm]=dict(orders=p.get('funnel_orders_count'),clicks=p.get('open_card_count'),source='MPStats exact-period fallback',observed_at=saved.get('observed_at'),period_from=first,period_to=last,scope='all_sources')
  except Exception:pass
 for nm in ids:
  if nm not in result['general']:result['general'][nm]=dict(orders=None,clicks=None,scope='all_sources',missing='Общая воронка WB/точный MPStats-период недоступны; органику не вычисляю вычитанием атрибуции')
 io=IO();wb=WB()
 selected=sorted({c['id'] for c in view.get('campaigns',{}).values() if any(n.get('nm_id') in ids for n in c.get('nm_settings',[]))})
 with reading():
  if not selected and view.get('requested_campaign_ids'):selected=view['requested_campaign_ids']
  cs=run('Текущий состав РК',lambda:current(io,selected or None))
  if cs is None:return result
  if view.get('requested_campaign_ids'):cs={cid:c for cid,c in cs.items() if cid in view['requested_campaign_ids']}
  cs={cid:c for cid,c in cs.items() if any(n.get('nm_id') in ids for n in c.get('nm_settings',[]))}
  if len(cs)>10:result['gaps'].append('Больше10РКдляодногоадресногосбора');return result
  result.update(campaigns=cs,campaign_at=w.now.isoformat())
  cfg=run('Минимальный шаг WB',lambda:http(io,'/api/advert/v1/config'))
  if cfg and cfg.get('currency')=='CNY':result['config']=cfg
  elif cfg:result['gaps'].append('Валюта конфигурации WB не CNY')
  if cs:
   stat=run('Реклама по полным дням',lambda:http(io,'/adv/v3/fullstats?ids='+','.join(map(str,cs))+'&beginDate='+first+'&endDate='+str(w.now.astimezone(MSK).date())))
   if isinstance(stat,list) and all(c.get('currency')=='CNY' for c in stat):result['stats']={c['advertId']:c for c in stat}
   elif stat is not None:result['gaps'].append('Валюта/форма рекламной статистики не подтверждена')
  for cid,c in cs.items():
   budget=run('Бюджет РК'+str(cid),lambda:http(io,'/adv/v1/budget?id='+str(cid)))
   if isinstance(budget,dict) and number(budget.get('total')) and c.get('currency')=='CNY':result['budgets'][str(cid)]=budget['total']
   for zone in ['search','recommendations']:
    selected_nm=[n['nm_id'] for n in c.get('nm_settings',[]) if n['nm_id'] in ids and c.get('settings',{}).get('placements',{}).get(zone) is True]
    if not selected_nm or c.get('status')!=9 or c.get('settings',{}).get('payment_type')!='cpc':continue
    minimums=run('Минимум WB РК'+str(cid),lambda:wb.minimums(cid,selected_nm,zone))
    if minimums:result['minimums'].update({str(cid)+':'+str(nm)+':'+zone:v for nm,v in minimums.items()})
 return result
def handle(w,job,history):
 if not requested(job.get('request_text','')):return None
 ids=scope(w,job,history)
 if not ids:return None
 from china_analytic_dialog import Analyst
 text=job.get('request_text','')
 percent=re.search(r'(?:ставк|повыс|подня|тест).*?(?:на|\+)\s*(\d+(?:[.,]\d+)?)\s*%',text,re.I)
 period=re.search(r'(?:последни[ех]|за)\s+(\d+)\s+дн',text,re.I)
 cids=[int(x) for x in re.findall(r'(?<!\d)(4\d{7})(?!\d)',text)]
 result=collect(Analyst(w,job,history),ids,days=int(period[1]) if period else 3,raise_percent=float(percent[1].replace(',','.')) if percent else 10,campaign_ids=cids)
 return result['text'],[dict(name='article_diagnostic',source_key=result['source_key'],status=result['status'],nm_ids=ids,read_only=True,wb_writes=0)]
