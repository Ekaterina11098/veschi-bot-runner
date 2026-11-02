"""Owner-requested exact media replacement628629; no WB reads/writes."""
import os,json,copy,base64,hashlib
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
from china_advertising_state import AdvertisingIO
from owner_midday_renderer2 import render_midday
ROOT='china_agent:owner_midday_replace:2026-11-02:v1'
ART='china_agent:advertising_midday_artifacts:2026-11-02:v1'
DEL='china_agent:advertising_midday_delivery:2026-11-02:v1'
def now():return datetime.now(timezone.utc).isoformat()
class IO(AdvertisingIO):
 def wb(self,*a,**k):raise RuntimeError('NoWBcapability')
def main():
 os.environ.setdefault('WB_TOKEN_3','unused-no-wb-capability')
 io=IO();a=io.get(ROOT+':approval')or{}
 if a.get('status')!='approved' or a.get('owner_id')!=5122667182 or a.get('message_ids')!=[628,629]:raise ValueError('Exactapprovalabsent')
 if io.get(ROOT):raise ValueError('Priorattempt;neverblindTelegramretry')
 art=io.get(ART);delivery=io.get(DEL)
 if delivery.get('status')!='delivered' or len(art['files'])!=2:raise ValueError('Originalscopechanged')
 for f,p,mid in zip(art['files'],delivery['parts'],[628,629]):
  if p['message_id']!=mid or p['status']!='sent' or p['receipt']['chat']['id']!=-1004342917488 or p['receipt']['from']['id']!=8780468043:raise ValueError('Identitychanged')
  if hashlib.sha256(base64.b64decode(f['b64'])).hexdigest()!=p['sha256'] or f['action_count']!=0:raise ValueError('Originalartifactchanged')
 for suffix,value in [('before_artifacts',art),('before_delivery',delivery)]:
  if not io.create(ROOT+':'+suffix,value):raise ValueError('Archiveexists')
 b=copy.deepcopy(art['bundle']);b['force_two_pages']=True
 for c in b['campaigns']:c['archived']=c['id']in[41270474,41413113,41415271]
 files=render_midday(b)
 if len(files)!=2 or any(f['actions'] for f in files):raise ValueError('Unexpectedplan')
 e=dict(status='prepared',message_ids=[628,629],parts=[],created_at=now(),wb_writes=0)
 if not io.create(ROOT,e):raise ValueError('Concurrentexecution')
 for index,(f,p,old) in enumerate(zip(files,delivery['parts'],art['files']),1):
  mid=p['message_id'];raw=f['bytes'];sha=hashlib.sha256(raw).hexdigest()
  step=dict(status='submitting',message_id=mid,sha256=sha,submitted_at=now());e['parts'].append(step);io.put(ROOT,e)
  cap='Китай · промежуточный отчёт · 2026-11-02 · '+str(index)+'/2. Новых действий для исполнения нет.'
  media=dict(type='photo',media='attach://photo',caption=cap)
  answer=requests.post('https://api.telegram.org/bot'+io.bot+'/editMessageMedia',data=dict(chat_id=-1004342917488,message_id=mid,media=json.dumps(media,ensure_ascii=False)),files=dict(photo=('midday.png',raw,'image/png')),timeout=45).json()
  if not answer.get('ok'):
   step.update(status='rejected',error_code=answer.get('error_code'));e['status']='partial_or_rejected';io.put(ROOT,e);raise RuntimeError('Telegrameditrejected')
  r=answer['result']
  if r.get('message_id')!=mid or r.get('chat',{}).get('id')!=-1004342917488 or r.get('from',{}).get('id')!=8780468043 or not r.get('photo'):raise RuntimeError('Editedreceiptmismatch')
  step.update(status='edited',receipt=r,edited_at=now());io.put(ROOT,e)
  old.update(b64=base64.b64encode(raw).decode(),owner_revision=ROOT)
  p.update(sha256=sha,receipt=r,owner_revision=ROOT,edited_at=now())
  io.put(ART,art);io.put(DEL,delivery)
 art['owner_revision']=ROOT;delivery['owner_revision']=ROOT;io.put(ART,art);io.put(DEL,delivery)
 e.update(status='completed',completed_at=now());io.put(ROOT,e)
 print(json.dumps(dict(status=e['status'],message_ids=e['message_ids'],wb_writes=0)))
if __name__=='__main__':main()
