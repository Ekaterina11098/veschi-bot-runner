"""Cloud Codex decides report contents; deterministic collectors/guards/renderers remain."""
import copy,json,re
from china_codex_analysis import Core,active,digest,text_review,POLICY
DIRECTIONS=('raise','add','reduce','exclude')
def direction(a):
 k=a.get('kind')
 if k=='ad_exclude_sku':return 'exclude'
 if k in ('ad_add_sku','ad_add_nms'):return 'add'
 if k=='ad_set_bid':return 'raise'if a['target_minor']>a['old_minor']else'reduce'
 return None
def compact_source(s):
 from china_advertising_v2 import history,event_time,MSK
 products={}
 for batch in s.get('batches',{}).values():
  for campaign in batch.get('stats',[]):
   cid=campaign['advertId']
   for day in campaign.get('days',[]):
    for app in day.get('apps',[]):
     for n in app.get('nms',[]):
      key=str(cid)+':'+str(n['nmId']);p=products.setdefault(key,dict(campaign_id=cid,nm_id=n['nmId'],daily={}))
      m=p['daily'].setdefault(day['date'][:10],dict(spend=0,amount=0,clicks=0,views=0,orders=0,baskets=0))
      for a,b in [('spend','sum'),('amount','sum_price'),('clicks','clicks'),('views','views'),('orders','orders'),('baskets','atbs')]:m[a]+=n.get(b,0)
 columns=['spend','amount','orders','clicks','views','baskets']
 compact_products={key:dict(campaign_id=p['campaign_id'],nm_id=p['nm_id'],daily={day:[row[k]for k in columns]for day,row in p['daily'].items()})for key,p in products.items()}
 fields=['observed_at','period_from','period_to','own_cogs_rub','seller_price_cny','stock_free','published_stock','buyout','sample_size','buyout_fallback','commission_policy_fallback','commission_pct','tax_pct','handling_rub','logistics_cny','expected_margin_before_ads_cny','price_observed_at','stock_observed_at','published_stock_observed_at','fx_rub_per_cny','fx_date','preliminary','unknown_reverse_and_shared_costs']
 economics=s.get('economics',{})
 current=(s.get('full_growth_inputs')or{}).get('campaigns')or[c for b in s.get('batches',{}).values()for c in b.get('campaigns',{}).get('adverts',[])]
 return dict(period_from=s.get('period_from'),period_to=s.get('period_to'),observed_at=s.get('observed_at'),day_quality=s.get('day_quality'),products=compact_products,product_daily_columns=columns,
  owner_held_nm_ids=(s.get('full_growth_inputs')or{}).get('excluded_nm_ids',[]),current_campaigns=[dict(id=c['id'],status=c['status'],currency=c['currency'],bid_type=c['bid_type'],settings=c['settings'],nm_settings=[dict(nm_id=n['nm_id'],subject_id=n['subject']['id'],bids_kopecks=n['bids_kopecks'])for n in c['nm_settings']])for c in current],
  catalogue=dict(rows=[dict(nmID=r['nmID'],vendorCode=r['vendorCode'])for r in s.get('catalogue',{}).get('rows',[])]),
  economics=dict(status=economics.get('status'),rows={nm:{k:e[k]for k in fields if k in e}for nm,e in economics.get('rows',{}).items()},missing=economics.get('missing',{})),
  addition_scan=s.get('addition_scan'),growth_inputs_scope=s.get('full_growth_review')or s.get('growth_scope'),
  changes=[dict(nm=x.get('nm'),campaign_id=x.get('cid'),kind=x.get('kind'),at=x.get('at'))for x in history(s.get('executions',[]))],wb_action_permission=False)
def compact_report(bundle):
 """All arithmetic stays in the renderer source; avoid charging twice for repeated raw evidence."""
 keys=['id','name','status','payment','zone','balance','period','last','budget_period','budget_days','budget_reference_need','budget_cash_gap','budget_reserve_amount','budget_economics_status','budget_economics_reason','budget_recommendation']
 out={k:bundle[k]for k in ['days','budget_days','source_observed_at','budget_observed_at','total_yesterday_spend','full_cabinet_growth_review']if k in bundle}
 out['campaigns']=[]
 for c in bundle['campaigns']:
  row={k:c[k]for k in keys if k in c}
  row['focus']=[dict(nm=r['nm'],article=r['article'],decision=r.get('decision'),period=r.get('period'),comparison=r.get('comparison'),action_id=(r.get('action')or{}).get('id'),pending_first_day=r.get('pending_first_day'))for r in c.get('focus',[])]
  row['budget_member_count']=len(c.get('budget_members',[]))
  out['campaigns'].append(row)
 return out
