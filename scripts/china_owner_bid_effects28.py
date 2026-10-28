"""Read-only effects of four explicitly verified owner bid changes."""
import os,json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
KEY='china_agent:owner_bid_effects:2026-10-28:1715:v1'
ITEMS=[(40933588,1473244337,'177-AngelaBag-brown','china_agent:owner_growth_apply28:2026-10-28:v1:execution'),(40933588,1473244340,'447-AngelaBag-burgundy','china_agent:owner_growth_apply28:2026-10-28:v1:execution'),(40933588,1473245494,'143-ReginaBag-black','china_agent:owner_growth_apply28:2026-10-28:v1:execution'),(41325622,1535337780,'17-FurPanama-leo','china_agent:owner_panama17_apply28:2026-10-28:v3:execution')]
FIELDS=['sum','views','clicks','atbs','orders','sum_price']
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if method!='GET' or write:raise ValueError('Read-only diagnosis')
  return super().req(path,method,body,False)
def extract(stats,cid,nm):
 st=next((s for s in stats if s['advertId']==cid),None)
 if not st:return dict(status='missing_campaign',metrics=None)
 d=next((d for d in st.get('days',[]) if d['date'][:10]=='2026-10-28'),None)
 if not d:return dict(status='missing_day',metrics=None)
 rows=[n for a in d.get('apps',[]) for n in a.get('nms',[]) if n['nmId']==nm]
 if not rows or any(r.get(k) is None for r in rows for k in FIELDS):return dict(status='missing_sku_or_metrics',metrics=None)
 return dict(status='reported',metrics={k:sum(r[k] for r in rows) for k in FIELDS})
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache()
 if c.get(KEY):return
 w=ReadWB();validate_identity(c,w)
 out=dict(status='collecting',observed_at=stamp(),items=[],wb_writes=0,telegram_sends=0)
 try:
  current=w.req('/adv/v3/fullstats?ids=40933588,41325622&beginDate=2026-10-28&endDate=2026-10-28')
  camps=w.campaigns([40933588,41325622]);out['stats_observed_at']=stamp()
  middle=(c.get('china_agent:owner_sales_ads_review:2026-10-28:urgent:v1:advertising') or {})
  for cid,nm,article,key in ITEMS:
   receipt=c.get(key) or {}
   if receipt.get('status')!='verified':raise ValueError('Canonical execution not verified')
   before=extract(receipt.get('baseline_fullstats',[]),cid,nm);now=extract(current,cid,nm);mid=extract(middle.get('stats',[]),cid,nm)
   delta={k:round(now['metrics'][k]-before['metrics'][k],4) for k in FIELDS} if now['metrics'] is not None and before['metrics'] is not None else None
   late={k:round(now['metrics'][k]-mid['metrics'][k],4) for k in FIELDS} if now['metrics'] is not None and mid['metrics'] is not None else None
   ns=next((n for n in camps[str(cid)]['nm_settings'] if n['nm_id']==nm),None)
   out['items'].append(dict(article=article,nm_id=nm,campaign_id=cid,verified_at=receipt['verified_at'],before=before,current=now,delta_since_change=delta,at1646=mid,delta_since1646=late,current_bids=ns.get('bids_kopecks') if ns else None,member_present=ns is not None,canonical=key))
  out.update(status='complete',observed_at=stamp(),attribution_note='Intraday cumulative readback deltas include delayed attribution/revisions; no causal proof or full-day decision.')
 except Exception as e:out.update(status='blocked',reason=str(e) if isinstance(e,ValueError) else type(e).__name__)
 c.put(KEY,out);print(json.dumps(dict(status=out['status'],wb_writes=0,telegram_sends=0)))
if __name__=='__main__':main()
