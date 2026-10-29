"""Compact factual campaign cards. Receipts establish exclusions, not recommendations."""
from datetime import datetime
from china_advertising_v2 import history,price_map,daily_metrics,sums,ratio,MSK
ZERO=dict(spend=0,amount=0,orders=0,views=0,clicks=0)
def money(x):return f'{x:,.2f}'.replace(',',' ').replace('.',',')
def enhance(bundle,source):
 labels=price_map(source['catalogue']);changes=history(source.get('executions',[]))
 intraday=source.get('intraday') or {};today_raw={r['advertId']:r for b in intraday.get('ad_batches',[]) for r in b.get('data',[])}
 today_date=bundle['day']
 raw={r['advertId']:r for b in source['batches'].values() for r in b['stats']}
 campaigns={c['id']:c for b in source['batches'].values() for c in b['campaigns'].get('adverts',[])}
 for c in bundle['campaigns']:
  current=campaigns[c['id']];members={n['nm_id'] for n in current.get('nm_settings',[])}
  bynm={}
  for day in raw.get(c['id'],{}).get('days',[]):
   if day['date'][:10] not in bundle['days']:continue
   for app in day.get('apps',[]):
    for n in app.get('nms',[]):
     nm=n['nmId'];v=bynm.setdefault(nm,dict(ZERO))
     for k,x in daily_metrics(n).items():v[k]+=x
  # Keep the latest verified event for an article and check current membership.
  exclusions={}
  for x in changes:
   if x['cid']!=c['id'] or x['kind']!='excluded' or x['nm'] in members:continue
   local=datetime.fromisoformat(x['at'].replace('Z','+00:00')).astimezone(MSK)
   if local.date().isoformat()<bundle['days'][0]:continue
   exclusions[x['nm']]=dict(nm=x['nm'],article=labels.get(x['nm'],{}).get('article','WB '+str(x['nm'])),at=x['at'],date=local.strftime('%d.%m'))
  active=sums(bynm.get(nm,ZERO) for nm in members) if not c['missing_stats'] else None
  maximum=max((v['spend'] for nm,v in bynm.items() if nm in members),default=0)
  today=next((daily_metrics(d) for d in today_raw.get(c['id'],{}).get('days',[]) if d['date'][:10]==today_date),None)
  c.update(never_started=current.get('status')==4 and current.get('timestamps',{}).get('started') is None, today=today,yesterday=c.get('last'),today_observed_at=intraday.get('observed_at'),confirmed_exclusions=list(exclusions.values()),current_period=active,max_member_spend=maximum,
           member_count=len(members),current_articles=[dict(nm=nm,article=labels.get(nm,{}).get('article','WB '+str(nm))) for nm in sorted(members)],facts_checked=True)
  # Only concrete new actions appear as individual SKU rows. Waiting/old actions stay out.
  c['attention']=[r for r in c['focus'] if r.get('action') and r['nm'] in members]
  if c.get('budget_action',{} ) and c['budget_action']['kind']=='pause_campaign':
   c['budget_action']=None;c['budget_recommendation']='Не пополнять. РК остаётся активной: пауза не согласована.'
  c['notes']=notes(c)
 bundle['presentation']='three_day_attention_table_v4'
 bundle['today_observed_at']=intraday.get('observed_at')
 bundle['total_yesterday_spend']=sum(c['last']['spend'] for c in bundle['campaigns'] if c.get('last') is not None) if all(c.get('last') is not None or c['status']!=9 for c in bundle['campaigns']) else None
 bundle['receipt_basis']='verified before/after diff and current campaign membership'
 from china_budget_reserve import apply
 return apply(bundle,(source.get('config') or {}).get('minTopUp',10000)/100)

def notes(c):
 if c.get('missing_stats'):return ['Статистика WB за период отсутствует; расход и ДРР не подтверждены.']
 if c['status']!=9:return ['РК не активна. Изменений не нужно.']
 out=[];high=c.get('drr') is not None and c['drr']>5
 ex=c.get('confirmed_exclusions',[])
 if ex and (high or c.get('attention')):
  listed='; '.join(x['article']+' ('+x['date']+')' for x in ex[:3])
  if len(ex)>3:listed+='; ещё '+str(len(ex)-3)+' SKU'
  out.append('Уже исключены: '+listed+'. ДРР включает прежний расход.')
 if c.get('attention'):return out
 if high:
  p=c.get('current_period')
  if p is None:return out+['Данные текущих артикулов не подтверждены; новые действия не сформированы.']
  names=', '.join(x['article'] for x in c.get('current_articles',[])) if c['member_count']<=3 else str(c['member_count'])+' SKU'
  out.append('Оставить '+names+': расход '+money(p['spend'])+' ¥; прямых рекламных заказов '+str(int(p['orders']))+'.')
  focus=[r for r in c.get('focus',[]) if r.get('reason') and not r.get('action')]
  if focus:
   out.append(focus[0]['article']+': '+focus[0]['decision']+' '+focus[0]['reason'])
  elif c.get('new_composition'):
   out.append('Первый полный день нового состава ещё не завершён. Максимум расхода одного SKU — '+money(c.get('max_member_spend',0))+' ¥.')
  elif p['orders']==0:
   out.append('Максимум расхода одного SKU — '+money(c.get('max_member_spend',0))+' ¥; подтверждённого сигнала для нового исключения нет.')
  elif ratio(c.get('last')) is not None and ratio(c['last'])<=5:
   out.append('За последний полный день ДРР '+money(ratio(c['last']))+'%, в пределах цели. Новых изменений не нужно.')
  else:
   out.append('По текущим SKU '+str(int(p['orders']))+' прямых заказов; ДРР прямой атрибуции '+(money(ratio(p))+'%' if ratio(p) is not None else 'не определена')+'. Данные после изменений ещё оцениваются.')
 return out or ['Изменений не нужно.']
