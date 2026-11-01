"""One-off owner requested completed-day campaign read. No marketplace mutations or sends."""
import os,json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_completed_campaign_read:2026-11-02:v1'
def main():
 c=Cache();scope=c.get(ROOT+':scope')or{}
 if scope.get('read_authorized')is not True or scope.get('cabinet')!='token_3' or datetime.now(timezone.utc)>=datetime.fromisoformat(scope['expires_at']):raise ValueError('Read scope expired')
 if c.get(ROOT+':result'):print('Existing source, no repeated collection');return
 if not c.create(ROOT+':lease',dict(at=stamp())):return
 w=WB();validate_identity(c,w)
 original=w.req
 def only_read(path,method='GET',body=None,write=False):
  if write:raise PermissionError('WB mutations forbidden')
  return original(path,method,body,write=False)
 w.req=only_read
 result=dict(status='collecting',cabinet='token_3',observed_at=stamp(),wb_writes=0,telegram_calls=0,grants_action_permission=False,errors={})
 from china_advertising_state import AdvertisingIO
 from china_moysklad_read import read_stock
 class Prices(AdvertisingIO):
  def __init__(self,token):self.token=token
 try:
  cid=scope['campaign_id'];ids=scope['nm_ids']
  result['campaign']=w.campaigns([cid])[str(cid)]
  if {n['nm_id']for n in result['campaign']['nm_settings']}!=set(ids):raise ValueError('Composition changed; review required')
  result['statistics']=w.req('/adv/v3/fullstats?ids='+str(cid)+'&beginDate='+scope['date_from']+'&endDate='+scope['date_to'])
  result['stats_at']=stamp();result['prices']=Prices(w.token).prices(ids)
  result['stock']=read_stock(scope['articles'])
  result['minimums']=w.minimums(cid,ids,'recommendations')
  result['status']='complete'
 except Exception as ex:
  result['status']='partial';result['errors']['collector']=str(ex)if isinstance(ex,(ValueError,RuntimeError,PermissionError))else type(ex).__name__
 result['completed_at']=stamp();c.put(ROOT+':result',json.loads(json.dumps(result)))
 print(json.dumps({k:result[k]for k in ['status','wb_writes','telegram_calls','errors']}))
if __name__=='__main__':main()

