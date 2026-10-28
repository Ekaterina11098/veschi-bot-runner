"""Owner requested China sales, intraday trend and advertising review. No marketplace mutations."""
import os,json,collections
from datetime import datetime,timezone,timedelta
import requests,time
_original_get=requests.get
def read_get(*args,**kwargs):
 for attempt in range(3):
  try:return _original_get(*args,**kwargs)
  except requests.exceptions.ConnectionError:
   if attempt==2:raise
   time.sleep(2)
requests.get=read_get
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
ROOT='china_agent:owner_sales_ads_review:2026-10-28:urgent:v1'
MSK=timezone(timedelta(hours=3))
FIELDS={'spend':'sum','amount':'sum_price','orders':'orders','clicks':'clicks','views':'views','baskets':'atbs'}
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write or method!='GET' and not(method=='POST' and path=='/api/advert/v2/budget'):raise ValueError('Review is read-only')
  return super().req(path,method,body,write=False)
def metric(d):
 return {k:d.get(v) for k,v in FIELDS.items()}
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache()
 if c.get(ROOT):print('Existing owner review; no repeated reads');return
 w=ReadWB();validate_identity(c,w);cut=datetime.now(MSK)
 out=dict(status='collecting',started_at=stamp(),cutoff_msk=cut.isoformat(),wb_writes=0,telegram_sends=0,errors=[])
 c.put(ROOT,out)
 for kind in ['orders','sales']:
  r=requests.get('https://statistics-api.wildberries.ru/api/v1/supplier/'+kind,params=dict(dateFrom='2026-10-21T00:00:00',flag=0),headers={'Authorization':w.token},timeout=80)
  if not r.ok:out['errors'].append(kind+' HTTP '+str(r.status_code));continue
  raw=r.json()
  if not isinstance(raw,list) or len(raw)>=80000:raise ValueError('Statistics scope incomplete')
  fields=['date','lastChangeDate','supplierArticle','nmId','srid','isCancel','cancelDate','priceWithDisc','finishedPrice','forPay','saleID']
  rows=[{k:x[k] for k in fields if k in x} for x in raw if '2026-10-21'<=x.get('date','')[:10]<='2026-10-28']
  c.put(ROOT+':'+kind,dict(observed_at=stamp(),rows=rows,raw_count=len(raw),fields_present=sorted({k for x in raw for k in x})))
  dedup={}
  for x in rows:
   key=x.get('srid') if kind=='orders' else x.get('saleID')
   if not key:raise ValueError('Statistics unique identity missing')
   if key not in dedup or x.get('lastChangeDate','')>dedup[key].get('lastChangeDate',''):dedup[key]=x
  summary=[]
  for day in ['2026-10-21','2026-10-22','2026-10-23','2026-10-24','2026-10-25','2026-10-26','2026-10-27','2026-10-28']:
   full=[x for x in dedup.values() if x['date'][:10]==day]
   same=[x for x in full if x['date'][11:19]<=cut.strftime('%H:%M:%S')]
   def summarize(items):
    if kind=='orders':
     active=[x for x in items if x.get('isCancel') is False]
     if any(type(x.get('isCancel')) is not bool for x in items):raise ValueError('Cancellation unknown')
     return dict(created=len(items),not_cancelled=len(active),cancelled=len(items)-len(active),created_amount_rub=sum(x['priceWithDisc'] for x in items),not_cancelled_amount_rub=sum(x['priceWithDisc'] for x in active))
    sale=[x for x in items if str(x.get('saleID','')).startswith('S')];ret=[x for x in items if str(x.get('saleID','')).startswith('R')]
    if len(sale)+len(ret)!=len(items):raise ValueError('Unknown sale/return identity')
    return dict(buyouts=len(sale),returns=len(ret),buyout_amount_rub=sum(abs(x['priceWithDisc']) for x in sale),return_amount_rub=sum(abs(x['priceWithDisc']) for x in ret))
   summary.append(dict(day=day,full=summarize(full),same_hour=summarize(same)))
  out[kind]=summary;c.put(ROOT,out)
 pr=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params=dict(limit=1000,offset=0),headers={'Authorization':w.token},timeout=60)
 if pr.ok:c.put(ROOT+':prices',dict(observed_at=stamp(),data=pr.json().get('data',{})))
 else:out['errors'].append('prices HTTP '+str(pr.status_code))
 inv=w.req('/adv/v1/promotion/count')
 ids=sorted({x['advertId'] for g in inv.get('adverts',[]) for x in g.get('advert_list',[])})
 stats=[];campaigns={};budgets=[]
 for pos in range(0,len(ids),50):
  group=ids[pos:pos+50]
  stats+=w.req('/adv/v3/fullstats?ids='+','.join(map(str,group))+'&beginDate=2026-10-21&endDate=2026-10-28')
  campaigns.update(w.campaigns(group))
  budget=w.req('/api/advert/v2/budget','POST',dict(advertIds=group))
  budgets+=budget.get('adverts',[])
 if any(x.get('currency')!='CNY' for x in budgets):raise ValueError('Budget currency mismatch')
 c.put(ROOT+':advertising',dict(observed_at=stamp(),stats=stats,campaigns=campaigns,budgets=budgets))
 byday={day:{k:0 for k in FIELDS} for day in ['2026-10-21','2026-10-22','2026-10-23','2026-10-24','2026-10-25','2026-10-26','2026-10-27','2026-10-28']}
 campaign_rows=[]
 for st in stats:
  cid=str(st['advertId']);cs=campaigns.get(cid,{})
  if cs.get('currency')!='CNY':raise ValueError('Campaign currency mismatch')
  days={}
  for d in st.get('days',[]):
   day=d['date'][:10]
   if day not in byday:continue
   m=metric(d)
   if any(v is None for v in m.values()):raise ValueError('Unknown campaign metric')
   days[day]=m
   for k in FIELDS:byday[day][k]+=m[k]
  campaign_rows.append(dict(id=cid,name=cs.get('settings',{}).get('name'),status=cs.get('status'),days=days,balance=next((x['total'] for x in budgets if str(x['advertId'])==cid),None),member_count=len(cs.get('nm_settings',[]))))
 out.update(status='complete',completed_at=stamp(),campaign_ids=ids,advertising=byday,campaigns=campaign_rows)
 c.put(ROOT,out);print(json.dumps(dict(status='complete',cutoff_msk=out['cutoff_msk'],errors=out['errors'],wb_writes=0)))
if __name__=='__main__':main()
