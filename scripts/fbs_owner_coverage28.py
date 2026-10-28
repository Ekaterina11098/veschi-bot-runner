"""Read-only source-to-document coverage inventory; operational state is never changed."""
import collections,datetime as dt,json,os,re
from fbs_document_chain import Cache,Transport,Worker,Stop,MS,WB,href,now,stamp
from fbs_ozon_api import ozon
REPORT='fbs_document_chain:owner_coverage:2026-10-28:v1'
TYPES=('customerorder','demand','salesreturn')
class ReadOnly(Transport):
 def request(self,base,path,method='GET',body=None,params=None):
  if base in (MS,WB) and method!='GET':raise Stop('Coverage audit prohibits operational writes')
  if base not in (MS,WB) and method!='GET' and (path!='telegram_api_cache' or (body or {}).get('cache_key')!=REPORT):raise Stop('Only coverage diagnostic may be saved')
  return super().request(base,path,method,body,params)
def slim(d):
 return {k:d.get(k) for k in ('id','name','moment','externalCode','description','applicable','sum','organization','customerOrder','demand')}
def coverage(cab,supply,c,ledger,docs):
 ident=supply['id'];state=ledger.get(ident);out=dict(cabinet=cab,supply_id=ident,closed_at=supply.get('closedAt'),source_name=supply.get('name'),ledger_status=(state or {}).get('status'),documents={},issues=[])
 if state and state.get('skipped_all_cancelled'):
  out['status']='skipped_all_cancelled';return out
 selected={};prefix=c.get('document_prefix','fbs-china')
 for typ in TYPES:
  ext=prefix+':'+ident+':'+typ
  candidates=[d for d in docs[typ] if d.get('externalCode')==ext]
  registered=((state or {}).get('documents') or {}).get(typ)
  if registered:
   by_id=[d for d in docs[typ] if d['id']==registered['id']]
   if len(by_id)==1 and not candidates:candidates=by_id
  if not candidates and typ=='customerorder' and ident.startswith('WB-GI-'):
   candidates=[d for d in docs[typ] if ident in re.findall(r'WB-GI-\d+',str(d.get('name',''))+' '+str(d.get('description','')))]
  if not candidates and typ=='demand' and 'customerorder' in selected:
   candidates=[d for d in docs[typ] if href(d.get('customerOrder') or {})==MS+'entity/customerorder/'+selected['customerorder']['id']]
  if not candidates and typ=='salesreturn' and 'demand' in selected:
   candidates=[d for d in docs[typ] if href(d.get('demand') or {})==MS+'entity/demand/'+selected['demand']['id']]
  out['documents'][typ]=[dict(id=d['id'],name=d.get('name'),posted=d.get('applicable'),sum=d.get('sum')) for d in candidates]
  if len(candidates)==1:
   selected[typ]=candidates[0]
   if candidates[0].get('applicable') is not True:out['issues'].append(typ+': not posted')
  elif len(candidates)>1:out['issues'].append(typ+': multiple matches')
 if len(selected)==3:
  if href(selected['demand'].get('customerOrder') or {})!=MS+'entity/customerorder/'+selected['customerorder']['id']:out['issues'].append('Demand order link mismatch')
  if href(selected['salesreturn'].get('demand') or {})!=MS+'entity/demand/'+selected['demand']['id']:out['issues'].append('Return demand link mismatch')
  out['status']='complete_documents' if not out['issues'] else 'documents_need_review'
 elif not selected:out['status']='not_matched'
 else:out['status']='partial_documents'
 if state and state.get('status')!='complete':out['issues'].append('Ledger incomplete')
 if ident=='WB-GI-298590867':out['owner_reviewed_do_not_change']=True
 return out
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise Stop('Public main only')
 t=ReadOnly();db=Cache(t);prior=db.get(REPORT)
 if prior and prior.get('status')=='complete':print('Existing completed coverage inventory');return
 report=dict(status='running',started_at=now(),operational_writes=0,source=[],results=[],errors=[])
 db.put(REPORT,report);configs={};ledgers={};source={};baselines={};tokens={cab:os.environ['WB_TOKEN_'+n] for cab,n in [('china','3'),('ip','2'),('ooo','1')]}
 try:
  for cab in ('china','ip','ooo','ozon'):
   c=db.get('fbs_document_chain:'+cab+':config:v1');base=db.get('fbs_document_chain:'+cab+':state:v1')
   if not c or not base:raise Stop('Missing configuration/baseline '+cab)
   configs[cab]=c;baselines[cab]=base
   rows=t.request(db.base,'telegram_api_cache',params={'cache_key':'like.fbs_document_chain:'+cab+':supply:v1:*','select':'payload','limit':1000})
   if len(rows)>=1000:raise Stop('Ledger inventory incomplete')
   ledgers[cab]={x['payload']['supply']['id']:x['payload'] for x in rows}
   if cab!='ozon':
    os.environ['WB_TOKEN_3']=tokens[cab];listed=Worker(t,db,c).supplies()
    closed=[x for x in listed if x.get('done') is True and x.get('closedAt')]
    source[cab]={x['id']:x for x in closed}
    report['source'].append(dict(cabinet=cab,observed_at=now(),listed=len(listed),closed=len(closed),not_closed=len(listed)-len(closed),baseline_count=len(base.get('baseline_done_ids',[])),activated_at=base['activated_at'],earliest_closed=min((x['closedAt'] for x in closed),default=None),latest_closed=max((x['closedAt'] for x in closed),default=None)))
    report.update(stage='source_'+cab,updated_at=now());db.put(REPORT,report)
  ozbase=baselines['ozon'];begin=stamp(ozbase['activated_at']).date()-dt.timedelta(days=7);end=dt.datetime.now(dt.timezone.utc).date();acts={}
  while begin<=end:
   until=min(end,begin+dt.timedelta(days=7))
   rows=ozon('/v2/posting/fbs/act/list',{'limit':50,'filter':{'date_from':str(begin),'date_to':str(until)}}).get('result')
   if not isinstance(rows,list) or len(rows)>=50:raise Stop('Ozon act pagination incomplete')
   for a in rows:acts[a['id']]=a
   begin=until+dt.timedelta(days=1)
  source['ozon']={}
  from fbs_ozon_chain import snapshot
  waiting=[]
  for act in acts.values():
   ident='OZON-ACT-'+str(act['id']);state=ledgers['ozon'].get(ident)
   if state or act.get('status')=='closed':
    source['ozon'][ident]={'id':ident,'closedAt':(state or {}).get('supply',{}).get('closedAt') or act.get('departure_date'),'name':'Ozon','act_status':act.get('status')}
   else:
    scope=snapshot(act)
    if scope['ready']:source['ozon'][ident]={'id':ident,'closedAt':scope['movement_at'],'name':'Ozon','act_status':act.get('status')}
    else:waiting.append(dict(id=ident,status=act.get('status'),included=len(scope['included']),excluded=len(scope['excluded'])))
  report['source'].append(dict(cabinet='ozon',observed_at=now(),listed_acts=len(acts),eligible_or_historical=len(source['ozon']),waiting_delivery=waiting,date_from=str(stamp(ozbase['activated_at']).date()-dt.timedelta(days=7)),date_to=str(end),activated_at=ozbase['activated_at'],baseline_count=len(ozbase.get('baseline_delivering_act_ids',[]))))
  for cab in source:
   for ident,state in ledgers[cab].items():
    if ident not in source[cab]:
     source[cab][ident]=dict(state['supply'],not_in_current_source_list=True)
  report.update(stage='moysklad_inventory',updated_at=now());db.put(REPORT,report)
  earliest=min(stamp(x['closedAt']).date() for cab in ('china','ip','ooo') for x in source[cab].values() if x.get('closedAt'))
  moment=(earliest-dt.timedelta(days=7)).strftime('%Y-%m-%d')+' 00:00:00'
  all_docs={};w=Worker(t,db,configs['china'])
  for typ in TYPES:
   all_docs[typ]=[slim(d) for d in w.ms_rows('entity/'+typ,{'filter':'moment>='+moment})]
   report.update(stage='moysklad_'+typ,updated_at=now());report.setdefault('ms_inventory',{})[typ]=len(all_docs[typ]);db.put(REPORT,report)
  report['ms_moment_from']=moment
  for cab,c in configs.items():
   org=href(c['templates']['customerorder']['organization'])
   docs={typ:[d for d in all_docs[typ] if href(d.get('organization') or {})==org] for typ in TYPES}
   base=baselines[cab];old=set(base.get('baseline_done_ids',[])) if cab!='ozon' else {'OZON-ACT-'+str(x) for x in base.get('baseline_delivering_act_ids',[])}
   for ident,supply in source[cab].items():
    row=coverage(cab,supply,c,ledgers[cab],docs)
    row['baseline_excluded']=ident in old
    row['not_in_current_source_list']=supply.get('not_in_current_source_list',False)
    row['automatic_period']=ident not in old and (ident in ledgers[cab] or (supply.get('closedAt') and stamp(supply['closedAt'])>stamp(base['activated_at'])))
    report['results'].append(row)
   report.update(stage='checked_'+cab,updated_at=now());db.put(REPORT,report)
  report['summary']=[]
  for cab in configs:
   rows=[r for r in report['results'] if r['cabinet']==cab]
   report['summary'].append(dict(cabinet=cab,total=len(rows),counts=dict(collections.Counter(r['status'] for r in rows)),automatic_counts=dict(collections.Counter(r['status'] for r in rows if r['automatic_period'])),historical_counts=dict(collections.Counter(r['status'] for r in rows if not r['automatic_period'])),ledger_chains=len(ledgers[cab]),ledger_incomplete=[r['supply_id'] for r in rows if r['ledger_status'] and r['ledger_status']!='complete']))
  report.update(status='complete',completed_at=now());db.put(REPORT,report)
  print(json.dumps(dict(status='complete',summary=report['summary'],operational_writes=0)))
 except Exception as ex:
  report.update(status='failed',error=str(ex) if isinstance(ex,Stop) else type(ex).__name__,failed_at=now());db.put(REPORT,report);raise
if __name__=='__main__':main()
