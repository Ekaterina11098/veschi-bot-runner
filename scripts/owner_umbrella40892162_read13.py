"""Read only three umbrella products and their existing campaigns. No sends or mutations."""
import json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
from china_advertising_state import AdvertisingIO
from china_morning_readiness import current_prices,published_stock
from china_moysklad_read import read_stock
def main():
 io=AdvertisingIO();c=Cache();w=WB();validate_identity(c,w)
 ids=[1556488181,1556488209,1556488210]
 inv=w.req('/adv/v1/promotion/count')
 cids=sorted({a['advertId']for g in inv.get('adverts',[])if g['status']in[4,9,11]for a in g.get('advert_list',[])})
 assert len(cids)<=50
 allcp=w.campaigns(cids)
 cp={cid:row for cid,row in allcp.items()if any(n['nm_id']in ids for n in row['nm_settings'])}
 prices=current_prices(io,ids);stock=read_stock([r['article']for r in prices['rows']]);pub=published_stock(io,prices,ids)
 minimum=w.minimums(40892162,ids,'search')
 budgets=w.req('/api/advert/v2/budget','POST',dict(advertIds=[int(cid)for cid in cp]))
 value=dict(observed_at=datetime.now(timezone.utc).isoformat(),campaigns=cp,prices=prices,stock=stock,published_stock=pub,minimum=minimum,budgets=budgets,wb_writes=0,telegram_calls=0,model_calls=0)
 c.put('china_agent:owner_umbrella40892162:2026-11-13:v1:current',value)
 print(json.dumps(dict(status='readback_saved',campaigns=list(cp),minimum=minimum,wb_writes=0)))
if __name__=='__main__':main()
