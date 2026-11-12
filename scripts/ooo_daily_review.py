"""Deterministic review of every catalogue row; proposals only, no provider calls."""
import collections,datetime,json
def review(a,e,day):
 yesterday=(datetime.date.fromisoformat(day)-datetime.timedelta(days=1)).isoformat()
 period=[(datetime.date.fromisoformat(day)-datetime.timedelta(days=i)).isoformat()for i in (3,2,1)]
 dates={str(c['advertId']):{d['date'][:10]for d in c['days']}for c in e['sources']['advertising14']['data']}
 missing={cid:[d for d in period if d not in dates.get(cid,set())]for cid in a['configurations']};missing={k:v for k,v in missing.items()if v}
 actions=[];checks=[];funding=[]
 for r in a['rows']:
  own=(r['funnel14']or{}).get('statistic',{}).get('selected',{})
  p=collections.Counter()
  for m in r['members']:p.update((m['ads']or{}).get('three',{}))
  knownstock=isinstance(r['free_msk'],(int,float)) and r['free_msk']>0 and (r['stock_wb']or{}).get('wb',0)>0
  checks.append({'nm':r['nm'],'article':r['article'],'all_members_three':dict(p),'own_orders':own.get('orderCount'),'buyouts':own.get('buyoutCount'),'cancels':own.get('cancelCount'),'stock_wb':r['stock_wb'],'stock_msk':r['free_msk'],'mature_cohort':r['cohort'],'scenario_lower_before_ads_rub':r['model_lower_before_ads_rub'],'overlapping_campaigns':[m['cid']for m in r['members']],'growth_review':'Sparse direct attribution or mixed placement cannot establish a ready raise/add; stock and mature before-ad scenario checked, no profit assertion.'})
  for m in r['members']:
   if m['status']!=9 or m['cid']in(41517533,39605582)or not knownstock:continue
   # Only a single serving placement gives an unambiguous bid target.
   placements=[k for k,v in m['placements'].items()if v]
   if len(placements)!=1:continue
   placement=placements[0];bid=m['bids'].get(placement);minimum=270 if m['cid']==39605579 and placement=='recommendations'else 325
   v=(m['ads']or{}).get('three',{});last=(m['ads']or{}).get('day',{})
   if type(bid)is int and bid>minimum and v.get('clicks',0)>=30 and v.get('sum',0)>=100 and v.get('orders',0)==0 and last.get('orders',0)==0 and last.get('sum',0)>0:
    actions.append({'kind':'reduce_bid','cid':m['cid'],'nm':r['nm'],'article':r['article'],'placement':placement,'from_minor':bid,'to_minor':minimum})
 for cid,cfg in a['configurations'].items():
  if cfg['status']!=9 or cid in missing or int(cid)in(41517533,39605582):continue
  c=a['campaigns'][cid];last=c['day'];three=c['three'];balance=a['budgets'][cid]
  drr=lambda x:x['sum']/x['sum_price']*100 if x.get('sum_price',0)>0 else None
  positive=[r for r in a['rows']if any(m['cid']==int(cid)for m in r['members'])and(r['model_lower_before_ads_rub']or 0)>0 and(r['free_msk']or 0)>0 and(r['stock_wb']or{}).get('wb',0)>0]
  if last.get('sum',0)>balance and drr(last)is not None and drr(three)is not None and max(drr(last),drr(three))<=5 and positive:
   funding.append({'cid':int(cid),'amount_kgs':1200 if last['sum']-balance<=1200 else int((last['sum']-balance+99)//100*100)})
 assert len(checks)==351
 return {'status':'reviewed_proposals_only','actions':actions,'funding':funding,'budgets':a['budgets'],'internal_analysis':{'catalogue':351,'sku_checks':checks,'missing_required_day':missing,'sources_at':a['sources_at'],'historical_coverage':e.get('advertising_coverage'),'rules':'No zero fill. DRR native campaign first; no averages. No automatic pause/exclusion from no orders. Bid reductions only unambiguous serving placement above cached minimum. No raise/add without robust placement evidence. Funding only actual one-day cash shortfall with native day/3d DRR<=5 and positive dated RUB-before-ad stock scenario; minimum1200 not authorization. No actual profit or FX conversion claimed. Recent minimum-bid changes never reissued.','economics':'RUB scenario before advertising only, mature cohort date explicit, no confirmed KGS/RUB FX or actual profit claim. Associated orders not proof of direct SKU efficacy.','wb_writes':0,'model_calls':0}}