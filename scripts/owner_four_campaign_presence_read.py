"""Dated owner-requested campaign membership and bid read. No external mutations."""
import json,requests
from datetime import datetime,timezone,date
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_143_campaign_results:2026-11-01:v1'
def main():
 c=Cache();request=c.get(ROOT+':request')
 if not request or request.get('cabinet')!='token_3' or request.get('read_only') is not True:raise ValueError('Private request required')
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1) or datetime.now(timezone.utc)>=datetime.fromisoformat(request['expires_at']):raise ValueError('Expired read')
 if c.get(ROOT+':result'):return
 ids=request['nm_ids']
 if not 1<=len(ids)<=10 or len(set(ids))!=len(ids) or any(type(n)is not int for n in ids):raise ValueError('Exact SKU scope')
 if not c.create(ROOT+':lease',dict(started_at=stamp(),wb_writes=0)):return
 original=requests.sessions.Session.request
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper()
  state=u.scheme=='https' and u.hostname==urlparse(c.url).hostname and u.path.startswith('/rest/v1/') and (m=='GET' or m=='POST' and u.path=='/rest/v1/telegram_api_cache')
  read=u.scheme=='https' and u.hostname=='advert-api.wildberries.ru' and m=='GET' and u.path in ['/adv/v1/promotion/count','/api/advert/v2/adverts','/adv/v3/fullstats']
  if not(state or read):raise PermissionError('Read-only scope')
  return original(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  wb=WB();validate_identity(c,wb)
  inventory=wb.req('/adv/v1/promotion/count')
  all_ids=sorted({r['advertId'] for group in inventory.get('adverts',[]) if group['status']!=-1 for r in group.get('advert_list',[])})
  if not all_ids or len(all_ids)>1000:raise ValueError('Campaign inventory unavailable')
  campaigns={}
  for offset in range(0,len(all_ids),50):campaigns.update(wb.campaigns(all_ids[offset:offset+50]))
  rows=[]
  for campaign in campaigns.values():
   matched=[n for n in campaign.get('nm_settings',[])if n['nm_id']in ids]
   if matched and campaign.get('currency')!='CNY':raise ValueError('Unexpected currency')
   for item in matched:
    rows.append(dict(nm_id=item['nm_id'],article=request['articles'][str(item['nm_id'])],campaign_id=campaign['id'],status=campaign['status'],bid_type=campaign.get('bid_type'),currency=campaign['currency'],settings=campaign['settings'],bids_minor=item.get('bids_kopecks'),campaign_updated=campaign.get('timestamps',{}).get('updated')))
  stats=[]
  for offset in range(0,len(all_ids),50):
   part=wb.req('/adv/v3/fullstats?ids='+','.join(map(str,all_ids[offset:offset+50]))+'&beginDate=2026-10-31&endDate=2026-11-01')
   if not isinstance(part,list):raise ValueError('Statistics unavailable')
   stats.extend(part)
  result=dict(statistics=stats,missing_stat_campaign_ids=sorted(set(all_ids)-{x['advertId']for x in stats}),status='complete',cabinet='token_3',started_at=c.get(ROOT+':lease')['started_at'],observed_at=stamp(),requested_nm_ids=ids,campaign_count=len(all_ids),inventory=inventory,campaigns=campaigns,rows=rows,wb_writes=0,telegram_calls=0,grants_action_permission=False)
  if not c.create(ROOT+':result',result) or c.get(ROOT+':result')!=result:raise ValueError('Private readback mismatch')
  print(json.dumps(dict(status='complete',campaigns=len(all_ids),matched_rows=len(rows),wb_writes=0,telegram_calls=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()
