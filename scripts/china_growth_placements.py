"""Pure full-catalogue discovery of absent search/recommendation placements."""
from datetime import date,timedelta
from zoneinfo import ZoneInfo

def addition_key(r):
 return str(r['campaign_id'])+':'+str(r['nm_id'])+':'+r.get('placement','recommendations')

def placement_candidates(source,inputs):
 from china_advertising_v2 import history,event_time
 end=date.fromisoformat(source['period_to']);blocked=set(inputs.get('excluded_nm_ids',[]))
 for change in history(source.get('executions',[])):
  if change['kind']=='excluded':blocked.add(change['nm'])
  if change['kind']in['bid','price','added','returned','relaunch'] and event_time(change['at']).astimezone(ZoneInfo('Europe/Moscow')).date()>=end:
   blocked.add(change['nm'])
 campaigns=inputs['campaigns'];occupied=set();targets=[]
 for cp in campaigns:
  for zone in ['search','recommendations']:
   if not cp['settings']['placements'].get(zone):continue
   if cp['status']in[9,11]:occupied.update((n['nm_id'],zone)for n in cp['nm_settings'])
   if cp['status']==9 and cp.get('currency')=='CNY'and cp.get('bid_type')=='manual'and cp['settings']['payment_type']=='cpc'and cp.get('restrictions',{}).get('can_change_nms')and len(cp['nm_settings'])<50:
    subjects={n['subject']['id']for n in cp['nm_settings']}
    if len(subjects)==1:targets.append((zone,next(iter(subjects)),cp['id']))
 own={int(r['nm_id']):r for r in inputs['own']['rows']};out=[]
 for nm in inputs['screened_nm_ids']:
  e=inputs['economics']['rows'].get(str(nm),{});o=own.get(nm,{})
  if nm in blocked or e.get('commission_policy_fallback')or e.get('buyout_fallback')or e.get('sample_size',0)<5:continue
  if e.get('expected_margin_before_ads_cny',-1)<=0 or e.get('stock_free',0)<=0 or not e.get('published_stock')or e['published_stock']<3:continue
  if o.get('is_payed',0)<3 or not o.get('open_card_count')or o.get('funnel_orders_count',0)/o['open_card_count']<.005:continue
  if type(o.get('subject_id'))is not int:raise ValueError('Eligible addition exact subject missing: '+str(nm))
  for zone in ['search','recommendations']:
   if (nm,zone)in occupied:continue
   choices=[cid for z,subject,cid in targets if z==zone and subject==o.get('subject_id')]
   if choices:out.append(dict(nm_id=nm,campaign_id=min(choices),placement=zone,subject_id=o['subject_id']))
 return out
