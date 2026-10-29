"""Exact owner-authorized IP card document inspection. No writes."""
import os,json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import requests
from stock_deploy_support import seal
targets={432727736:'472-StellaBag-beige',240435457:'126-BeatriceBag-brown'}
proof={'complete':False,'wb_writes':0,'cards':[],'schemas':{}}
try:
 for nm,sku in targets.items():
  r=requests.post('https://content-api.wildberries.ru/content/v2/get/cards/list',headers={'Authorization':os.environ['WB_TOKEN_2']},json={'settings':{'cursor':{'limit':100},'filter':{'textSearch':str(nm),'withPhoto':-1}}},timeout=60)
  if not r.ok: raise RuntimeError('Card read HTTP '+str(r.status_code))
  cards=[c for c in r.json().get('cards',[]) if c.get('nmID')==nm and c.get('vendorCode')==sku]
  if len(cards)!=1:raise RuntimeError('Exact IP card identity not found '+str(nm))
  c=cards[0];proof['cards'].append(c)
  sid=c['subjectID']
  if str(sid) not in proof['schemas']:
   time.sleep(1)
   r=requests.get('https://content-api.wildberries.ru/content/v2/object/charcs/'+str(sid),headers={'Authorization':os.environ['WB_TOKEN_2']},timeout=60)
   if not r.ok:raise RuntimeError('Subject schema HTTP '+str(r.status_code))
   proof['schemas'][str(sid)]=r.json()
  time.sleep(1)
 proof['complete']=len(proof['cards'])==2
except Exception as e:proof['error']=str(e) if isinstance(e,RuntimeError) else type(e).__name__
finally:
 seal('ip-documents-read-20261029',proof)
 print(json.dumps({'complete':proof['complete'],'wb_writes':0,'error':proof.get('error')}))
if not proof['complete']:raise SystemExit(1)
