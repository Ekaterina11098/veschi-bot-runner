"""Owner-requested current report from verified shared snapshots; no network collection."""
import copy,json
from datetime import datetime,timedelta,date,timezone
from china_advertising_v2 import build,ratio,price_map,MSK
def prepare(io,day):
 base=io.get('china_agent:advertising_source:'+day+':v2')
 fresh=io.get('china_agent:advertising_intraday:'+day+':v1')
 if not fresh:
  previous=str(date.fromisoformat(day)-timedelta(days=1))
  fresh=io.get('china_agent:owner_profit_compare:'+previous+':'+day+':v1')
 if not base:raise ValueError('Нет общего каталога РК и датированной базы цен; нужен адресный сбор')
 # Reuse an existing same-day snapshot before any WB call.
 if not fresh or (datetime.now(timezone.utc)-datetime.fromisoformat(fresh['observed_at'].replace('Z','+00:00'))).total_seconds()>3600:
  from china_advertising_v2 import http,save,stamp
  ids=base['ids'];batches=[];fresh_settings=[];fresh_budgets=[]
  for pos in range(0,len(ids),50):
   batch=ids[pos:pos+50];joined=','.join(map(str,batch))
   fresh_settings+=http(io,'/api/advert/v2/adverts?ids='+joined)['adverts']
   fresh_budgets+=http(io,'/api/advert/v2/budget','POST',dict(advertIds=batch))['adverts']
   batches.append(dict(data=http(io,'/adv/v3/fullstats?ids='+joined+'&beginDate='+str(date.fromisoformat(day)-timedelta(days=2))+'&endDate='+day)))
  fresh=dict(observed_at=stamp(),ad_batches=batches,campaigns=fresh_settings,budgets=fresh_budgets)
  save(io,'china_agent:advertising_intraday:'+day+':v1',fresh)
 observed=datetime.fromisoformat(fresh['observed_at'].replace('Z','+00:00'))
 if observed.astimezone(MSK).date().isoformat()!=day:raise ValueError('Сохранённый срез относится к другому дню')
 s=copy.deepcopy(base);s['period_to']=day;s['observed_at']=fresh['observed_at']
 campaigns={c['id']:c for b in s['batches'].values() for c in b['campaigns']['adverts']}
 if fresh.get('campaigns'):campaigns={c['id']:c for c in fresh['campaigns']}
 raw={c['advertId']:copy.deepcopy(c) for b in s['batches'].values() for c in b['stats']}
 for b in fresh['ad_batches']:
  for c in b['data']:
   prev=raw.setdefault(c['advertId'],copy.deepcopy(c));ds={d['date'][:10]:d for d in prev['days']}
   ds.update({d['date'][:10]:d for d in c['days']});prev['days']=[ds[d] for d in sorted(ds)]
 ex=io.get('china_agent:codex_search_exclude553:2026-10-25:v1:execution') or {}
 if ex.get('status')=='verified' and ex.get('after'):campaigns[41298169]=ex['after']
 budgets=fresh.get('budgets') or [x for b in s['batches'].values() for x in b['budgets']['adverts']]
 s['batches']={'0':dict(campaigns=dict(adverts=list(campaigns.values())),stats=list(raw.values()),budgets=dict(adverts=budgets))}
 b=build(s);b['day']=day;b['intraday']=True
 cut=observed.astimezone(MSK).strftime('%d.%m %H:%M МСК')
 budget_at=datetime.fromisoformat((fresh if fresh.get('budgets') else base)['observed_at'].replace('Z','+00:00')).astimezone(MSK).strftime('%d.%m %H:%M МСК')
 b['period_label']='Текущий срез '+cut+'; последний день неполный'
 b['budget_label']='Расходы: '+cut+'; остатки: '+budget_at
 b['view_only']=True
 # Intraday recommendations are review-only and never become executable plans.
 for c in b['campaigns']:
  for r in c['focus']:r['action']=None
  c['budget_action']=None;c['forecast']=None;c['coverage']=None
  c['budget_recommendation']='Остаток на '+budget_at+'. Автопополнение не предлагается по неполному дню.'
  if c['last'] and ratio(c['last']) is not None and ratio(c['last'])>5:c['budget_recommendation']+=' ДРР сегодня выше5%; сначала оценить SKU.'
  if not c.get('new_composition'):continue
  cp=raw.get(c['id']);members={n['nm_id'] for n in campaigns[c['id']]['nm_settings']};totals={}
  for d in (cp or {}).get('days',[]):
   if d['date'][:10]!=day:continue
   for a in d['apps']:
    for n in a['nms']:
     t=totals.setdefault(n['nmId'],dict(spend=0,amount=0,orders=0,views=0,clicks=0,carts=0))
     for x,k in [('spend','sum'),('amount','sum_price'),('orders','orders'),('views','views'),('clicks','clicks'),('carts','atbs')]:t[x]+=n.get(k,0)
  labels=price_map(s['catalogue'])
  existing={r['nm'] for r in c['focus']}
  for nm,t in totals.items():
   if nm not in members or nm in existing:continue
   price=labels.get(nm,{}).get('price');drr=ratio(t)
   if not ((drr is not None and drr>5) or (not t['orders'] and price and t['spend']>=price*.05)):continue
   zero=dict(spend=0,amount=0,orders=0,views=0,clicks=0);daily=[dict(zero),dict(zero),t]
   if cp:
    for i,d in enumerate(b['days'][:2]):
     for dayrow in cp.get('days',[]):
      if dayrow['date'][:10]!=d:continue
      for a in dayrow['apps']:
       for n in a['nms']:
        if n['nmId']==nm:
         for x,k in [('spend','sum'),('amount','sum_price'),('orders','orders'),('views','views'),('clicks','clicks')]:daily[i][x]+=n.get(k,0)
   period={k:sum(z[k] for z in daily) for k in zero}
   c['focus'].append(dict(nm=nm,article=labels.get(nm,{}).get('article','WB '+str(nm)),daily=daily,period=period,period_drr=ratio(period),done='Сегодня запущен/расширен тест',decision='Проверить исключение; только после отдельного подтверждения.',reason=f"Сегодня расход {t['spend']:.2f} ¥; {t['clicks']} кликов; {t['carts']} корзин; {t['orders']} рекламных заказов. Ранний сигнал, не доказанный убыток.",action=None))
 return b
