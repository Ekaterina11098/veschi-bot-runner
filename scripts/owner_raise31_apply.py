"""Exact owner-approved two bid raises and stated two one-time reserves; no Telegram."""
import os,copy,json,time,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,projection,stamp
ROOT='china_agent:owner_raise31:v1'
def direct(w,path,method='GET',body=None):
 if method=='GET' and path not in ['/api/advert/v1/config','/adv/v1/balance']:raise ValueError('Read scope')
 if method=='POST' and (path not in ['/adv/v1/budget/deposit?id=40933588','/adv/v1/budget/deposit?id=41298169'] or body.get('sum')!={40933588:2400,41298169:600}[int(path.split('=')[-1])] or body.get('type')not in[0,1]):raise ValueError('Deposit scope')
 r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':w.token},json=body,timeout=50)
 if not r.ok:raise RuntimeError('WB HTTP '+str(r.status_code))
 return r.json()if r.content else {}
def cash(w,cid):
 rows=w.req('/api/advert/v2/budget','POST',{'advertIds':[cid]})['adverts']
 if len(rows)!=1 or rows[0]['advertId']!=cid or rows[0]['currency']!='CNY':raise ValueError('Budget identity')
 return rows[0]['total']
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Publicmainonly')
 c=Cache();w=WB();a=c.get(ROOT+':approval')or{}
 if a.get('status')!='approved' or a.get('owner_user_id')!=5122667182 or a.get('source_channel')!='codex' or datetime.now(timezone.utc)>datetime.fromisoformat(a['expires_at']):raise ValueError('Owner approval missing/expired')
 items=a['approved_items']
 if [(i['campaign_id'],i['nm_id'],i['placement'],i['old_minor'],i['target_minor'],i['amount_cny'])for i in items]!=[(40933588,1473243904,'recommendations',28,31,2400),(41298169,1473244337,'search',28,31,600)]:raise ValueError('Exact scopechanged')
 prior=c.get(ROOT+':execution')
 if prior:print(json.dumps({'status':prior['status'],'existing':True}));return
 validate_identity(c,w)
 e=dict(status='running',created_at=stamp(),items=[],wb_writes=0,budget_writes=0,price_writes=0,telegram_calls=0,approval_key=ROOT+':approval')
 if not c.create(ROOT+':execution',e):raise ValueError('Executionrace')
 def save():c.put(ROOT+':execution',copy.deepcopy(e))
 cfg=direct(w,'/api/advert/v1/config')
 for i in items:
  st=dict(item=i,status='preflight');e['items'].append(st);save()
  try:
   before=w.campaigns([i['campaign_id']])[str(i['campaign_id'])];st['before']=before
   n=next(n for n in before['nm_settings']if n['nm_id']==i['nm_id'])
   if before['status']!=9 or before['currency']!='CNY' or before['bid_type']!='manual' or before['settings']['payment_type']!='cpc' or sorted(n['nm_id']for n in before['nm_settings'])!=i['baseline_nm_ids']:raise ValueError('Campaign changed')
   if n['bids_kopecks'][i['placement']]!=i['old_minor']:raise ValueError('Bid changed; no compounded repeat')
   mins=w.minimums(i['campaign_id'],[i['nm_id']],i['placement'])
   if cfg.get('currency')!='CNY' or type(cfg.get('cpcStep'))is not int or cfg['cpcStep']<=0 or i['target_minor']%cfg['cpcStep'] or mins[i['nm_id']]>i['target_minor'] or i['target_minor']>cfg['cpcMaxBid']:raise ValueError('Limitschanged')
   pr=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params={'limit':1000,'offset':0},headers={'Authorization':w.token},timeout=45);pr.raise_for_status()
   goods=pr.json()['data']['listGoods'];g=next(g for g in goods if g['nmID']==i['nm_id'])
   if g['currencyIsoCode4217']!='CNY' or {s['discountedPrice']for s in g['sizes']}!={i['price']}:raise ValueError('Pricechanged')
   size=[s['sizeID']for s in g['sizes']]
   rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':w.token},json={'chrtIds':size},timeout=40);rr.raise_for_status()
   stock=rr.json()['stocks']
   if {s['chrtId']for s in stock}!=set(size) or sum(s['amount']for s in stock)<=0:raise ValueError('Published stock unavailable')
   st.update(minimum=mins[i['nm_id']],published_stock=sum(s['amount']for s in stock),price=g['sizes'][0]['discountedPrice'])
   st['baseline_fullstats']=w.req('/adv/v3/fullstats?ids='+str(i['campaign_id'])+'&beginDate=2026-10-31&endDate=2026-10-31')
   body={'bids':[{'advert_id':i['campaign_id'],'nm_bids':[{'nm_id':i['nm_id'],'placement':i['placement'],'bid_kopecks':31}]}]}
   st.update(status='submitting',submitted_at=stamp(),request={'method':'PATCH','path':'/api/advert/v1/bids','body':body});save()
   try:response=w.req('/api/advert/v1/bids','PATCH',body,True)
   except Exception:st['status']='uncertain';save();raise
   st.update(status='accepted',response=response);e['wb_writes']+=1;save()
   expected=copy.deepcopy(before);next(n for n in expected['nm_settings']if n['nm_id']==i['nm_id'])['bids_kopecks'][i['placement']]=31
   after=w.campaigns([i['campaign_id']])[str(i['campaign_id'])];st['after']=after
   if projection(after)!=projection(expected):raise ValueError('Full readback mismatch; no repeat')
   st.update(status='verified',verified_at=stamp());save()
   child=ROOT+':'+str(i['campaign_id'])+':execution'
   val=dict(status='verified',before=before,after=after,items=[i],submitted_at=st['submitted_at'],verified_at=st['verified_at'],baseline_fullstats=st['baseline_fullstats'],parent=ROOT+':execution')
   if not c.create(child,val):raise ValueError('Canonicalreceiptalreadyexists')
   reg=c.get('china_agent:verified_campaign_state:v1')or{};reg[str(i['campaign_id'])]=child;c.put('china_agent:verified_campaign_state:v1',reg)
  except Exception as ex:
   st.update(status='uncertain'if st['status']in['submitting','accepted','uncertain']else'blocked',reason=type(ex).__name__+(': '+str(ex)if isinstance(ex,(ValueError,RuntimeError))else''));save()
   continue
  fund=dict(status='preflight',amount_cny=i['amount_cny']);st['funding']=fund;save()
  try:
   b=cash(w,i['campaign_id']);fund['before_budget']=b
   if b>i['balance_before']+2:raise ValueError('Funded since analysis; refresh instead of duplicate')
   if cfg['minTopUp']>i['amount_cny']*100:raise ValueError('Minimumtopupchanged')
   bal=direct(w,'/adv/v1/balance')
   if bal.get('currency')!='CNY':raise ValueError('Balancecurrency')
   source=0 if bal.get('balance',0)>=i['amount_cny']else 1 if bal.get('net',0)>=i['amount_cny']else None
   if source is None:raise ValueError('Insufficient available CNY')
   fund.update(status='submitting',submitted_at=stamp());save()
   try:result=direct(w,'/adv/v1/budget/deposit?id='+str(i['campaign_id']),'POST',{'sum':i['amount_cny'],'type':source})
   except Exception:fund['status']='uncertain';save();raise
   fund.update(status='accepted',response=result);e['budget_writes']+=1;save()
   b2=cash(w,i['campaign_id']);fund['after_budget']=b2
   if b2<b+i['amount_cny']-2:raise ValueError('Funding readback mismatch; no repeat')
   fund.update(status='verified',verified_at=stamp());save()
   fkey=ROOT+':'+str(i['campaign_id'])+':funding'
   c.create(fkey,dict(status='verified',kind='budget_topup',campaign_id=i['campaign_id'],cid=i['campaign_id'],amount_cny=i['amount_cny'],before_budget=b,after_budget=b2,steps={'deposit':dict(status='verified',path='/adv/v1/budget/deposit?id='+str(i['campaign_id']),body={'sum':i['amount_cny'],'type':source},submitted_at=fund['submitted_at'])},verified_at=fund['verified_at'],parent=ROOT+':execution'))
  except Exception as ex:
   fund.update(status='uncertain'if fund['status']in['submitting','accepted','uncertain']else'blocked',reason=type(ex).__name__+(': '+str(ex)if isinstance(ex,(ValueError,RuntimeError))else''));save()
 e.update(status='verified'if all(x['status']=='verified'and x.get('funding',{}).get('status')=='verified'for x in e['items'])else'partial',completed_at=stamp());save()
 print(json.dumps({'status':e['status'],'bid_writes':e['wb_writes'],'budget_writes':e['budget_writes'],'telegram_calls':0}))
if __name__=='__main__':run()
