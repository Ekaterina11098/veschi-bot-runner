"""Bounded data broker requested by cloud Codex. Read-only China subjects; no LLM or sends."""
import hashlib,json
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
TOPICS={'catalogue','products','prices','stock','advertising','orders'}
def validate_read(value,today=None):
 today=today or datetime.now(ZoneInfo('Europe/Moscow')).date()
 if value.get('kind')!='read' or value.get('topic')not in TOPICS:raise ValueError('Unknown read topic')
 ids=value.get('nm_ids')
 if not isinstance(ids,list)or len(ids)>30 or len(set(ids))!=len(ids)or any(type(x)is not int or x<=0 for x in ids):raise ValueError('Exact bounded nm ids required')
 first=date.fromisoformat(value['date_from']);last=date.fromisoformat(value['date_to'])
 if not today-timedelta(days=90)<=first<=last<=today or (last-first).days>30:raise ValueError('Read date window outside scope')
 return {k:value[k]for k in ('kind','topic','nm_ids','date_from','date_to')}
def collect(w,job,request):
 value=validate_read(request);topic=value['topic'];ids=value['nm_ids']
 catalogue=w.catalog();known={int(n)for n,_ in catalogue}
 if any(n not in known for n in ids):raise ValueError('Requested product outside China catalogue')
 if topic=='catalogue':
  return dict(status='available',cabinet='token_3',observed_at=datetime.now(timezone.utc).isoformat(),rows=[dict(nm_id=int(n),article=a)for n,a in catalogue if not ids or int(n)in ids],wb_writes=0)
 from china_analytic_dialog import Analyst,reading
 an=Analyst(w,job,[])
 with reading():result=an.live(topic,ids,value['date_from'],value['date_to'])
 result=dict(result,wb_writes=0,requested_scope=value)
 if topic=='orders':
  # This older source supplies counts only. Do not fabricate buyer amounts.
  result['amount_coverage']='unavailable_in_this_source'
  result['note']=result.get('note','')+' Суммы заказов этот источник не содержит; для текущего samehour используй полный hourly snapshot с ОБЕИМИ базами.'
 if len(json.dumps(result,ensure_ascii=False,default=str))>100000:
  if isinstance(result.get('rows'),list):
   result=dict(result,rows=result['rows'][:50],coverage='partial_rows',source_total_rows=len(result['rows']),note=result.get('note','')+' Полный набор не помещён; пропуски не нули.')
  else:raise ValueError('Read response too large; request exact subjects')
 return result
