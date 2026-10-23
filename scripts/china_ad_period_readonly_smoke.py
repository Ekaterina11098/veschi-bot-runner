import os,json,sys
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
sys.path[:0]=['scripts','source']
from conversion_watches import runtime,saved_network_guard
from china_three_day_ads import load,build
from china_ad_cost_png import render,suggestion
from china_ad_rule import reads,minimums,items_for,campaign_rows
from china_loss_ads import current
from china_price_apply import IO
w=runtime();today=w.now.astimezone(ZoneInfo('Europe/Moscow')).date()
with saved_network_guard():
 labels=dict(w.catalog());results={};sources3=None;report3=None
 for count in (3,5):
  sources=load(w,count);report=build(sources,today,labels,count)
  growing=[r for r in report['rows'] if r['rising_all_days']]
  images=render(report,{r['nm']:suggestion(r,sources[-1],today) for r in growing})
  results[str(count)]=dict(days=report['days'],sku_count=len(report['rows']),attention_count=len(growing),png_parts=len(images),png_valid=all(b.startswith(b'\x89PNG') for b in images))
  if count==3:sources3=sources;report3=report
 rows=[r for r in campaign_rows(sources3,labels) if r['drr'] is not None and r['drr']>=6]
 with reads() as scope:
  io=IO();campaigns=current(io);scope.update({cid:{n['nm_id'] for n in c.get('nm_settings',[])} for cid,c in campaigns.items()});mins={}
  for cid,c in campaigns.items():
   ids={int(r['nm']) for r in rows if r['campaign_id']==cid and 6<=r['drr']<=10}&scope[cid]
   if ids and c.get('currency')=='CNY' and c.get('settings',{}).get('payment_type')=='cpc':
    mins.update({(cid,nm):value for nm,value in minimums(io,cid,ids).items()})
  plan_items=items_for(rows,campaigns,mins)
 result=dict(status='verified_readonly',date=str(today),periods=results,ad_plan_items=plan_items,ad_plan_counts={kind:sum(i['kind']==kind for i in plan_items) for kind in ('ad_set_bid','ad_exclude_sku','needs_data')},wb_writes=0,telegram_calls=0,observed_at=w.now.isoformat())
 w.save('china_agent:ad_period_readonly_smoke:'+str(today)+':v1',result)
print(json.dumps({k:v for k,v in result.items() if k!='ad_plan_items'},ensure_ascii=False))