def ad_validate(value,actions,campaigns,labels):
 if value.get('kind')!='advertising_review':raise ValueError('Advertising review kind required')
 rows=value.get('decisions')
 if not isinstance(rows,list)or len(rows)>len(actions):raise ValueError('Decision list invalid')
 seen=set()
 for r in rows:
  if not isinstance(r,dict)or r.get('id')not in actions or r['id']in seen:raise ValueError('Unverified/duplicate action selected')
  seen.add(r['id'])
  if set(r)-{'id','note','reason'}:raise ValueError('Cloud cannot change action parameters')
  if not isinstance(r.get('note'),str)or not 0<len(r['note'])<=180:raise ValueError('Brief recommendation required')
 coverage=value.get('directions')
 if not isinstance(coverage,dict)or set(coverage)!=set(DIRECTIONS):raise ValueError('All four directions required')
 for d in coverage.values():
  if d.get('status')not in ('checked','unavailable')or not isinstance(d.get('note'),str)or len(d['note'])>3000:raise ValueError('Coverage must distinguish unavailable from no candidates')
 research=value.get('research',[])
 if not isinstance(research,list)or len(research)>12:raise ValueError('Research scope invalid')
 for r in research:
  if r.get('nm_id')not in labels or r.get('campaign_id')not in campaigns or r.get('direction')not in ('raise','add'):raise ValueError('Research subject outside current cabinet')
  if not isinstance(r.get('note'),str)or not 0<len(r['note'])<=1800:raise ValueError('Research note outside bounded scope')
  if len(r['note'])>110:
   r['private_reason']=r['note'];r['note']='Нужны проверка текущей экономики, наличия и минимальной ставки.'
 return value
def review_advertising(io,bundle,source,identity,observational=None,force=False,core=None):
 if core is None and not force and (io.get(POLICY)or{}).get('status')!='active':return bundle
 core=core or Core()
 if not force and not active(core.db):return bundle
 actions={};subjects={};funding={};readiness_blocks=[]
 blocked=(core.db.get(POLICY)or{}).get('owner_withdrawn_actions',[])
 def withdrawn(a):return any(a.get('campaign_id')==x.get('campaign_id') and a.get('nm_id')==x.get('nm_id') and a.get('kind')==x.get('kind')for x in blocked)
 for c in bundle['campaigns']:
  for r in c.get('focus',[])+c.get('attention',[]):
   a=r.get('action')
   if not a or withdrawn(a):continue
   e=r.get('economics')or a.get('growth_evidence')or{}
   if (core.db.get(POLICY)or{}).get('require_published_stock') and e.get('published_stock')is None:
    readiness_blocks.append(dict(id=a.get('id'),article=r['article'],blocker='Current published WB stock not confirmed'));continue
   if direction(a)in('raise','add')and e.get('published_stock')==0:
    readiness_blocks.append(dict(id=a.get('id'),article=r['article'],blocker='Current published WB stock zero'));continue
   key=a.get('id')or str(c['id'])+':'+str(a.get('nm_id'))
   if direction(a) is None:continue
   if key in actions and actions[key]!=a:raise ValueError('Conflicting exact candidate')
   actions[key]=copy.deepcopy(a);subjects[key]=dict(article=r['article'],campaign_id=c['id'],decision=r.get('decision'),economics_ref=str((a or{}).get('nm_id')),metrics=(r.get('comparison')or{}).get('after')or r.get('period'),basis_days=(r.get('comparison')or{}).get('to_days')or bundle.get('days'),evidence_ref='allowed_actions.'+key+'.growth_evidence' if a.get('growth_evidence') else r.get('closed_day_evidence'))
  a=c.get('budget_action')
  if a:
   key='funding:'+str(c['id']);actions[key]=copy.deepcopy(a);funding[key]=c['id']
   subjects[key]=dict(campaign_id=c['id'],balance=c.get('balance'),forecast=c.get('forecast'),budget_period=c.get('budget_period'),note=c.get('budget_recommendation'))
 labels={int(x['nmID']):x['vendorCode']for x in source.get('catalogue',{}).get('rows',[])}
 campaigns={c['id']for c in bundle['campaigns']}
 contract=dict(kind='advertising_review',decisions=[dict(id='exact allowed_actions key',note='Короткое действие без чисел/ставок: параметры возьмутся из immutable action',reason='Private reasoning')],directions={d:dict(status='checked|unavailable',note='Private coverage conclusion')for d in DIRECTIONS},research=[dict(nm_id='known nm',campaign_id='known campaign',direction='raise|add',note='Краткая непроверенная идея без конкретной непроверенной ставки')],summary='Private concise analysis')
 data=dict(report=compact_report(bundle),completed_source=compact_source(source),intraday_observation=observational,allowed_actions=actions,candidate_evidence=subjects,readiness_blocks=readiness_blocks,
  instruction='Самостоятельно проверь все направления и экономику. Черновые кандидаты не рекомендация. Отбери только обоснованные; маленькую собственную выборку/разовый ноль не объявляй доказательством. Предложи исследовать рост по другим товарам, если есть конкретные данные. Готовые действия — только exact allowed_actions. Сегодняшний день не основание снижения/исключения. Funding допускает только3-дневный расчёт.')
 result,receipt=core.ask(identity,'advertising',data,contract,lambda v:ad_validate(v,actions,campaigns,labels),force)
 selected={r['id']:r for r in result['decisions']};out=copy.deepcopy(bundle)
 for c in out['campaigns']:
  for group in ('focus','attention'):
   kept=[]
   for r in c.get(group,[]):
    a=r.get('action');key=(a or{}).get('id')or str(c['id'])+':'+str((a or{}).get('nm_id'))
    if a and key not in selected:r['action']=None
    if a and key in selected:
     # Exact action values and actual article retained; model wording is private.
     r['codex_reason']=selected[key].get('reason');r['codex_note']=selected[key]['note']
    if group!='attention' or r.get('action'):kept.append(r)
   c[group]=kept
  fid='funding:'+str(c['id'])
  rejected_composition=any(a.get('campaign_id')==c['id'] and direction(a)in('reduce','exclude') and k not in selected for k,a in actions.items())
  if c.get('budget_action')and (fid not in selected or rejected_composition):
   c['budget_action']=None;c['forecast']=None;c['coverage']=None;c['budget_recommendation']='Пересчитать резерв на три дня перед пополнением.'
  c['codex_research_recommendations']=[labels[r['nm_id']]+': проверить '+('повышение'if r['direction']=='raise'else'добавление')+'; '+r['note'] for r in result.get('research',[])if r['campaign_id']==c['id']]
 from china_advertising_directions import attach
 out=attach(out,source)
 for name,status in result['directions'].items():
  out['recommendation_directions'][name]['status']=status['status'];out['recommendation_directions'][name]['note']=status['note']
 out['codex_analysis']=dict(receipt,identity=identity,summary=result.get('summary'),research=result.get('research',[]),selected_action_ids=list(selected),backend='managed_codex',legacy_analysis_used=False)
 return out
