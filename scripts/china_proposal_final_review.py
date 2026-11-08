"""A complete scoped decision ledger must precede any proposal delivery."""
import math
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote
from china_ad_retest import assess,period,finite

ROOT='china_agent:proposal_final_review:v1:'
HOLD={1007948808,1473245494,1473245510,1473243903}

def complete(io,s,req):
 day=datetime.now(ZoneInfo('Europe/Moscow')).date()
 full=io.get('china_agent:advertising_full_growth:'+str(day)+':v1:inputs')or{}
 if full.get('cabinet')!='token_3' or full.get('status')!='complete':raise ValueError('Полная экономика кабинета Китай недоступна')
 # Never invent a logistics cost because an older proposal cache omitted a SKU.
 economics=(full.get('economics')or{}).get('rows',{})
 own={int(r['nm_id']):r for r in full.get('own',{}).get('rows',[])}
 policy=dict(s['policy'],logistics_by_nm=dict(s['policy']['logistics_by_nm']))
 supplements=[]
 for nm,e in economics.items():
  if nm not in policy['logistics_by_nm'] and finite(e.get('logistics_cny')) and e['logistics_cny']>0 and e.get('logistics_historical')is True:
   policy['logistics_by_nm'][nm]=dict(delivery_cny=e['logistics_cny'],source_key='china_agent:advertising_full_growth:'+str(day)+':v1:inputs',historical=True);supplements.append(int(nm))
 s=dict(s,policy=policy)
 active={n['nm_id']for c in s['campaigns'].values()if c.get('status')==9 for n in c.get('nm_settings',[])}
 wanted=set(req.get('nm_ids',[]));subjects=set(req.get('subject_ids',[]))
 products=[r for r in s['products']if (not wanted or int(r['nm_id'])in wanted) and(not subjects or r.get('subject_id')in subjects)]
 scoped=dict(s,products=products)
 candidates={r['nm_id']:r for r in assess(scoped,manual_review=True)}
 ledger=[];groups={'orders':[],'demand':[]};blocked=[]
 # Complete day evidence is mandatory; live day is never substituted.
 end=date.fromisoformat(s['period_to'])
 post=period(io,end,end,collect=True)
 if not post:raise ValueError('Нет полного среза общей воронки за '+str(end)+'; итоговый подбор не отправлен')
 postrows={int(r['nm_id']):r for r in post['rows']}
 for p in products:
  nm=int(p['nm_id']);r=candidates.get(nm);e=economics.get(str(nm))or{};o=own.get(nm)or{}
  if r is None and e and not e.get('buyout_fallback') and e.get('sample_size',0)>=3 and e.get('stock_free',0)>=5 and nm not in active and nm not in HOLD:
   from china_experience import assess_candidate
   price=next((q['sizes'][0]['discountedPrice']for q in s['prices']if q['nmID']==nm),None)
   matches=[v for v in s['stock']if str(v.get('article','')).casefold()==p['sa_name'].casefold()]
   if price and len(matches)==1 and p.get('open_card_count') and p.get('funnel_orders_count')is not None:
    reasons=[];ret=(s.get('retest_evidence')or{}).get(str(nm))
    history=assess_candidate(s['experience']['experiences'],nm,dict(seller_price=price,stock_available=matches[0]['stock']-matches[0]['reserve'],rating=p.get('commentsvaluation')))
    if nm in s['experience'].get('recent_changed_nm_ids',[]):reasons.append('Недавнее изменение: заданное окно ещё не завершено')
    if history['needs_review']:reasons.append('Не разобрана причина прежнего финансового убытка')
    if nm in s.get('protected',[]) and (not ret or ret.get('status')!='improved'):reasons.append('Не подтверждено улучшение после исключения')
    if p.get('advertisement')is None:reasons.append('Не подтверждена история рекламных расходов')
    r=dict(nm_id=nm,article=p['sa_name'],subject_id=p['subject_id'],price_cny=price,stock=matches[0]['stock']-matches[0]['reserve'],paid=p['is_payed'],finished=p['finished_orders'],conversion=100*p['funnel_orders_count']/p['open_card_count'],recent_orders=0,group='demand',requires_review=reasons,retest=ret,memory_used=True,memory_event_ids=history['event_ids'])
  record=dict(nm_id=nm,article=p['sa_name'],checks_complete=True,status='rejected',source_keys=['china_agent:new_ad_source:v1:'+str(day),'china_agent:advertising_full_growth:'+str(day)+':v1:inputs',post.get('source_key')or post.get('snapshot_id')])
  if nm in HOLD:record['reason']='Отдельный запрет владельца'
  elif nm in active:record.update(status='out_of_scope',reason='Уже в активной рекламе: не новый запуск и не повод создавать дубль')
  elif not e or e.get('model_unavailable'):
   # New draft cards with zero price or zero MSK stock are observed non-candidates, not pending research.
   price=next((q['sizes'][0]['discountedPrice']for q in s['prices']if q['nmID']==nm),None)
   if price==0:record['reason']='Текущая цена WB равна нулю; карточка не готова к рекламному тесту'
   elif e.get('stock_free')==0:record['reason']='Свободный остаток МСК равен нулю'
   elif (p.get('finished_orders')or 0)<3:record['reason']='Недостаточно собственного завершённого выкупа для положительной экономики'
   else:record.update(status='blocked',checks_complete=False,reason='Нет подтверждённой адресной экономики/COGS: '+str(e.get('model_unavailable')or nm))
  elif e.get('stock_free',0)<5:record['reason']='Недостаточный свободный остаток МСК для теста'
  elif (p.get('finished_orders')or 0)<3 or e.get('buyout_fallback'):record['reason']='Недостаточно собственного завершённого выкупа; усреднённый выкуп не подставлен'
  elif r is None:
   if not finite(e.get('expected_margin_before_ads_cny')):record.update(status='blocked',checks_complete=False,reason='Нет полного расчёта собственных затрат')
   else:record['reason']='Сценарная экономика/спрос не проходит проверку положительного ограниченного теста'
  else:
   fx=e['fx_rub_per_cny'];delivery=max(e['logistics_cny'],(o.get('average_delivery_cost')or 0)/fx)
   reverse=o.get('backwardlogisticsum')
   if not finite(reverse):record.update(status='blocked',checks_complete=False,reason='Не подтверждены наблюдаемые обратные расходы')
   else:
    # Revalue against the newer exact seller price and MSK cost already in the source.
    cost=next((v['price']/100 for v in s['stock']if str(v.get('article','')).casefold()==r['article'].casefold()),None)
    if cost is None:record.update(status='blocked',checks_complete=False,reason='Не подтверждена адресная COGS МСК')
    else:
     margin=e['expected_margin_before_ads_cny']+e['buyout']*((r['price_cny']-e['seller_price_cny'])*(1-(e['commission_pct']+e.get('tax_pct',5))/100)-(cost-e['own_cogs_rub'])/fx)
     margin-=delivery-e['logistics_cny']+reverse/e['sample_size']/fx
     expected=margin-.05*r['price_cny']
     record.update(economics_after_5pct_cny=expected,own_buyout=[r['paid'],r['finished']],current_price_cny=r['price_cny'],stock_msk_free=r['stock'])
     reasons=list(r['requires_review']);ret=r.get('retest')or{}
     if expected<=0:record['reason']='После наблюдаемой обратной логистики сценарная экономика неположительна'
     elif any('Недавнее' in x for x in reasons):
      events=[v for v in s['experience']['experiences']if nm in(v.get('action')or{}).get('nm_ids',[]) and v.get('comparison',{}).get('evaluate_from')]
      until=max([v['comparison']['evaluate_from']for v in events],default=str(day+timedelta(days=1)))
      record.update(status='deferred',reason='Заданный эксперимент ещё не завершил своё окно оценки',eligible_after_msk=until)
     elif any('Не разобрана' in x for x in reasons):record.update(status='blocked',checks_complete=False,reason='Нужно адресное сопоставление причины прежнего финансового убытка')
     elif any('Не подтверждено улучшение' in x or 'последний полный период' in x for x in reasons):
      if ret.get('status')in('not_improved','small_sample') and ret.get('fresh_complete'):record.update(reason='Повторный тест не прошёл завершённое сравнение конверсии после исключения',retest=ret)
      else:record.update(status='blocked',checks_complete=False,reason='Недоступен точный завершённый период до/после прежнего исключения')
     elif reasons:record.update(reason='; '.join(reasons))
     elif nm not in postrows or not finite(postrows[nm].get('open_card_count')) or not finite(postrows[nm].get('funnel_orders_count')):record.update(status='blocked',checks_complete=False,reason='SKU отсутствует в полном срезе последнего завершённого дня')
     else:
      pr=postrows[nm];last_at=max([v['started_at']for v in s['experience']['experiences']if v.get('record_type')=='verified_action' and nm in(v.get('action')or{}).get('nm_ids',[]) and v.get('started_at')],default=None)
      if last_at and datetime.fromisoformat(last_at.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date()>=end:record.update(status='deferred',reason='Нет полного дня после последнего verified изменения',eligible_after_msk=str(day+timedelta(days=1)))
      else:
       r['group']='orders'if pr.get('funnel_orders_count',0)>0 else'demand'
       r=dict(r,expected_rub_per_order=round(expected*fx,2),economics_detail=dict(cogs_rub=cost,delivery_cny=delivery,fx_rub_cny=fx,observed_reverse_per_created_order_cny=reverse/e['sample_size']/fx,scenario_drr_pct=5,unknown_costs=True),final_post_change_day=dict(day=str(end),views=pr.get('open_card_count'),orders=pr.get('funnel_orders_count'),source_key=post.get('source_key')or post.get('snapshot_id')),full_checks_completed=True)
       record.update(status='ready',reason='Все необходимые доступные проверки завершены; ограниченный сценарный тест, не доказанная прибыль',last_full_day=str(end))
       groups[r['group']].append(r)
  ledger.append(record)
  if record['status']=='blocked':blocked.append(record)
 counts=dict(Counter(r['status']for r in ledger))
 review=dict(status='blocked'if blocked else'complete',job_id=req['job_id'],scope_count=len(products),ledger=ledger,counts=counts,blocked_nm_ids=[r['nm_id']for r in blocked],supplemented_logistics_nm_ids=supplements,observed_at=datetime.now(timezone.utc).isoformat(),source_observed_at=s['observed_at'],all_scope_accounted=len(ledger)==len(products),grants_action_permission=False,wb_writes=0)
 key=ROOT+str(req['job_id'])+':'+req.get('revision','initial')
 if io.get(key):io.put(key,review)
 else:io.create(key,review)
 if blocked:raise ValueError('Итоговый подбор заблокирован: '+ '; '.join(str(r['nm_id'])+': '+r['reason']for r in blocked))
 for group,rows in groups.items():
  if len({r['subject_id']for r in rows})>1:raise ValueError('Подбор охватывает разные категории; требуется раздельная группировка РК до отправки')
 return s,groups,review,key
