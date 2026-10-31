"""Read current campaign cash after verified eight actions. No WB writes or Telegram calls."""
import os,json,requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:job194_recovery:2026-10-31:v1'
PID='daily-2026-10-31-owner-agreed8-v1-drr-0'
def run():
 c=Cache();e=c.get('china_agent:daily_ad_execution:v2:'+PID)or{}
 if len(e.get('items',[]))!=8 or any(s.get('status')!='verified'for s in e['items']):raise ValueError('Eight actions not all WBverified')
 if c.get(ROOT+':post_budget_snapshot'):return
 w=WB();validate_identity(c,w)
 inv=w.req('/adv/v1/promotion/count');ids=sorted({x['advertId']for g in inv.get('adverts',[])if g['status']==9 for x in g.get('advert_list',[])})
 campaigns=w.campaigns(ids);budgets=w.req('/api/advert/v2/budget','POST',{'advertIds':ids})
 if {x['advertId']for x in budgets['adverts']}!=set(ids) or any(x.get('currency')!='CNY'for x in budgets['adverts']):raise ValueError('Cash scope/currency incomplete')
 cfg=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':w.token},timeout=40)
 if not cfg.ok:raise ValueError('Config read HTTP '+str(cfg.status_code))
 config=cfg.json()
 if config.get('currency')!='CNY':raise ValueError('Configuration currency mismatch')
 snapshot=dict(status='complete',observed_at=stamp(),campaigns=campaigns,budgets=budgets,config=config,all_eight_verified=True,source_execution='china_agent:daily_ad_execution:v2:'+PID,wb_budget_writes=0,wb_writes=0,telegram_calls=0)
 if not c.create(ROOT+':post_budget_snapshot',snapshot):raise ValueError('Snapshot race')
 print(json.dumps({'status':'complete','campaigns':len(ids),'wb_writes':0,'telegram_calls':0}))
if __name__=='__main__':run()