def price_parts(draft):
 lines=draft.splitlines();tables=[];plain=[];candidates={};index=0
 while index<len(lines):
  if re.match(r'^(?:Повышение|Снижение) · .+ Продавец:',lines[index]) and index+1<len(lines) and lines[index+1].startswith('Покупатель:'):
   key='row:'+str(index);candidates[key]='\n'.join(lines[index:index+2]);plain.append(key);index+=2;continue
  if '|'in lines[index]and index+1<len(lines)and re.match(r'^\s*\|?[\s:|-]+\|[\s:|-]*$',lines[index+1]):
   table=dict(header=lines[index:index+2],rows=[]);index+=2
   while index<len(lines)and '|'in lines[index]and lines[index].strip():
    key='row:'+str(index);candidates[key]=lines[index];table['rows'].append(key);index+=1
   tables.append(table);continue
  if re.search(r'\d{1,4}-[A-Za-z]',lines[index]):
   key='row:'+str(index);candidates[key]=lines[index];plain.append(key)
  index+=1
 return candidates,tables,plain
def review_price(worker,draft,trace,force=False,core=None):
 if getattr(worker,'mode',None)=='control':
  value=getattr(worker,'control_value',None)or{}
  if value.get('model_version')!='wb_profit_floor_price_hypothesis_v4' or value.get('report_date')!=str(worker.day):raise ValueError('Control report canonical scope missing')
  return draft,list(trace)+[dict(name='china_control_canonical_report',model_calls=0,read_only=True)]
 if core is None and not force:
  from china_no_paid import require_paid_api
  try:require_paid_api(worker.get('china_agent:codex_cloud:v1:policy')or{})
  except PermissionError:
   if not any(e.get('name')=='china_price_daily_report' and e.get('status')=='complete_orders' for e in trace):raise ValueError('Completed deterministic price inputs missing')
   review=getattr(worker,'price_control_review',None)or{}
   if review.get('status')!='complete_disclosed_forecast_model':raise ValueError('Full price reduction review incomplete')
   from china_price_current_check import check as check_current
   answer=check_current(worker,draft)
   return answer,list(trace)+[dict(name='china_price_rules_review',model_calls=0,read_only=True,source='completed deterministic rules and current price/MSK/WB checks')]
 if core is None and not force and (worker.get(POLICY)or{}).get('status')!='active':return draft,trace
 core=core or Core()
 if not force and not active(core.db):return draft,trace
 rows,tables,plain=price_parts(draft)
 from china_price_evidence import price_evidence
 source=price_evidence(worker)
 source_key='china_agent:price_evidence:v1:'+str(worker.day)+':'+str(getattr(worker,'mode',worker.audit.get('mode')))+':'+digest(source)
 worker.save(source_key,source)
 worker.audit['price_evidence']=dict(source_key=source_key,status=source['status'],financial_rows=len(source['financial_rows']),settled_cohort_profit_status=source['settled_cohort_profit_status'])
 data=dict(completed_source=source,report_day=str(worker.day),mode=getattr(worker,'mode',worker.audit.get('mode')),draft_evidence=draft,rows=rows,audit={k:worker.audit[k] for k in ['mode','source_blocker','errors','source_snapshot_id','source_collected_at','calculated_at'] if k in worker.audit},
  evidence_scope='Exact prevalidated actionable draft rows plus structured completed-period financial evidence. No draft candidates does not mean no source data. Reported MPStats profit is not settled cohort profit.',
  instruction='Сформулируй собственный краткий вывод; выбери исходные строки с достаточными основаниями. Не меняй их числа/товары/цены. Правило «заказы держатся — цену сохранить» запрещает необоснованное снижение после теста, но НЕ отменяет согласованное повторное повышение +5% после четырёх полных дней ежедневных заказов и сохранённой общей конверсии. Отдельно оцени наличие дневных заказов, отчётной экономики завершённого периода и окончательно закрытой прибыли когорты. Не называй отсутствующими переданные financial_rows. Для повышения +5% применяй согласованные дневные заказы и сохранённую общую конверсию: рост прибыли и окончательно закрытая прибыль когорты не являются условиями допуска. Для снижения нужны собственная предварительная экономика и проверка причин падения; неизвестные расходы не ноль. Отсутствие части источников не означает отсутствие кандидатов во всём каталоге. Не дополняй сегодня сравнением полного вчера. Summary без чисел/новых цен, конкретные проверенные данные только в выбранных исходных строках.')
 def validate(v):
  if v.get('kind')!='price_review' or not isinstance(v.get('keep_rows'),list)or len(set(v['keep_rows']))!=len(v['keep_rows'])or any(x not in rows for x in v['keep_rows']):raise ValueError('Price rows changed/outside evidence')
  if not isinstance(v.get('summary'),str)or not v['summary'].strip() or re.search(r'\d|[¥₽→]',v['summary']):raise ValueError('Price summary must not invent actionable numbers')
  if len(v['summary'])>650:
   # Preserve full provider completion privately; length is presentation, not an action failure.
   v['summary']=v['summary'][:647].rsplit(' ',1)[0]+'…'
  return v
 ident='price:'+str(worker.day)+':'+str(getattr(worker,'mode',worker.audit.get('mode')))+':'+str(getattr(worker,'section',''))
 result,receipt=core.ask(ident,'price',data,dict(kind='price_review',keep_rows=['exact row ids'],summary='Краткий человеческий вывод без чисел и новых цен'),validate,force)
 from china_price_review_guard import protected_repeats
 protected=protected_repeats(worker,rows)
 keep=set(result['keep_rows'])|protected
 worker.audit['price_review_guard']=dict(protected_repeat_rows=sorted(protected),model_omitted_ready_repeat_rows=sorted(protected-set(result['keep_rows'])),rule='owner_four_full_days_daily_orders_and_general_conversion_held')
 parts=[] if rows else [draft]
 for t in tables:
  chosen=[rows[k]for k in t['rows']if k in keep]
  if chosen:parts.append('\n'.join(t['header']+chosen))
 for key in plain:
  if key in keep:parts.append(rows[key])
 answer='\n\n'.join(parts) if parts else 'Повышение: нет готовых рекомендаций\n\nСнижение: нет готовых рекомендаций'
 from china_price_current_check import check as check_current
 if rows:
  try:answer=check_current(worker,answer)
  except (RuntimeError,ValueError) as exc:
   worker.audit['current_price_check_blocker']=str(exc)[:200]
   answer='Повышение: проверка не завершена\n\nСнижение: проверка не завершена'
 worker.audit['codex_analysis']=receipt
 return answer,list(trace)+[dict(name='china_codex_analysis',**receipt)]
