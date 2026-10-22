"""Exact approved SKU exclusions, batched once, full campaign readback and PNG receipt."""
import copy,hashlib,json,os,time,tempfile
from datetime import datetime,timezone
from pathlib import Path
from china_loss_control import PLAN,CHAT,BOT,OWNER,digest
def stamp():return datetime.now(timezone.utc).isoformat()
def nmset(c):return {int(x['nm_id']) for x in c.get('nm_settings',[])}
def operation(plan,before):
 grouped={}
 for i in plan['items']:
  if i['kind']=='ad_exclude_sku':grouped.setdefault(i['campaign_id'],set()).add(i['nm_id'])
 result=[]
 for cid,targets in grouped.items():
  c=before[cid]
  if c.get('currency')!='CNY' or c.get('status')!=9 or c.get('settings',{}).get('payment_type')!='cpc':raise ValueError('Статус, валюта или тип РК изменились')
  ids=nmset(c);remove=ids&targets
  if not ids-remove:raise ValueError('Исключение оставит РК без товаров')
  if remove:result.append(dict(advert_id=cid,nms=dict(add=[],delete=sorted(remove))))
 return dict(nms=result)
def check(plan,before,after):
 target={}
 for i in plan['items']:
  if i['kind']=='ad_exclude_sku':target.setdefault(i['campaign_id'],set()).add(i['nm_id'])
 for cid,b in before.items():
  a=after.get(cid)
  if not a or a.get('status')!=b.get('status') or a.get('settings')!=b.get('settings'):return False
  if nmset(a)!=nmset(b)-target.get(cid,set()):return False
  old={x['nm_id']:x for x in b['nm_settings']}
  if any(old.get(x['nm_id'])!=x for x in a['nm_settings']):return False
 return True
def http(io,path,method='GET',body=None):
 import requests
 time.sleep(1.2)
 r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=45)
 if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code))
 return r.json() if r.content else {}
def current(io,ids=None):
 if ids is None:
  j=http(io,'/adv/v1/promotion/count');ids=sorted({x['advertId'] for g in j.get('adverts',[]) if g.get('status')==9 for x in g.get('advert_list',[])})
  if not ids:raise ValueError('Нет активных РК')
 if len(ids)>50:raise ValueError('Нужна полная пагинация рекламных кампаний')
 j=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,ids)))
 cs=j.get('adverts',[])
 if {c['id'] for c in cs}!=set(ids):raise ValueError('Неполный ответ рекламного API')
 return {c['id']:c for c in cs}
def execute(io,approval,p):
 key='china_agent:loss_ad_execution:v1:'+p['plan_id'];e=io.get(key)
 if e and e.get('status') in ['verified','blocked','uncertain']:return e
 io.validate_owner(approval)
 if p.get('plan_sha256')!=digest(p['items']) or approval['plan_sha256']!=p['plan_sha256']:raise ValueError('Plan hash changed')
 if e:
  # A persisted in-flight write is NEVER repeated. Only read the existing outcome.
  if e['status'] in ['submitting','accepted']:
   try:
    a=current(io,[int(k) for k in e['before']]);b={int(k):v for k,v in e['before'].items()}
    e.update(status='verified' if check(p,b,a) else 'accepted',after=a,verified_at=stamp())
   except Exception as ex:e.update(status='uncertain',reason=type(ex).__name__)
   io.put(key,json.loads(json.dumps(e)))
  return e
 e=dict(status='preflight',plan_id=p['plan_id'],approval_job=approval['job_id'],created_at=stamp(),wb_writes=0)
 if not io.create(key,e):return io.get(key)
 try:
  before=current(io)
  for item in p['items']:
   if item['kind']=='ad_exclude_sku' and item['campaign_id'] not in before:raise ValueError('Согласованная РК уже не активна')
   if item['kind']=='keep_outside_ads' and any(item['nm_id'] in nmset(c) for c in before.values()):raise ValueError('Товар внеРК появился в рекламе — нужен новый план')
  body=operation(p,before);e.update(before=before,request=body,status='submitting' if body['nms'] else 'verified');io.put(key,json.loads(json.dumps(e)))
  if not body['nms']:return e
  response=http(io,'/adv/v0/auction/nms','PATCH',body)
  e.update(status='accepted',response=response,submitted_at=stamp(),wb_writes=1);io.put(key,json.loads(json.dumps(e)))
  after=current(io,list(before))
  e.update(after=after,status='verified' if check(p,before,after) else 'accepted',verified_at=stamp());io.put(key,json.loads(json.dumps(e)))
 except Exception as ex:
  e.update(status='uncertain' if e['status']=='submitting' else ('accepted' if e['status']=='accepted' else 'blocked'),reason=str(ex) if isinstance(ex,(RuntimeError,ValueError)) else type(ex).__name__);io.put(key,json.loads(json.dumps(e)))
 return e
