"""Read-only, exact WB subject identity for growth screening; never infer from article."""
import time,requests
from datetime import datetime,timezone
def ensure_subjects(io,v):
 # Without any own sales/funnel rows, no SKU can pass the existing addition sample gate.
 if not v.get('own',{}).get('rows'):return v
 if v.get('subjects',{}).get('status')=='complete':
  subjects=v['subjects']['by_nm']
 else:
  cursor={'limit':100};subjects={};seen=set()
  for _ in range(50):
   time.sleep(.7)
   r=requests.post('https://content-api.wildberries.ru/content/v2/get/cards/list',headers={'Authorization':io.token},json={'settings':{'cursor':cursor,'filter':{'withPhoto':-1}}},timeout=40)
   if not r.ok:raise ValueError('Growth subject catalogue HTTP '+str(r.status_code))
   j=r.json();cards=j.get('cards');c=j.get('cursor')
   if not isinstance(cards,list)or not isinstance(c,dict):raise ValueError('Growth subject page unknown')
   for card in cards:
    nm=card.get('nmID');subject=card.get('subjectID')
    if type(nm)is not int or type(subject)is not int or subject<=0:raise ValueError('Exact card subject missing')
    if str(nm)in subjects and subjects[str(nm)]!=subject:raise ValueError('Conflicting subject identity')
    subjects[str(nm)]=subject
   if c.get('total',100)<100:break
   marker=(c.get('updatedAt'),c.get('nmID'))
   if None in marker or marker in seen:raise ValueError('Subject cursor incomplete')
   seen.add(marker);cursor={'limit':100,'updatedAt':marker[0],'nmID':marker[1]}
  else:raise ValueError('Subject pagination bound')
  v['subjects']={'status':'complete','by_nm':subjects,'observed_at':datetime.now(timezone.utc).isoformat(),'source':'content/v2/get/cards/list','wb_writes':0}
 for row in v['own']['rows']:
  subject=subjects.get(str(row['nm_id']))
  if subject is not None:row['subject_id']=subject
 return v
