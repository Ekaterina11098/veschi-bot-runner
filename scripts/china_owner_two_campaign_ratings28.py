"""Read-only review-rating screen; retain aggregates only, no review text or buyer identities."""
import requests,time,collections
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
KEY='china_agent:two_campaign_rating_review:2026-10-28:v1'
def main():
 c=Cache()
 if c.get(KEY):return
 w=WB();validate_identity(c,w);out=dict(status='collecting',observed_at=stamp(),wb_writes=0,telegram_sends=0,errors=[])
 try:
  previous=c.get('china_agent:two_zero_campaigns_all_orders:2026-10-28:1825:v1') or {}
  ids={n['nm_id'] for cp in previous.get('campaigns',{}).values() for n in cp['nm_settings']}
  source=c.get('china_agent:new_ad_source:v1:2026-10-28') or {};pm={p['nm_id']:p for p in source['products'] if p['nm_id'] in ids}
  if len(pm)!=36:raise ValueError('Exact target identity missing')
  ratings=collections.defaultdict(dict);sources=[];complete=True
  for answered in ['true','false']:
   r=requests.get('https://feedbacks-api.wildberries.ru/api/v1/feedbacks',params={'isAnswered':answered,'take':5000,'skip':0,'order':'dateDesc'},headers={'Authorization':w.token},timeout=60)
   if not r.ok:out['errors'].append('Feedbacks '+answered+' HTTP '+str(r.status_code));complete=False;break
   j=r.json()
   if j.get('error'):raise ValueError('Feedbacks returned error')
   data=j.get('data',{});rows=data.get('feedbacks')
   if not isinstance(rows,list):raise ValueError('Feedback rows missing')
   sources.append(dict(answered=answered,received=len(rows),truncated=len(rows)>=5000))
   if len(rows)>=5000:complete=False
   for row in rows:
    nm=(row.get('productDetails') or {}).get('nmId');stars=row.get('productValuation')
    if nm in ids and type(stars) in [int,float] and 1<=stars<=5:ratings[nm][row['id']]=stars
   time.sleep(.5)
  result=[]
  for nm,p in pm.items():
   rr=list(ratings[nm].values());avg=sum(rr)/len(rr) if rr else None
   historical=p.get('commentsvaluation')
   result.append(dict(nm_id=nm,article=p['sa_name'],historical_rating=historical if isinstance(historical,(int,float)) and historical>0 else None,historical_period_to=source.get('period_to'),review_count=len(rr) if complete else None,received_review_count=len(rr),received_review_average=round(avg,3) if avg is not None else None,
    review_scope='seller feedback list answered+unanswered; archive/card grouping may differ',displayed_card_rating_verified=False,screen='low_received_rating' if avg is not None and avg<4.5 else 'few_reviews' if rr and len(rr)<5 else 'received_rating_pass' if rr else 'rating_unconfirmed'))
  out.update(status='complete' if complete else 'partial',rows=result,sources=sources,observed_at=stamp())
 except Exception as e:out.update(status='blocked',reason=str(e) if isinstance(e,(ValueError,RuntimeError)) else type(e).__name__)
 c.put(KEY,out);print(out['status'])
if __name__=='__main__':main()
