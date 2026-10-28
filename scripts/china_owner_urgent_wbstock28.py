"""WB FBS inventory read only for eight exact declining cards; no stock update endpoint."""
import requests,time
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
KEY='china_agent:owner_sales_ads_review:2026-10-28:urgent:v1:wb_stock'
ARTS=["64-NoelBag-zchocolate","4-FurPanama-white","61-NoelBag-beige","56-NoelBag-cream","684-CelineaBag-grey","50-NoelBag-yellow","51-NoelBag-green","60-NoelBag-black"]
def main():
 c=Cache()
 if c.get(KEY):return
 w=WB();validate_identity(c,w)
 h={'Authorization':w.token};out=dict(status='collecting',observed_at=stamp(),rows=[],wb_writes=0,errors=[])
 try:
  pr=c.get('china_agent:owner_sales_ads_review:2026-10-28:urgent:v1:prices') or {}
  goods=pr.get('data',{}).get('listGoods',[])
  wanted=[p for p in goods if p.get('vendorCode') in ARTS]
  sizes={z['sizeID']:dict(article=p['vendorCode'],nm=p['nmID']) for p in wanted for z in p.get('sizes',[])}
  if len(wanted)!=len(ARTS) or not sizes:raise ValueError('Current price size identity incomplete')
  r=requests.get('https://marketplace-api.wildberries.ru/api/v3/warehouses',headers=h,timeout=45)
  if not r.ok:raise ValueError('WB warehouses HTTP '+str(r.status_code))
  warehouses=r.json()
  if not isinstance(warehouses,list) or len(warehouses)>20:raise ValueError('Warehouse scope unexpected')
  out['warehouses']=warehouses
  for wh in warehouses:
   r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/'+str(wh['id']),headers=h,json={'chrtIds':list(sizes)},timeout=45)
   if not r.ok:out['errors'].append('WB stocks HTTP '+str(r.status_code)+' warehouse '+str(wh['id']));continue
   out['rows']+=[dict(sizes.get(v['chrtId'],{}),warehouse_id=wh['id'],**v) for v in r.json().get('stocks',[])]
   time.sleep(.3)
  out['status']='complete' if not out['errors'] else 'partial'
 except Exception as e:out.update(status='blocked',reason=str(e) if isinstance(e,ValueError) else type(e).__name__)
 out['completed_at']=stamp();c.put(KEY,out)
if __name__=='__main__':main()
