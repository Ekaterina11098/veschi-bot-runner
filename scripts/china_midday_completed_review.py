"""Carry calculated completed-day recommendations into the current-day report."""
import copy
from datetime import date,timedelta,datetime,timezone
from china_advertising_v2 import collect,refresh_budget_context,build,http,save,history,MSK,never_started_draft
def include_closed(io,source,day):
 source=copy.deepcopy(source)
 inventory=http(io,'/adv/v1/promotion/count')
 ids=sorted({a['advertId']for g in inventory.get('adverts',[])if g['status']==7 for a in g.get('advert_list',[])}-set(source['ids']))
 if len(ids)>50:raise ValueError('Closed campaign scope requires bounded pagination')
 if ids:
  joined=','.join(map(str,ids));source['ids']=sorted(source['ids']+ids)
  source['batches']['closed']=dict(campaigns=http(io,'/api/advert/v2/adverts?ids='+joined),budgets=http(io,'/api/advert/v2/budget','POST',dict(advertIds=ids)),stats=http(io,'/adv/v3/fullstats?ids='+joined+'&beginDate='+day+'&endDate='+day))
 key='china_agent:advertising_midday_inclusive:'+day+':v1';save(io,key,source)
 return source
def merge_completed(bundle,review,source_ref):
 out=copy.deepcopy(bundle);closed={c['id']:c for c in review['campaigns']}
 for c in out['campaigns']:
  c['attention']=[];r=closed.get(c['id'])
  if not r:continue
  if r.get('recommendation_review_note'):c['recommendation_review_note']=r['recommendation_review_note']
  done=[]
  for row in r.get('focus',[]):
   if row.get('already_excluded') or row.get('pending_first_day'):
    if row.get('done')and row.get('done')!='Нет подтверждённых изменений':done.append(row['article']+': '+row['done'])
    continue
   if not row.get('action'):continue
   days=(row.get('comparison')or{}).get('to_days')or review['days']
   if not days or days[-1]>=out['day']:raise ValueError('Partial day cannot become an action basis')
   evidence=(row['action'].get('growth_evidence')or{})
   days=evidence.get('decision_days')or days
   m=(row.get('comparison')or{}).get('after')or row.get('period')
   if row['action']['kind']=='ad_add_sku':
    days=[evidence['period_from'],evidence['period_to']]
   if days[-1]>=out['day']:raise ValueError('Partial growth day cannot become an action basis')
   c['attention'].append(dict(article=row['article'],decision=row['decision'],action=row['action'],spend=(m or{}).get('spend'),clicks=(m or{}).get('clicks'),closed_day_evidence=dict(period_from=days[0],period_to=days[-1],verified=True,source_ref=source_ref,postclick_reviewed=True,metrics=m,ad_cpa_unknown=evidence.get('ad_cpa_unknown',False))))
  c['completed_actions']=list(dict.fromkeys(done))
 out['recommendation_directions']=copy.deepcopy(review.get('recommendation_directions',{}))
 out['growth_review']=copy.deepcopy(review.get('growth_review',{}))
 if review.get('codex_analysis'):out['codex_analysis']=copy.deepcopy(review['codex_analysis'])
 if review.get('sales_growth_review'):out['sales_growth_review']=copy.deepcopy(review['sales_growth_review'])
 for c in out['campaigns']:
  c['codex_research_recommendations']=copy.deepcopy((closed.get(c['id'])or{}).get('codex_research_recommendations',[]))
 for c in out['campaigns']:
  c['addition_review_notes']=[]
 for row in out['recommendation_directions'].get('add',{}).get('rows',[]):
  campaign=next((c for c in out['campaigns']if c['id']==row.get('campaign_id')),None)
  if campaign and row.get('bid_verified')is True:
   campaign['addition_review_notes'].append(row['article']+': кандидат на добавление; требуется отдельный точный план.')

 out['recommendation_basis']='completed_days_with_fresh_economics_and_current_state'
 return out
