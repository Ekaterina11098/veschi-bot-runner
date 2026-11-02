"""Owner2Nov: edit only budget614; no marketplace capability."""
import os,json,copy,base64,hashlib
from datetime import datetime,timezone
import requests
from china_advertising_state import AdvertisingIO
import china_advertising_v2_png as png
DAY='2026-11-02'
ROOT='china_agent:budget_owner_correction:2026-11-02:v1'
ART='china_agent:advertising_artifacts:'+DAY+':v2'
DEL='china_agent:advertising_delivery:'+DAY+':v1'
class IO(AdvertisingIO):
 def wb(self,*a,**k):raise RuntimeError('No WB capability')
io=IO()
def save(k,v):
 if io.get(k) is None:
  if not io.create(k,v):raise RuntimeError('Concurrent create')
 else:io.put(k,v)
def main():
 auth=io.get(ROOT+':approval')
 if not auth or auth.get('message_id')!=614 or auth.get('owner_id')!=5122667182 or auth.get('status')!='approved':raise RuntimeError('No exact owner authorization')
 e=io.get(ROOT)
 if e and e.get('status')=='completed':return
 if e:raise RuntimeError('Prior attempt exists; no blind Telegram retry')
 art=io.get(ART);delivery=io.get(DEL)
 part=next(p for p in delivery['parts'] if p['kind']=='budgets:001')
 original=next(f for f in art['files'] if f['family']=='budgets')
 if part['message_id']!=614 or part['receipt']['chat']['id']!=-1004342917488 or part['receipt']['from']['id']!=8780468043 or part['sha256']!=hashlib.sha256(base64.b64decode(original['b64'])).hexdigest():raise RuntimeError('Identity changed')
 for suffix,value in [('before_artifacts',art),('before_delivery',delivery)]:
  if io.get(ROOT+':'+suffix) is None:save(ROOT+':'+suffix,value)
 bundle=copy.deepcopy(art['bundle'])
 old=png.budget_column
 def column(c):
  return 'Пока не пополнять' if c['id']==41296359 else old(c)
 png.budget_column=column
 files=[f for f in png.render(bundle) if f['family']=='budgets']
 if len(files)!=1 or files[0]['actions']:raise RuntimeError('Expected one zero-action budget PNG')
 raw=files[0]['bytes'];sha=hashlib.sha256(raw).hexdigest()
 e=dict(status='submitting',message_id=614,sha256=sha,wb_writes=0,submitted_at=datetime.now(timezone.utc).isoformat())
 save(ROOT,e)
 media=dict(type='photo',media='attach://photo',caption='Китай · бюджеты · 2026-11-02 · исправлено по просьбе владельца. РК 41296359 пока не пополнять. Новых действий: 0.')
 answer=requests.post('https://api.telegram.org/bot'+io.bot+'/editMessageMedia',data=dict(chat_id=-1004342917488,message_id=614,media=json.dumps(media,ensure_ascii=False)),files=dict(photo=('budgets.png',raw,'image/png')),timeout=45).json()
 if not answer.get('ok'):
  e.update(status='rejected',error_code=answer.get('error_code'));save(ROOT,e);raise RuntimeError('Telegram edit rejected')
 receipt=answer['result']
 if receipt.get('message_id')!=614 or receipt.get('chat',{}).get('id')!=-1004342917488 or receipt.get('from',{}).get('id')!=8780468043 or not receipt.get('photo'):raise RuntimeError('Edited receipt mismatch')
 e.update(status='edited',receipt=receipt,b64=base64.b64encode(raw).decode());save(ROOT,e)
 original['b64']=e['b64'];original['owner_revision']=ROOT
 if 'sha256' in original:original['sha256']=sha
 art['owner_revision']=ROOT
 part.update(sha256=sha,receipt=receipt,owner_revision=ROOT,edited_at=datetime.now(timezone.utc).isoformat())
 delivery['owner_revision']=ROOT
 save(ART,art);save(DEL,delivery)
 e.update(status='completed',completed_at=datetime.now(timezone.utc).isoformat());save(ROOT,e)
 print(json.dumps(dict(status=e['status'],message_id=614,wb_writes=0)))
if __name__=='__main__':main()
