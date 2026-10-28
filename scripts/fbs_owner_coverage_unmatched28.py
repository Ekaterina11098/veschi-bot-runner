"""Read-only targeted clarification of the nine unmatched historical supplies."""
import json,os,re
from fbs_document_chain import Cache,Transport,Worker,Stop,MS,WB,href,now
from fbs_ozon_api import ozon
ROOT='fbs_document_chain:owner_coverage:2026-10-28:v1'
REPORT=ROOT+':unmatched'
class ReadOnly(Transport):
 def request(self,base,path,method='GET',body=None,params=None):
  if base in (MS,WB) and method!='GET':raise Stop('Read only')
  if base not in (MS,WB) and method!='GET' and (path!='telegram_api_cache' or body.get('cache_key')!=REPORT):raise Stop('Only diagnostic write')
  return super().request(base,path,method,body,params)
def search(t,text):
 data=t.request(MS,'entity/customerorder',params={'search':text,'limit':100,'offset':0})
 size=data.get('meta',{}).get('size')
 if not isinstance(size,int) or size>500:raise Stop('Search broad or incomplete')
 rows=data['rows']
 while len(rows)<size:
  batch=t.request(MS,'entity/customerorder',params={'search':text,'limit':100,'offset':len(rows)}).get('rows',[])
  if not batch:raise Stop('Search incomplete')
  rows+=batch
 return rows
def slim(d):
 return dict(id=d['id'],name=d.get('name'),organization=href(d.get('organization') or {}),posted=d.get('applicable'),externalCode=d.get('externalCode'),comment=d.get('description'))
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise Stop('Public main only')
 t=ReadOnly();db=Cache(t);root=db.get(ROOT)
 if not root or root.get('status')!='complete':raise Stop('Full inventory incomplete')
 if db.get(REPORT):print('Existing clarification');return
 report=dict(status='running',started_at=now(),results=[],operational_writes=0)
 tokens={cab:os.environ['WB_TOKEN_'+n] for cab,n in [('ip','2'),('ooo','1')]}
 unknown=[r for r in root['results'] if r['status']=='not_matched']
 for row in unknown:
  if row['cabinet']=='ozon':continue
  out=dict(cabinet=row['cabinet'],supply_id=row['supply_id'],closed_at=row['closed_at'])
  try:
   os.environ['WB_TOKEN_3']=tokens[row['cabinet']]
   ids=t.request(WB,'api/marketplace/v3/supplies/'+row['supply_id']+'/order-ids').get('orderIds')
   if not isinstance(ids,list):raise Stop('Order IDs incomplete')
   out['current_order_count']=len(ids)
   out['global_order_search']=[slim(d) for d in search(t,row['supply_id'])]
  except Exception as e:out['error']=str(e) if isinstance(e,Stop) else type(e).__name__
  report['results'].append(out);db.put(REPORT,report)
 acts=ozon('/v2/posting/fbs/act/list',{'limit':50,'filter':{'date_from':'2026-10-13','date_to':'2026-10-20'}}).get('result')
 if not isinstance(acts,list) or len(acts)>=50:raise Stop('Historical act list incomplete')
 amap={'OZON-ACT-'+str(a['id']):a for a in acts}
 orders=search(t,'Озон')
 for row in unknown:
  if row['cabinet']!='ozon':continue
  out=dict(cabinet='ozon',supply_id=row['supply_id'])
  try:
   act=amap[row['supply_id']];out.update(departure_date=act.get('departure_date'),created_at=act.get('created_at'),act_status=act.get('status'))
   postings=ozon('/v2/posting/fbs/act/get-postings',{'id':act['id']}).get('result')
   if not isinstance(postings,list):raise Stop('Act posting list incomplete')
   wanted={p['posting_number'] for p in postings}
   out.update(posting_count=len(wanted),quantity=sum(p['quantity'] for rowp in postings for p in rowp.get('products',[])))
   out['candidates']=[]
   for d in orders:
    present=set(re.findall(r'\d{4,}-\d+-\d+',str(d.get('description',''))))
    if present & wanted:out['candidates'].append(dict(slim(d),matched_postings=len(present & wanted),other_postings=len(present-wanted),missing_postings=len(wanted-present)))
   if not out['candidates'] and wanted:
    out['first_posting_search']=[slim(d) for d in search(t,sorted(wanted)[0])]
  except Exception as e:out['error']=str(e) if isinstance(e,Stop) else type(e).__name__
  report['results'].append(out);db.put(REPORT,report)
 report.update(status='complete',completed_at=now());db.put(REPORT,report);print(json.dumps({'status':'complete','checked':len(report['results'])}))
if __name__=='__main__':main()