def completed_campaign_stats(io,campaigns,saved_stats,period_from,period_to):
 """A campaign created after the closed window has verified empty history, not missing API data."""
 result=copy.deepcopy(saved_stats);missing=[]
 for c in campaigns:
  cid=c['id']
  if cid in result:continue
  created=c.get('timestamps',{}).get('created')
  try:
   at=datetime.fromisoformat(created.replace('Z','+00:00'))
   if at.tzinfo is None:raise ValueError('Creation timestamp has no timezone')
   after_window=at.astimezone(MSK).date()>date.fromisoformat(period_to)
  except (AttributeError,TypeError,ValueError):after_window=False
  if after_window:
   result[cid]=dict(advertId=cid,currency='CNY',days=[],sum=0,orders=0,sum_price=0,clicks=0,views=0,atbs=0,
                    history_status='created_after_completed_window',history_evidence=dict(created_at=created,period_from=period_from,period_to=period_to))
  else:missing.append(cid)
 if missing:
  extra=http(io,'/adv/v3/fullstats?ids='+','.join(map(str,missing))+'&beginDate='+period_from+'&endDate='+period_to)
  if not isinstance(extra,list):raise ValueError('Completed-day campaign history unavailable: expected list for '+','.join(map(str,missing)))
  for r in extra:
   if not isinstance(r,dict)or type(r.get('advertId'))is not int or r['advertId']not in missing or not isinstance(r.get('days'),list):raise ValueError('Completed-day campaign history malformed')
   result[r['advertId']]=copy.deepcopy(r)
 if any(c['id']not in result for c in campaigns):raise ValueError('Completed-day campaign history incomplete')
 return result

def validate_recommendation_readiness(review):
 if not review.get('economic_review_complete'):
  # Missing evidence blocks that recommendation, not the scheduled factual report.
  blockers=review.get('economic_review_blockers',[])
  if not blockers:raise ValueError('Economic review incomplete without explicit blockers')
  for campaign in review['campaigns']:
   affected={r['article']for r in blockers if r['campaign_id']==campaign['id']}
   for row in campaign.get('focus',[])+campaign.get('attention',[]):
    if row.get('article')in affected and row.get('action'):raise ValueError('Unready economic action survived')
   if affected:campaign['recommendation_review_note']='Нет готовых действий: проверка данных не завершена.'
  for section in review.get('recommendation_directions',{}).values():section['status']='unavailable'
 return review

