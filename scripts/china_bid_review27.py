"""Owner-requested current candidate review; no marketplace writes or Telegram transport."""
import copy,json,os
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,WB,validate_identity
from china_price_apply import IO
KEY='china_agent:bid_proposal_check_now:2026-10-27:v1'
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:raise PermissionError('Read-only review')
  return super().req(path,method,body,write=False)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 cache=Cache()
 if cache.get(KEY):print('Review already collected; no polling');return
 wb=ReadWB();validate_identity(cache,wb)
 inv=wb.req('/adv/v1/promotion/count')
 ids=sorted({x['advertId'] for g in inv.get('adverts',[]) if g.get('status')==9 for x in g.get('advert_list',[])})
 if not ids or len(ids)>50:raise ValueError('Campaign scope unexpected')
 cs=wb.campaigns(ids);stats=wb.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-24&endDate=2026-10-27')
 io=IO();prices=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
 if len(prices)>=1000:raise ValueError('Price catalogue truncated')
 headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN']};base='https://api.moysklad.ru/api/remap/1.2'
 r=requests.get(base+'/entity/store',headers=headers,params={'limit':1000},timeout=45)
 if not r.ok:raise RuntimeError('MSK store unavailable')
 stores=[s for s in r.json().get('rows',[]) if s.get('name')=='МСК' and not s.get('archived')]
 if len(stores)!=1:raise ValueError('MSK store ambiguous')
 stock=[];offset=0
 while True:
  r=requests.get(base+'/report/stock/all',headers=headers,params={'filter':'store='+stores[0]['meta']['href'],'stockMode':'all','limit':1000,'offset':offset},timeout=50)
  if not r.ok:raise RuntimeError('MSK stock unavailable')
  d=r.json();part=d.get('rows',[]);stock += [{k:s.get(k) for k in ['article','stock','reserve','price']} for s in part]
  if offset+len(part)>=d.get('meta',{}).get('size',offset+len(part)):break
  if not part or offset>=5000:raise ValueError('MSK stock truncated')
  offset+=len(part)
 model=cache.get('china_agent:new_ad_source:v1:2026-10-27') or {}
 if not model.get('products'):raise ValueError('Own completed buyout source absent')
 out=dict(status='complete',observed_at=datetime.now(timezone.utc).isoformat(),campaigns=cs,stats=stats,prices=prices,stock=stock,products=model['products'],policy=model['policy'],economics_observed_at=model['observed_at'],registry=cache.get('china_agent:verified_campaign_state:v1') or {},wb_writes=0,telegram_calls=0)
 if not cache.create(KEY,out):raise ValueError('Concurrent review')
 print(json.dumps(dict(status='complete',campaigns=len(ids),products=len(model['products']),wb_writes=0,telegram_calls=0)))
if __name__=='__main__':run()
