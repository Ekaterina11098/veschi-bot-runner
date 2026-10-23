"""One reply-bound IP plan; no dispatcher, queues, timers or automatic restoration."""
import argparse,base64,copy,hashlib,json,os,re,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path.cwd()))
from china_price_apply import IO as BaseIO
from china_loss_ads import check
CHAT=-1004378639510
BOT=8987327588
PLAN='advertising:ip:png_plan:20261023:five:v1'
TARGETS={506186804,255477781,1007948812,347406432,776196396}
CID=39410834
def now():return datetime.now(timezone.utc)
def digest(p):return hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def current(io,ids):
 if ids!=[CID]:raise ValueError('Exact campaign read only')
 from analytics.collect import fetch
 j=fetch('GET','https://advert-api.wildberries.ru/api/advert/v2/adverts',io.token,params={'ids':str(CID)},max_retry_wait=1200)
 if len(j.get('adverts',[]))!=1 or j['adverts'][0]['id']!=CID:raise ValueError('Incomplete configuration')
 return {CID:j['adverts'][0]}
def http(io,path,method,body):
 # Single non-retriable write; share endpoint cooldown, never reuse retrying read transport.
 if method!='PATCH' or path!='/adv/v0/auction/nms' or body!={'nms':[{'advert_id':CID,'nms':{'add':[],'delete':sorted(TARGETS)}}]}:raise ValueError('Write outside exact plan')
 import requests,time
 from analytics.collect import database
 pause='wb-pause:'+hashlib.sha256((io.token+'advert-api.wildberries.ru'+path).encode()).hexdigest()
 existing=io.get(pause)
 if existing and existing.get('until',0)>time.time():raise RuntimeError('Shared write cooldown; no write attempted')
 r=requests.patch('https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=45)
 if r.status_code==429:
  from analytics.mpstats_probe import retry_delay
  seconds=retry_delay(r.headers.get('Retry-After') or r.headers.get('X-Ratelimit-Retry') or '65')
  database('POST','telegram_api_cache',body={'cache_key':pause,'payload':{'until':time.time()+seconds+1},'expires_at':(now()+timedelta(seconds=seconds+61)).isoformat()},params={'on_conflict':'cache_key'})
 if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code)+'; no write replay')
 return r.json() if r.content else {}
class IO(BaseIO):
 def __init__(self):
  self.url=os.environ['SUPABASE_URL'].rstrip('/');key=os.environ['SUPABASE_SECRET_KEY']
  self.headers={'apikey':key,'Content-Type':'application/json'}
  if not key.startswith('sb_secret_'):self.headers['Authorization']='Bearer '+key
  self.token=os.environ['WB_TOKEN_2'];self.bot=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN']
 def identity(self):
  if self.tg('getMe',{}).get('id')!=BOT:raise ValueError('Bot identity mismatch')
  rows=self.db('advertising_telegram_chat?is_active=eq.true&select=chat_id')
  if rows!=[{'chat_id':CHAT}]:raise ValueError('Registered group changed')
 def member(self,uid):
  m=self.tg('getChatMember',dict(chat_id=CHAT,user_id=uid))
  if m.get('user',{}).get('id')!=uid or m['user'].get('is_bot') or not(m.get('status') in ['member','administrator','creator'] or m.get('status')=='restricted' and m.get('is_member') is True):raise ValueError('Not a current human member')
def validate(p):
 if not p or p.get('chat_id')!=CHAT or p.get('bot_id')!=BOT or p.get('campaign_id')!=CID or p.get('return_policy')!='separate_explicit_decision':raise ValueError('Plan scope mismatch')
 if len(p['items'])!=5 or {x['nm_id'] for x in p['items']}!=TARGETS or any(x['kind']!='ad_exclude_sku' or x['campaign_id']!=CID for x in p['items']):raise ValueError('Only exact five exclusions allowed')
 if p['plan_sha256']!=digest(p['items']):raise ValueError('Plan changed')
def stable(c):
 return {k:copy.deepcopy(c.get(k)) for k in ['id','currency','status','bid_type','settings','nm_settings','restrictions']}
def prepare(io,p):
 validate(p);io.identity()
 # Publishing a saved proposal needs no additional WB collection. Fresh read is mandatory only on execution.
 b=p['baseline']
 if b.get('currency')!='RUB' or b.get('status')!=9 or b.get('settings',{}).get('payment_type')!='cpm' or b.get('bid_type')!='manual' or not b.get('restrictions',{}).get('can_change_nms'):raise ValueError('Unexpected campaign settings')
 ids={n['nm_id'] for n in b['nm_settings']}
 if not TARGETS<ids:raise ValueError('Five targets not present or campaign would be emptied')
 return stable(b)
