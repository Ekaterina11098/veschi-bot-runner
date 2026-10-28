"""Owner read-only all-source orders and buyouts for two current campaign memberships."""
import os,json
from datetime import datetime,timezone,timedelta
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
KEY='china_agent:two_zero_campaigns_all_orders:2026-10-28:1825:v1'
CIDS=[41296359,41155824]
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if method!='GET' or write:raise ValueError('Read only')
  return super().req(path,method,body,False)
def main():
 c=Cache()
 if c.get(KEY):return
 w=ReadWB();validate_identity(c,w);out=dict(status='collecting',started_at=stamp(),errors=[],wb_writes=0,telegram_sends=0)
 try:
  inv=w.req('/adv/v1/promotion/count')
  ids=sorted({a['advertId'] for g in inv.get('adverts',[]) if g.get('status') in [9,11] for a in g.get('advert_list',[])})
  if any(cid not in ids for cid in CIDS):raise ValueError('Target campaign not in active inventory')
  campaigns=w.campaigns(ids);out['campaigns']={str(cid):campaigns[str(cid)] for cid in CIDS};out['membership_at']=stamp()
  stats=[]
  for start in range(0,len(ids),50):stats+=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids[start:start+50]))+'&beginDate=2026-10-28&endDate=2026-10-28')
  out['advertising_at']=stamp();out['stats']=stats
  wanted={n['nm_id'] for cid in CIDS for n in campaigns[str(cid)]['nm_settings']}
  data={}
  for kind in ['orders','sales']:
   r=requests.get('https://statistics-api.wildberries.ru/api/v1/supplier/'+kind,params={'dateFrom':'2026-10-28T00:00:00','flag':0},headers={'Authorization':w.token},timeout=80)
   if not r.ok:
    out['errors'].append(kind+' HTTP '+str(r.status_code));data[kind]=None;continue
   rows=r.json()
   if not isinstance(rows,list) or len(rows)>=80000:raise ValueError('Statistics incomplete')
   selected=[x for x in rows if x.get('nmId') in wanted and x.get('date','')[:10]=='2026-10-28']
   fields=['date','lastChangeDate','supplierArticle','nmId','srid','isCancel','cancelDate','priceWithDisc','finishedPrice','forPay','saleID']
   data[kind]=[{k:x[k] for k in fields if k in x} for x in selected];out[kind+'_observed_at']=stamp()
   out[kind+'_raw_count']=len(rows)
  out.update(data,status='complete' if not out['errors'] else 'partial',observed_at=stamp())
 except Exception as e:out.update(status='blocked',reason=str(e) if isinstance(e,ValueError) else type(e).__name__)
 c.put(KEY,out);print(json.dumps(dict(status=out['status'],wb_writes=0)))
if __name__=='__main__':main()
