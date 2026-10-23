"""Bounded, resumable China-only reads for missing daily advertising sources."""
import json,os
from contextlib import contextmanager
from datetime import datetime,timezone
from urllib.parse import urlparse
_SCOPE=None
@contextmanager
def read_scope(days):
 global _SCOPE
 old=_SCOPE;_SCOPE={'days':set(days),'campaigns':set()}
 try:yield _SCOPE
 finally:_SCOPE=old
def allowed_read(method,url,body):
 if _SCOPE is None or method.upper()!='POST' or urlparse(url)._replace(query='',fragment='').geturl()!='https://mcp.mpstats.io/mcp' or not isinstance(body,dict):return False
 rpc=body.get('method');p=body.get('params') or {}
 if rpc in ('initialize','notifications/initialized','tools/list'):return True
 if rpc!='tools/call':return False
 name=p.get('name');a=p.get('arguments') or {}
 if name in ('account_limits','wbbidder_cabinets'):return not a
 if name=='lk_wb_cabinets':return a=={'action':'list'}
 if name=='wbbidder_campaigns':
  return a.get('tokens')==[939742] and a.get('report')=='state' and set(a)<={'tokens','report','limit','start_row','bidder_only','sort','sort_dir'}
 if name=='wbbidder_campaign':return set(a)=={'campaign_id'} and a['campaign_id'] in _SCOPE['campaigns']
 if name=='wbbidder_campaign_stats':
  return set(a)=={'campaign_id','report','d1','d2'} and a['campaign_id'] in _SCOPE['campaigns'] and a['report']=='products' and a['d1']==a['d2'] and a['d1'] in _SCOPE['days']
 return False
def collect(worker,days):
 from analytics.mpstats_probe import discover
 from analytics.mpstats_gaps import execute_reads
 from analytics.mpstats_recovery import BIDDER
 if not days:return
 key='china_agent:ad_cost_collection:'+days[0]+':'+days[-1]+':v1'
 state=worker.get(key) or dict(status='collecting',cabinet='token_3',days=days,observations=[],wb_writes=0,telegram_calls=0)
 if state.get('days')!=days:raise ValueError('Collection dates changed')
 def persist(cabinet,obs):
  state['observations']=[x for x in state['observations'] if x.get('request_key')!=obs['request_key']]
  state['observations'].append(dict(cabinet=cabinet,**obs));worker.save(key,state)
 def req(tool,args):
  return dict(cabinet='token_3',tool=tool,arguments=args,key='ad-cost:'+tool+':'+json.dumps(args,sort_keys=True))
 with read_scope(days) as scope:
  def reader(call,checks,known):
   mapping=dict(token_3=dict(BIDDER['token_3'],campaign_ids=[]))
   def run(requests):
    received={o['request_key'] for o in state['observations'] if o.get('status')=='received'}
    return execute_reads(call,checks,known,[r for r in requests if r['key'] not in received],mapping,persist,max_requests=120)
   run([dict(cabinet='shared',tool='wbbidder_cabinets',arguments={},key='ad-cost:cabinets')])
   cabs=next(o for o in state['observations'] if o['tool']=='wbbidder_cabinets')
   if cabs.get('status')!='received':raise ValueError('Кабинет рекламы не получен')
   identity=[c for c in cabs['data'].get('data',[]) if c.get('id')==939742]
   if len(identity)!=1 or identity[0].get('info',{}).get('currency')!='CNY':raise ValueError('Кабинет Китая не подтверждён')
   state['identity']=identity[0]
   run([req('wbbidder_campaigns',dict(tokens=[939742],report='state',limit=100,start_row=0,bidder_only=False,sort='wb_id',sort_dir='asc'))])
   cat=next(o for o in state['observations'] if o['tool']=='wbbidder_campaigns')
   body=cat['data'];rows=body.get('data',[])
   if cat.get('status')!='received' or body.get('total')!=len(rows) or body.get('returned')!=len(rows):raise ValueError('Неполный каталог РК')
   ids=sorted({c['id'] for c in rows});scope['campaigns']=set(ids);mapping['token_3']['campaign_ids']=ids
   tasks=[req('wbbidder_campaign',dict(campaign_id=cid)) for cid in ids]
   tasks += [req('wbbidder_campaign_stats',dict(campaign_id=cid,report='products',d1=day,d2=day)) for day in days for cid in ids]
   run(tasks)
   for day in days:
    selected=[o for o in state['observations'] if o['tool'] in ('wbbidder_campaigns','wbbidder_campaign') or (o['tool']=='wbbidder_campaign_stats' and o['arguments']['d1']==day)]
    complete=len(selected)==1+2*len(ids) and all(o.get('status')=='received' and o.get('scope_verified') is True for o in selected)
    if not complete:continue
    for o in selected:
     if o['tool']!='wbbidder_campaign_stats':continue
     b=o['data']
     if b.get('period')!={'from':day,'to':day} or b.get('returned')!=len(b.get('data',[])) or ('total' in b and b['total']!=len(b.get('data',[]))):raise ValueError('Неполная пагинация SKU за '+day)
    source=dict(status='complete',cabinet='token_3',identity=identity[0],observed_at=datetime.now(timezone.utc).isoformat(),source_kind='ad_cost_products_only',observations=selected,wb_writes=0)
    worker.save('china_agent:ad_cost_source:'+day+':v1',source)
   return {'requests':len(tasks),'wb_writes':0}
  result=discover(os.environ.get('MPSTATS_API_TOKEN',''),read_checks=True,extra_reader=reader)
 state['last_result']=result.get('status');state['updated_at']=datetime.now(timezone.utc).isoformat();worker.save(key,state)
 if not result.get('connected'):raise ValueError('MPStats: '+str(result.get('status'))+'; недостающие дни '+', '.join(days))