def results(plan,e):
 out=[]
 for i in plan['items']:
  if e['status']=='verified':
   text='Уже вне активных РК — без изменений' if i['kind']=='keep_outside_ads' else 'Исключён из РК '+str(i['campaign_id'])
  elif e['status']=='accepted':text='WB принял; результат проверяется'
  else:text='Не выполнено: '+e.get('reason','результат не подтверждён')
  out.append((i['article'],text))
 return out
def render(plan,e,path):
 from PIL import Image,ImageDraw,ImageFont
 def f(n,b=False):return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf',n)
 im=Image.new('RGB',(1500,1120),'#f4f7fb');d=ImageDraw.Draw(im)
 d.text((30,25),'Китай • результат выполнения',font=f(34,True),fill='#20344f')
 d.rounded_rectangle((20,88,1480,146),10,fill='#253c59')
 for x,t in [(35,'Артикул'),(650,'Результат')]:d.text((x,102),t,font=f(26,True),fill='white')
 for n,(article,text) in enumerate(results(plan,e)):
  y=156+n*80;d.rounded_rectangle((20,y,1480,y+72),8,fill='white' if n%2==0 else '#e7eef7')
  d.text((35,y+21),article,font=f(23,True),fill='#20344f');d.text((650,y+21),text,font=f(22),fill='#20344f')
 note='Проверено WB. Цены и остальные товары РК сохранены.' if e['status']=='verified' else 'Цены не менялись. Выполнение не объявляется без проверки WB.'
 d.text((30,995),note,font=f(23),fill='#52647c');d.text((30,1040),'Контроль: 4 полных дня после фактического изменения.',font=f(22),fill='#52647c')
 im.save(path)
def process_and_deliver(io,a,p):
 e=execute(io,a,p)
 if e['status']=='accepted':return e # Delayed API synchronization: send only verified final or concrete failure.
 delivery='china_agent:loss_ad_result_png:v1:'+p['plan_id']
 if io.get(delivery):return e
 if not io.create(delivery,dict(status='rendering',plan_id=p['plan_id'])):return e
 try:
  import requests
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'Китай-результат.png';render(p,e,path)
   io.put(delivery,dict(status='sending',plan_id=p['plan_id']))
   r=requests.post('https://api.telegram.org/bot'+io.bot+'/sendDocument',data={'chat_id':CHAT,'caption':'Результат выполнения. Цены не менялись.','reply_parameters':json.dumps(dict(message_id=a['input_message_id'],allow_sending_without_reply=True))},files={'document':(path.name,path.read_bytes(),'image/png')},timeout=45).json()
   if not r.get('ok'):raise RuntimeError('Telegram result not confirmed')
   io.put(delivery,dict(status='sent',plan_id=p['plan_id'],message_id=r['result']['message_id'],chat_id=CHAT,results=results(p,e)))
 except Exception:io.put(delivery,dict(status='uncertain',plan_id=p['plan_id']))
 return e
