"""Read actual advertising spend19-25Oct for owner weekly profit only."""
import os,json
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
ROOT='china_agent:weekly_profit:2001087979:ads:v1'
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write or method!='GET':raise ValueError('Read only')
  return super().req(path,method,body,False)
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()=='2026-10-29'
 c=Cache();w=ReadWB();validate_identity(c,w)
 if c.get(ROOT):print('Existing result; no repeated collection');return
 inv=w.req('/adv/v1/promotion/count')
 ids=sorted({x['advertId'] for g in inv.get('adverts',[]) for x in g.get('advert_list',[])})
 rows=[]
 for pos in range(0,len(ids),50):
  rows+=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids[pos:pos+50]))+'&beginDate=2026-10-19&endDate=2026-10-25')
 daily={};out=[]
 for st in rows:
  days=[]
  for d in st.get('days',[]):
   if d.get('sum') is None:raise ValueError('Missing spend')
   day=d['date'][:10]
   if not '2026-10-19'<=day<='2026-10-25':raise ValueError('Wrong period')
   daily[day]=round(daily.get(day,0)+d['sum'],2)
   days.append(dict(day=day,spend=d['sum']))
  out.append(dict(id=st['advertId'],days=days))
 if len(daily)!=7:raise ValueError('Incomplete days')
 result=dict(status='complete',observed_at=stamp(),period_from='2026-10-19',period_to='2026-10-25',cabinet='token_3',currency='CNY',ids=ids,rows=out,daily=daily,total=round(sum(daily.values()),2),missing_stats_ids=[x for x in ids if x not in {s['advertId'] for s in rows}],wb_writes=0,telegram_sends=0)
 c.put(ROOT,result);print('Weekly advertising read stored privately')
if __name__=='__main__':main()
