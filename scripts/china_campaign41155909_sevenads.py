import os,json
from china_price_apply import IO
from analytics.mpstats_probe import discover,sanitize
io=IO()
r=discover(os.environ['MPSTATS_API_TOKEN'])
keep=[x for x in r.get('tools',[]) if x['name'] in ['wbbidder_clusters','wbbidder_campaign_stats','wb_sku','lk_wb_card_info','lk_wb_card_widget','lk_wb_card_orders']]
io.create('china_agent:seven_ad_diagnosis:2026-10-21:catalog:v1',dict(status=r['status'],tools=sanitize(keep),wb_writes=0,telegram_calls=0))
print('Readonly diagnostic metadata retained')
