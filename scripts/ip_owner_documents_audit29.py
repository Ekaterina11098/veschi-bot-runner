"""Owner-requested IP permit audit. No WB writes, no Telegram, private outputs."""
import os,time,requests
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,stamp
ROOT='ip_agent:documents_audit:2026-10-29:v1'
def req(method,url,**kw):
 r=requests.request(method,url,headers={'Authorization':os.environ['WB_TOKEN_2'].strip()},timeout=(15,60),allow_redirects=False,**kw)
 if not r.ok:raise RuntimeError('WB read HTTP '+str(r.status_code))
 return r.json()
def main():
 if datetime.now(timezone(timedelta(hours=3))).date().isoformat()!='2026-10-29':raise RuntimeError('Expired read')
 c=Cache()
 if c.get(ROOT):return
 if not c.create(ROOT,dict(status='collecting',cabinet='token_2',observed_at=stamp(),wb_writes=0,telegram_sends=0)):return
 try:
  seller=req('GET','https://common-api.wildberries.ru/api/v1/seller-info')
  c.put(ROOT+':seller',dict(observed_at=stamp(),cabinet='token_2',data=seller))
  cur={'limit':100};seen=set();count=0;pages=0
  while True:
   j=req('POST','https://content-api.wildberries.ru/content/v2/get/cards/list',params={'locale':'ru'},json={'settings':{'sort':{'ascending':True},'cursor':cur,'filter':{'withPhoto':-1}}})
   rows=j.get('cards')
   if not isinstance(rows,list) or not isinstance(j.get('cursor'),dict):raise RuntimeError('Incomplete card response')
   for x in rows:
    nm=x.get('nmID')
    if not isinstance(nm,int) or nm in seen:raise RuntimeError('Card identity or pagination conflict')
    seen.add(nm)
   c.put(ROOT+':page:'+str(pages),dict(cards=rows,observed_at=stamp(),cursor=j['cursor'],cabinet='token_2'))
   count+=len(rows);pages+=1
   if int(j['cursor'].get('total',-1))<100:break
   if pages>=40:raise RuntimeError('Pagination bound exceeded')
   cur={k:j['cursor'][k] for k in ('updatedAt','nmID')};cur['limit']=100
   time.sleep(.7)
  c.put(ROOT,dict(status='complete',cabinet='token_2',completed_at=stamp(),pages=pages,total=count,complete=True,wb_writes=0,telegram_sends=0))
 except Exception as ex:
  c.put(ROOT,dict(status='blocked',error=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__,observed_at=stamp(),wb_writes=0,telegram_sends=0))
  raise RuntimeError('Private IP audit incomplete') from None
if __name__=='__main__':
 try:main();print('Private owner-requested read finished.')
 except Exception:print('Private read incomplete; inspect private cache.');raise SystemExit(1)
