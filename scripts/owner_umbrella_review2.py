"""Owner2Nov: edit only budget614; no marketplace capability."""
import os,json,copy,base64,hashlib
from datetime import datetime,timezone
import requests
from china_advertising_state import AdvertisingIO
import china_advertising_v2_png as png
DAY='2026-11-02'
ROOT='china_agent:budget_owner_correction:2026-11-02:v2'
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
  return 'Пока не пополнять' if c['id'] in (41296359,41325637) else old(c)
 png.budget_column=column
 files=[f for f in png.render(bundle) if f['family']=='budgets']
 if len(files)!=1 or files[0]['actions']:raise RuntimeError('Expected one zero-action budget PNG')
 raw=files[0]['bytes'];sha=hashlib.sha256(raw).hexdigest()
 e=dict(status='submitting',message_id=614,sha256=sha,wb_writes=0,submitted_at=datetime.now(timezone.utc).isoformat())
 save(ROOT,e)
 media=dict(type='photo',media='attach://photo',caption='Китай · бюджеты · 2026-11-02 · исправлено по просьбе владельца. РК 41296359 и 41325637 пока не пополнять. Новых действий: 0.')
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


def audit():
 from china_advertising_v2 import http,history,read_price_experience
 from china_analytic_dialog import Analyst,reading
 from china_advertising_economic_review import model_rows
 from datetime import date
 source=io.get('china_agent:advertising_source:2026-11-02:v2')
 current=http(io,'/api/advert/v2/adverts?ids=41325637')['adverts']
 if len(current)!=1 or current[0]['currency']!='CNY':raise RuntimeError('Cabinet campaign identity')
 ids=sorted(n['nm_id'] for n in current[0]['nm_settings'])
 if len(ids)>20:raise RuntimeError('Unexpected scope')
 class Work:
  now=datetime.now(timezone.utc)
  def get(self,k):return io.get(k)
  def save(self,k,v,**kw):save(k,v)
  def catalog(self):return [(str(r['nmID']),r['vendorCode']) for r in source['catalogue']['rows']]
 w=Work();an=Analyst(w,dict(request_text='Адресная экономика оставшихся зонтов41325637'),[])
 with reading():
  prices=an.collect('prices',ids,date(2026,10,3),date(2026,11,1))
  stock=an.collect('stock',ids,date(2026,10,3),date(2026,11,1))
 for val in (prices,stock):val['observed_at']=datetime.now(timezone.utc).isoformat()
 products=io.get('china_agent:analytic_read:v1:893557e46ce1918d55ff958ce88fd1f202ee06e10e60792aeabbbb67cd857b35')
 fx=io.get('china_agent:cbr_cny:v1:2026-11-01')
 if not products or products['period_to']!='2026-11-01':raise RuntimeError('Own completed history missing')
 minimum=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=41325637,nm_ids=ids,payment_type='cpc',placement_types=['search']))
 inputs=dict(products=products,prices=prices,stock=stock,fx=fx)
 economics=model_rows(inputs,io.get('china_agent:new_ad_economics_policy:v1') or {},io.get('china_agent:expected_profit_delivery_model:v1') or {})
 events=[e for e in history(source['executions']) if e.get('nm') in ids]
 price_events=[e for e in read_price_experience(io) if int(e['action'].get('item') or e['action'].get('nm_ids',[0])[0]) in ids]
 save(ROOT+':audit',dict(status='complete',observed_at=datetime.now(timezone.utc).isoformat(),campaign=current[0],minima=minimum,economics=economics,events=events,price_events=price_events,prices=prices,stock=stock,products=dict(products,rows=[r for r in products['rows'] if r.get('nm_id') in ids]),wb_writes=0))
if __name__=='__main__':
 audit()
 main()