def attach(io,bundle,day):
 from china_morning_readiness import enrich_economics
 from china_advertising_cards import enhance
 from china_advertising_economic_review import apply
 current=io.get('china_agent:advertising_midday_inclusive:'+day+':v1')or collect(io,day,current=True);source=copy.deepcopy(collect(io,day))
 end=str(date.fromisoformat(day)-timedelta(days=1))
 if source.get('day_quality',{}).get('usable')is not True or source['period_to']!=end:raise ValueError('Usable completed-day source required')
 source=refresh_budget_context(io,source,day)
 saved_stats={r['advertId']:copy.deepcopy(r) for b in source['batches'].values() for r in b['stats']}
 source['ids']=list(current['ids']);source['batches']=copy.deepcopy(current['batches'])
 for batch in source['batches'].values():
  ids=[c['id']for c in batch['campaigns']['adverts'] if not never_started_draft(c)]
  active=[c for c in batch['campaigns']['adverts']if c['id']in ids]
  saved_stats=completed_campaign_stats(io,active,saved_stats,source['period_from'],end)
  batch['stats']=[copy.deepcopy(saved_stats[cid]) for cid in ids]
 source['observed_at']=datetime.now(timezone.utc).isoformat();source['budget_balance_observed_at_iso']=current.get('completed_at',current['observed_at'])
 rough=build(source)
 from china_advertising_full_growth import enabled as full_enabled,collect as collect_full
 class MiddayFullIO:
  # Reuse completed own history; refresh intraday price/stock/bids in a separate resumable journal.
  def key(self,key):return key+':midday' if key.startswith('china_agent:advertising_full_growth:')else key
  def get(self,key):return io.get(self.key(key))
  def create(self,key,value):return io.create(self.key(key),value)
  def put(self,key,value):return io.put(self.key(key),value)
  def __getattr__(self,name):return getattr(io,name)
 source=collect_full(MiddayFullIO(),source,day) if full_enabled(io) else enrich_economics(io,source,rough,day)
 if source.get('full_growth_review'):source['full_growth_review']['input_key']+=':midday'
 if source.get('morning_fresh_inputs',{}).get('errors'):raise ValueError('Fresh completed-day recommendation inputs incomplete')
 minima={}
 for c in rough['campaigns']:
  # Economics may create a precise action from a formerly unready row.
  ids=[r['nm']for r in c['focus']if not r.get('pending_first_day')and 'Выполнено.'not in r['decision']]
  if not ids or c['status']!=9 or c['payment']!='cpc':continue
  zone='search'if c['zone']=='поиск'else'recommendation'
  raw=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=c['id'],nm_ids=ids,payment_type='cpc',placement_types=[zone]))
  found=set()
  for row in raw.get('bids',[]):
   values=[v['value']for v in row['bids']if v['type']==zone and v['currency']=='CNY']
   if len(values)!=1:raise ValueError('Unverified current minimum')
   found.add(row['nm_id']);minima[str(c['id'])+':'+str(row['nm_id'])]=values[0]
  if found!=set(ids):raise ValueError('Incomplete current minima')
 from china_advertising_growth import enrich as growth_enrich
 from china_advertising_directions import attach as attach_directions
 # Use the same four-direction review as the morning report. Missing evidence remains unavailable.
 source['addition_bid_quotes']={};source['addition_quote_errors']={}
 for nm in source.get('addition_candidate_ids',[]):
  cid=(source.get('addition_targets')or{}).get(str(nm))
  if not cid:continue
  try:
   raw=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=[nm],payment_type='cpc',placement_types=['recommendation']))
   values=[v['value']for row in raw.get('bids',[])if row.get('nm_id')==nm for v in row.get('bids',[])if v.get('type')=='recommendation'and v.get('currency')=='CNY']
   if len(values)!=1 or type(values[0])is not int or values[0]<=0 or values[0]%source['config']['cpcStep']:raise ValueError('Exact addition minimum unavailable')
   source['addition_bid_quotes'][str(nm)]=dict(campaign_id=cid,target_minor=values[0],bid_verified=True,observed_at=source['observed_at'])
  except Exception as ex:source['addition_quote_errors'][str(nm)]=type(ex).__name__
 class MiddayGrowthIO:
  # Morning proposals can predate today's verified changes. Do not reuse that journal.
  def get(self,key):return io.get(key+':midday' if key.startswith('china_agent:daily_growth:')else key)
  def create(self,key,value):return io.create(key+':midday' if key.startswith('china_agent:daily_growth:')else key,value)
  def __getattr__(self,name):return getattr(io,name)
 review=apply(enhance(build(source,minima),source),source,minima)
 if source.get('full_growth_inputs'):
  from china_advertising_full_growth import enrich as full_review
  review=full_review(MiddayFullIO(),source,review)
 else:review=growth_enrich(MiddayGrowthIO(),source,review)
 review=attach_directions(review,source)
 from china_codex_reports import review_advertising
 review=review_advertising(io,review,source,'advertising:'+day+':midday',bundle)
 from china_sales_growth_review import attach as sales_review
 review=sales_review(review)
 review=validate_recommendation_readiness(review)
 key='china_agent:advertising_midday_completed:'+day+':v1';save(io,key,dict(source=source,review=review,status='complete',observed_at=source['observed_at'],wb_writes=0))
 return merge_completed(bundle,review,key)


