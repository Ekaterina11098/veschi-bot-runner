"""Read-only stock check for owner urgent sales diagnosis."""
import os,time,json,requests
from china_cloud_cost_control import Cache,stamp
from china_bid_proposals import fresh_stock
ROOT='china_agent:owner_sales_ads_review:2026-10-28:urgent:v1:stock'
old=requests.get
def safe_get(*a,**kw):
 for attempt in range(3):
  try:return old(*a,**kw)
  except requests.exceptions.ConnectionError:
   if attempt==2:raise
   time.sleep(2)
requests.get=safe_get
def main():
 c=Cache()
 if c.get(ROOT):return
 try:
  rows=fresh_stock({},["64-NoelBag-zchocolate","4-FurPanama-white","61-NoelBag-beige","56-NoelBag-cream","684-CelineaBag-grey","50-NoelBag-yellow","51-NoelBag-green","60-NoelBag-black"])
  c.put(ROOT,dict(status='complete',observed_at=stamp(),rows=rows,wb_writes=0,telegram_sends=0))
 except Exception as e:
  c.put(ROOT,dict(status='blocked',observed_at=stamp(),error=type(e).__name__,wb_writes=0,telegram_sends=0))
if __name__=='__main__':main()
