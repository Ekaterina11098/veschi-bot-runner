"""OOO report-only worker. No model credentials or mutation endpoints."""
import os,json,datetime,re,runpy,tempfile,base64,hashlib
from pathlib import Path
from china_codex_cloud import DB,stamp
from ooo_daily_review import review
MSK=datetime.timezone(datetime.timedelta(hours=3))
def execute(code,path):
 path.write_text(code,encoding='utf-8');return runpy.run_path(str(path),run_name='__main__')
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'))
def worker(slot,day=None,verify=False):
 db=DB();day=day or datetime.datetime.now(MSK).date().isoformat();date=datetime.date.fromisoformat(day)
 root='ooo_agent:'+('morning:'+day if slot=='morning' else 'midday:'+day+':1500')
 delivery=db.get(root+':telegram:execution')or{}
 if delivery and not verify:return {'status':'already_'+delivery.get('status','attempted'),'root':root}
 policy=db.get('ooo_agent:daily_reports:v1:policy')or{}
 if policy.get('enabled')is not True:raise PermissionError('Report delivery policy disabled')
 assets=json.loads((Path(__file__).parent/'ooo_report_templates.json').read_text(encoding='utf-8'))
 with tempfile.TemporaryDirectory()as temp:
  R=Path(temp);(R/'work/china_logic_review').mkdir(parents=True);(R/'outputs').mkdir()
  for name in ['china_advertising_v2_png.py','china_advertising_directions.py','china_advertising_midday.py']:(R/'work/china_logic_review'/name).write_text(assets[name],encoding='utf-8')
  def dated(code,base,offsets):
   mapping={k:(date+datetime.timedelta(days=v)).isoformat()for k,v in offsets.items()}
   return re.sub('|'.join(map(re.escape,mapping)),lambda m:mapping[m.group()],code)
  collector=dated(assets['collector'],'2026-11-12',{'2026-11-12':0,'2026-11-11':-1,'2026-11-09':-3,'2026-10-29':-14,'2026-10-15':-28,'2026-10-28':-15})
  # Resume only unfinished read stages; returned evidence and completed stages are immutable.
  collector=collector.replace("if db.get(KEY):print('Existing dated collector/evidence retained');return","prior_state=db.get(KEY)\n if prior_state and prior_state.get('status')=='finished':return")
  collector=collector.replace("db.once(KEY,state)","state=prior_state or state\n if not prior_state:db.once(KEY,state)")
  collector=collector.replace("def read(label,fn):\n  try:","def read(label,fn):\n  if state['sources'].get(label,{}).get('status')=='complete':return\n  try:")
  collector=collector.replace("not set(IDS)<={r['advertId']for r in rows}or ","")
  key='ooo_agent:morning:'+day+':evidence'
  if slot=='morning' and not verify:execute(collector,R/'work/collector.py')
  evidence=db.get(key)or{}
  if evidence.get('status')!='finished' or any(v.get('status')!='complete'for v in evidence.get('sources',{}).values()):raise RuntimeError('Incomplete morning sources; retained for same worker recovery')
  (R/'work/ooo_morning_20261111.json').write_text(json.dumps(evidence),encoding='utf-8')
  model=db.get('ooo_agent:daily_reports:v1:model')or{}
  (R/'work/ooo_full_plan_model.json').write_text(json.dumps(model),encoding='utf-8')
  analyzer=dated(assets['analyzer'],'2026-11-11',{'2026-11-11':0,'2026-11-10':-1,'2026-11-08':-3})
  execute(analyzer,R/'work/analyzer.py');a=json.loads((R/'work/ooo_morning11_analysis.json').read_text(encoding='utf-8'))
  for cid in a['configurations']:a['campaigns'].setdefault(cid,{p:{}for p in ['day','three','fourteen','today']})
  z=review(a,evidence,day)
  (R/'work/ooo_morning12_analysis.json').write_text(json.dumps(a),encoding='utf-8');(R/'work/ooo_morning12_review.json').write_text(json.dumps(z),encoding='utf-8')
  if slot=='morning':
   renderer=assets['renderer'].replace('def native(p):return {','def native(p):return None if not p else {');period=[(date-datetime.timedelta(days=i)).isoformat()for i in(3,2,1)]
   renderer=renderer.replace("['2026-11-09','2026-11-10','2026-11-11']",repr(period)).replace('2026-11-12_actions',day+'_actions')
   caption=datetime.datetime.fromisoformat(evidence['finished_at']).astimezone(MSK).strftime('%d.%m.%Y %H:%M МСК')+' · когорта06.11 · KGS'
   renderer=renderer.replace('12.11.2026 · 09–11.11 свежие · когорта 06.11 · KGS',caption)
   renderer=renderer.replace('cid in [41516903,41517233]','str(cid) in z["internal_analysis"]["missing_required_day"]')
   renderer=renderer.replace("if c['id']==39605581:","if any(f['cid']==c['id'] for f in z['funding']):")
   renderer=renderer.replace('budget_reserve_amount=1200','budget_reserve_amount=next(f["amount_kgs"] for f in z["funding"]if f["cid"]==c["id"])')
   renderer=renderer.replace("==0\n# No China", "==len(z['actions'])\n# No China")
   renderer=renderer.replace("'action_count':0","'action_count':len(z['actions'])")
   renderer=renderer.replace("'Исключить из РК.'if v['kind']=='exclude_sku'else('Рекомендации'if v['placement']=='recommendations'else'Поиск')+': снизить 3,60 → 3,25 KGS.'","'Исключить из РК.'if v['kind']=='exclude_sku'else('Рекомендации'if v['placement']=='recommendations'else'Поиск')+': снизить '+format(v['from_minor']/100,'.2f').replace('.',',')+' → '+format(v['to_minor']/100,'.2f').replace('.',',')+' KGS.'")
   missing=z['internal_analysis']['missing_required_day'];renderer=renderer.replace('Нет полной строки WB у РК 41516903 и 41517233','Пропуски WB: '+(', '.join(missing)if missing else 'нет'))
   execute(renderer,R/'work/render.py');kinds=['advertising','budgets'];files=[R/'outputs'/('VESCHI_OOO_'+k+'_'+day+'_actions_only.png')for k in kinds]
  else:
   ids=[39605581,39605579,40385586,41515989,41516310,41516903,41517233,41517533,39605582]
   request={'read_only':True,'cabinet':'token_1','day':day,'campaign_ids':ids}
   if not db.get(root+':request'):db.once(root+':request',request)
   reader=assets['midreader'].replace('2026-11-11',day);execute(reader,R/'work/readmid.py');s=db.get(root+':read')or{}
   if not s.get('data')or not s.get('steps'):raise RuntimeError('Current-day source unavailable')
   s.update(day=day,observed_at=s['steps']['0']['observed_at'],status='partial',missing_ids=sorted(set(s['steps']['0']['requested_ids'])-{c['advertId']for c in s['data']}))
   (R/'work/ooo_midday11_current.json').write_text(json.dumps(s),encoding='utf-8');(R/'work/ooo_morning11_review.json').write_text(json.dumps({'actions':[],'funding':[]}),encoding='utf-8')
   (R/'work/ooo_morning11_analysis.json').write_text(json.dumps(a),encoding='utf-8')
   renderer=assets['midrenderer'].replace("source['day']=='2026-11-11'","source['day']=="+repr(day)).replace('VESCHI_OOO_midday_2026-11-11.png','VESCHI_OOO_midday_'+day+'.png')
   execute(renderer,R/'work/rendermid.py');kinds=['midday'];files=[R/'outputs'/('VESCHI_OOO_midday_'+day+'.png')];z['actions']=[];z['funding']=[]
  if verify:
   return {'status':'render_verified','images':len(files),'sizes':[p.stat().st_size for p in files],'actions':len(z['actions']),'funding':z['funding'],'catalogue':len(a['rows'])}
  def once(k,v):
   if not db.get(k):db.once(k,v)
  images=[]
  for kind,path in zip(kinds,files):
   raw=path.read_bytes();encoded=base64.b64encode(raw).decode();keys=[]
   for i in range(0,len(encoded),40000):
    k=root+':artifact:'+kind+':'+str(i//40000);keys.append(k);once(k,{'data':encoded[i:i+40000]})
   images.append({'kind':kind,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'chunk_keys':keys})
  raw=canonical(z).encode();encoded=base64.b64encode(raw).decode();keys=[]
  for i in range(0,len(encoded),40000):
   k=root+':analysis:'+str(i//40000);keys.append(k);once(k,{'data':encoded[i:i+40000]})
  manifest={'cabinet':'token_1','currency':'KGS','actions':[{k:v for k,v in x.items()if k!='article'}for x in z['actions']],'topups':z['funding'],'other_changes':[]}
  plan=('morning-'+day)if slot=='morning'else('midday-'+day+'-1500')
  report={'status':'ready','analysis':{'full_analysis':{'encoding':'base64-json-utf8','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'chunk_keys':keys}},'wb_writes':0,'model_calls':0}
  once(root+':report',report);once(root+':telegram:input',{'owner_approved':True,'chat_id':-1003987998401,'kinds':kinds,'images':images})
  once('ooo_agent:sol_dialog:v1:publication:'+plan,{'status':'prepared','plan_id':plan,'chat_id':-1003987998401,'manifest':manifest,'manifest_sha256':hashlib.sha256(canonical(manifest).encode()).hexdigest(),'expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=17)).isoformat(),'artifact_sha256':[x['sha256']for x in images],'receipt_keys':[root+':telegram:delivery:'+k for k in kinds]})
  sender=assets['sender'if slot=='morning'else'midsender'].replace('2026-11-11',day);execute(sender,R/'work/send.py')
  final=db.get(root+':telegram:execution')or{}
  if final.get('status')!='verified':raise RuntimeError('Delivery requires attention; never replay unknown attempt')
  return {'status':'verified','receipts':final.get('receipts')}
def run():
 if os.environ.get('OOO_REPORT_VERIFY_ONLY')=='1':
  print(json.dumps(worker('morning',verify=True)));return
 now=datetime.datetime.now(MSK);due=[]
 if(now.hour,now.minute)>=(7,30):due.append('morning')
 if(now.hour,now.minute)>=(15,0):due.append('midday')
 for slot in due:print(json.dumps(worker(slot)))
if __name__=='__main__':run()