def publish(io):
 p=io.get(PLAN);validate(p)
 if p.get('message_id'):return dict(status='already_sent',message_id=p['message_id'],wb_writes=0)
 if p.get('delivery_status') in ['sending','uncertain']:return dict(status='uncertain',wb_writes=0)
 data=base64.b64decode(p['png_base64'],validate=True)
 if hashlib.sha256(data).hexdigest()!=p['png_sha256']:raise ValueError('PNG changed')
 before=prepare(io,p)
 if not io.create(PLAN+':publish_claim',dict(status='sending',created_at=now().isoformat())):raise ValueError('Publication already claimed; no blind repeat')
 p.update(delivery_status='sending',before=before,expires_at=(now()+timedelta(hours=24)).isoformat());io.put(PLAN,p)
 import requests
 try:
  cap='ИП · рекомендации за 20–22 октября.\nДля применения ответьте на этот PNG: «Сделай всё». Любой участник этой группы может подтвердить.\nИсключить только пять указанных товаров из РК 39410834 до отдельного возврата. Другие товары и РК не менять.\nПостклик по исходным товарам не подтверждён. До ответа изменения не выполняются.'
  r=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data=dict(chat_id=CHAT,caption=cap),files={'photo':('IP-recommendations.png',data,'image/png')},timeout=45).json()
  if not r.get('ok') or r['result'].get('chat',{}).get('id')!=CHAT:raise ValueError('Delivery not confirmed')
  m=r['result'];p.update(delivery_status='sent',message_id=m['message_id'],file_unique_id=m['photo'][-1]['file_unique_id'],message_thread_id=m.get('message_thread_id'),sent_at=now().isoformat());io.put(PLAN,p)
  io.put(PLAN+':publish_claim',dict(status='sent',message_id=p['message_id']))
  return dict(status='sent',message_id=p['message_id'],wb_writes=0)
 except Exception:
  p['delivery_status']='uncertain';io.put(PLAN,p);raise
def apply(io,key):
 if key!=PLAN+':approval':raise ValueError('Approval key outside exact plan')
 a=io.get(key);p=io.get(PLAN);validate(p);io.identity()
 if not a or a.get('chat_id')!=CHAT or a.get('bot_id')!=BOT or a.get('reply_message_id')!=p.get('message_id') or a.get('plan_sha256')!=p['plan_sha256'] or a.get('command')!='Сделай всё' or type(a.get('update_id')) is not int or type(a.get('sender_id')) is not int:raise ValueError('Missing exact Telegram approval')
 if now()>datetime.fromisoformat(p['expires_at']):raise ValueError('Plan expired; no execution')
 io.member(a['sender_id']);ek=PLAN+':execution'
 e=io.get(ek)
 if e:return e # Never repeat an uncertain or completed write.
 if not io.create(ek,dict(status='preflight',wb_writes=0,approval=a)):return io.get(ek)
 e=io.get(ek)
 try:
  before=current(io,[CID])[CID]
  if stable(before)!=p['before']:raise ValueError('WB composition/settings changed since PNG; fresh plan required')
  body=dict(nms=[dict(advert_id=CID,nms=dict(add=[],delete=sorted(TARGETS)))])
  e.update(status='submitting',before=before,request=body);io.put(ek,e)
  response=http(io,'/adv/v0/auction/nms','PATCH',body)
  e.update(status='accepted',wb_writes=1,response=response);io.put(ek,e)
  after=current(io,[CID])[CID]
  verified=check(p,{CID:before},{CID:after}) and all(before.get(k)==after.get(k) for k in ['currency','bid_type','restrictions'])
  e.update(status='verified' if verified else 'uncertain',after=after);io.put(ek,e)
 except Exception as ex:
  e.update(status='uncertain' if e['status'] in ['submitting','accepted'] else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__);io.put(ek,e)
 nk=PLAN+':result'
 if io.create(nk,dict(status='sending')):
  try:
   text='Исключены только 534-NoelBag-emerald, 593-KendraBag-coffee, 61-NoelBag-beige, 209-JessicaBag-grey и 600-JessicaBag-blue из РК39410834. Проверено WB. Возврат — только отдельным решением.' if e['status']=='verified' else 'Применение не подтверждено: '+e.get('reason',e['status'])+'. Повторная запись заблокирована.'
   r=io.tg('sendMessage',dict(chat_id=CHAT,text=text,reply_parameters=dict(message_id=a['input_message_id'])))
   if r.get('chat',{}).get('id')!=CHAT:raise ValueError('Receipt mismatch')
   io.put(nk,dict(status='sent',message_id=r['message_id']))
  except Exception:io.put(nk,dict(status='uncertain'))
 return e
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['publish','apply'],required=True);parser.add_argument('--approval-key',default='');args=parser.parse_args()
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=IO();result=publish(io) if args.mode=='publish' else apply(io,args.approval_key)
 from stock_deploy_support import seal
 seal('ip-png-plan',result)
 print(json.dumps({k:result.get(k) for k in ['status','message_id','wb_writes']}))

