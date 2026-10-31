"""One dated owner-requested China ad review. Read-only WB/MS; private output only."""
import copy,json,requests,time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity
from china_analytic_dialog import reading,allowed_read
from china_moysklad_read import read_stock
ROOT='china_agent:owner_ad_review:2026-11-01:v1'
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
 c=Cache()
 if c.get(ROOT+':inputs'):return
 if datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()!='2026-11-01':raise ValueError('Dated read expired')
 w=WB();validate_identity(c,w)
 if not c.create(ROOT+':lease',dict(started_at=stamp(),wb_writes=0)):return
 state=dict(cabinet='token_3',status='collecting',observed_at=stamp(),period_from='2026-10-24',period_to='2026-10-31',errors={},wb_writes=0,telegram_sends=0,grants_action_permission=False)
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  if url.startswith(c.url) and (method.upper()=='GET' or method.upper() in ['POST','PATCH'] and str((kw.get('json')or{}).get('cache_key','')).startswith(ROOT)):return original(session,method,url,**kw)
  if allowed_read(method,url,kw.get('json')):return original(session,method,url,**kw)
  raise ValueError('Non-read request blocked')
 requests.sessions.Session.request=guard
 def save():c.put(ROOT+':checkpoint',copy.deepcopy(state))
 try:
  with reading():
   inv=w.req('/adv/v1/promotion/count');ids=sorted({a['advertId'] for g in inv.get('adverts',[]) if g.get('status') in [7,9,11] for a in g.get('advert_list',[])})
   if not 0<len(ids)<=50:raise ValueError('Campaign coverage bound')
   state['campaigns']=w.campaigns(ids);state['campaigns_at']=stamp();save()
   state['stats']=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-24&endDate=2026-10-31');state['stats_at']=stamp();state['missing_campaigns']=sorted(set(ids)-{x['advertId'] for x in state['stats']});save()
   r=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':w.token},timeout=45);r.raise_for_status();state['config']=r.json()
   if state['config'].get('currency')!='CNY':raise ValueError('Currency mismatch')
   active={int(cid):cp for cid,cp in state['campaigns'].items() if cp['status']==9};nms={n['nm_id'] for cp in active.values() for n in cp.get('nm_settings',[])}
   prices=[]
   for offset in range(0,20000,1000):
    r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params={'limit':1000,'offset':offset},headers={'Authorization':w.token},timeout=55);r.raise_for_status();part=r.json()['data']['listGoods']
    prices.extend(p for p in part if p.get('nmID') in nms)
    if len(part)<1000:break
   else:raise ValueError('Price pagination incomplete')
   state['prices']=prices;state['prices_at']=stamp();save()
   state['stock']=read_stock(sorted({p['vendorCode'] for p in prices}));save()
   candidates=[]
   for cp in state['stats']:
    cid=cp['advertId']
    if cid not in active:continue
    current={n['nm_id'] for n in active[cid]['nm_settings']};by={}
    for d in cp.get('days',[]):
     if d['date'][:10]!='2026-10-31':continue
     for a in d.get('apps',[]):
      for n in a.get('nms',[]):
       if n['nmId'] not in current:continue
       row=by.setdefault(n['nmId'],dict(spend=0,amount=0,orders=0))
       for k,f in [('spend','sum'),('amount','sum_price'),('orders','orders')]:row[k]+=n[f]
    for nm,r in by.items():
     if r['spend']>0 and (r['orders']==0 or r['amount']<=0 or r['spend']/r['amount']>.05):candidates.append(dict(cid=cid,nm=nm,**r))
   candidates.sort(key=lambda r:-r['spend']);selected=candidates[:24];state['minimums']={}
   for cid in sorted({r['cid'] for r in selected}):
    cp=active[cid];wanted=sorted({r['nm'] for r in selected if r['cid']==cid})
    for zone,on in cp['settings']['placements'].items():
     if on and zone in ['search','recommendations'] and cp['settings'].get('payment_type')=='cpc':
      try:state['minimums'][str(cid)+':'+zone]=w.minimums(cid,wanted,zone)
      except Exception as ex:state['errors']['minimum:'+str(cid)+':'+zone]=type(ex).__name__
    save()
   state['minimums_at']=stamp();state['minimum_selected']=selected
  state.update(status='complete' if not state['errors'] else 'partial',completed_at=stamp())
  if not c.create(ROOT+':inputs',state) or c.get(ROOT+':inputs')!=state:raise ValueError('Private readback mismatch')
  print(json.dumps(dict(status=state['status'],campaigns=len(state['campaigns']),price_rows=len(state['prices']),wb_writes=0,telegram_sends=0)))
 except Exception as ex:state.update(status='failed',error=type(ex).__name__);save();raise
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()

