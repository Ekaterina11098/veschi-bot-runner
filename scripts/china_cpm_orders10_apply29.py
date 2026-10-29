"""Owner authorized second CPM candidate inputs. Read only. No Telegram."""
import os,json,requests
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
from china_advertising_state import AdvertisingIO
class PriceRead(AdvertisingIO):
 def __init__(self):self.token=os.environ['WB_TOKEN_3']
 def tg(self,*args,**kwargs):raise ValueError('No Telegram')
ROOT="china_agent:owner_cpm_orders10_apply29:2026-10-29:v1"
def main():
 assert os.environ.get('GITHUB_REPOSITORY')=='Ekaterina11098/veschi-bot-runner' and os.environ.get('GITHUB_REF')=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()=='2026-10-29'
 c=Cache();w=WB();validate_identity(c,w)
 assert c.create(ROOT+':read2:guard',dict(at=stamp())),'Read already claimed'
 cfg=c.get(ROOT+':selection');assert cfg
 ids=sorted({a['advertId'] for g in w.req('/adv/v1/promotion/count').get('adverts',[]) for a in g.get('advert_list',[])})
 camps=w.campaigns(ids)
 c.put(ROOT+':before',dict(status='captured',observed_at=stamp(),campaigns=camps))
 prices=PriceRead().prices([int(x['nm']) for x in cfg['candidates']])
 assert len(prices)==len(cfg['candidates']) and all(x['currencyIsoCode4217']=='CNY' for x in prices.values())
 c.put(ROOT+':prices',dict(observed_at=stamp(),rows=list(prices.values())))
 headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'}
 def get(path,params):
  r=requests.get('https://api.moysklad.ru/api/remap/1.2'+path,params=params,headers=headers,timeout=65)
  assert r.ok,'MS stock read HTTP '+str(r.status_code)
  return r.json()
 stores=get('/entity/store',dict(limit=1000))
 assert stores['meta']['size']<=len(stores['rows'])
 chosen=[x for x in stores['rows'] if x.get('name')=='МСК' and not x.get('archived')]
 assert len(chosen)==1
 articles={x['article'] for x in cfg['candidates']};rows=[];offset=0
 while True:
  j=get('/report/stock/all',dict(filter='store='+chosen[0]['meta']['href']+';stockMode=all;quantityMode=all',limit=1000,offset=offset))
  part=j['rows'];size=j['meta']['size'];assert isinstance(size,int)
  rows.extend({k:x.get(k) for k in ['article','stock','reserve','price']} for x in part if x.get('article') in articles)
  offset+=len(part)
  if offset>=size:break
  assert part and offset<50000
 c.put(ROOT+':stock',dict(observed_at=stamp(),warehouse='МСК',complete=True,raw_count=offset,rows=rows))
 c.put(ROOT+':inputs',dict(status='complete',observed_at=stamp(),WBwrites=0,TelegramSends=0))
 print('Private candidate stock, price, and campaign inputs complete')
if __name__=='__main__':main()
