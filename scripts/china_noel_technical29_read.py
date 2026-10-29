"""Read only current CNY bid minimums for Noel campaign members, no stock access."""
import os,time,json
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
ROOT='china_agent:noel_intraday:2026-10-29:v1'
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write or method!='GET' and not(method=='POST' and path=='/api/advert/v1/bids/min'):raise ValueError('Read only')
  return super().req(path,method,body,False)
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()=='2026-10-29'
 c=Cache();w=ReadWB();validate_identity(c,w);key=ROOT+':minimums'
 if c.get(key):print('Existing technical result');return
 for _ in range(20):
  root=c.get(ROOT) or {}
  if root.get('status') in ('complete','partial'):break
  time.sleep(3)
 else:raise ValueError('Base read not ready')
 prices=c.get(ROOT+':prices') or {}; names={int(x['nmID']):x['vendorCode'] for x in prices.get('rows',[]) if 'noelbag' in x.get('vendorCode','').lower()}
 cfg=c.get(ROOT+':campaigns') or {};rows=[];errors=[]
 for cid,ad in cfg.get('campaigns',{}).items():
  if ad.get('status')!=9:continue
  items=[n for n in ad.get('nm_settings',[]) if n['nm_id'] in names]
  if not items:continue
  for placement,enabled in ad.get('settings',{}).get('placements',{}).items():
   if not enabled:continue
   try:
    mins=w.minimums(cid,[n['nm_id'] for n in items],placement)
    for n in items:rows.append(dict(cid=int(cid),nm=n['nm_id'],article=names[n['nm_id']],placement=placement,bid=n['bids_kopecks'][placement],minimum=mins[n['nm_id']],restrictions=ad.get('restrictions'),observed_at=stamp()))
   except Exception as ex:errors.append(dict(cid=cid,placement=placement,error=type(ex).__name__))
 result=dict(status='complete' if not errors else 'partial',observed_at=stamp(),rows=rows,errors=errors,wb_writes=0,stock_reads=0)
 c.put(key,result);print('Noel technical read saved privately')
if __name__=='__main__':main()
