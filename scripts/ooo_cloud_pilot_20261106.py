"""One manual, cache-only OOO cloud pilot. No WB credentials, webhook changes or schedules."""
import os,json,time,hashlib,io,datetime,sys
from decimal import Decimal
MODEL='gpt-6.1-sol'
SOL_RATES={'input':2,'cached_input':0.1,'output':10}
from china_codex_cloud import DB
ROOT='ooo_agent:cloud_pilot:2026-11-06:v1'
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
class Cache:
 def __init__(self,db=None):self.db=db or DB();self.read_bytes=0;self.write_bytes=0
 def check(self,k):
  if not k.startswith(ROOT+':'):raise PermissionError('Pilot cache boundary')
 def get(self,k):
  self.check(k);v=self.db.get(k);self.read_bytes+=len(json.dumps(v,ensure_ascii=False).encode());return v
 def once(self,k,v):
  self.check(k);self.write_bytes+=len(json.dumps(v,ensure_ascii=False).encode());return self.db.once(k,v)
 def update(self,k,v):
  self.check(k);self.write_bytes+=len(json.dumps(v,ensure_ascii=False).encode())
  if not self.db.update(k,v):raise RuntimeError('Private state update not confirmed')
def select_trigger(updates,policy):
 found={}
 for u in updates:
  m=u.get('message')or{};ch=m.get('chat')or{};sender=m.get('from')or{}
  if ch.get('type')not in('group','supergroup')or sender.get('id')not in policy['allowed_senders']:continue
  if m.get('text','').strip().casefold()!=('/pilot@'+policy['expected_username']).casefold():continue
  if m.get('date',0)<policy['command_not_before_unix']:continue
  found[ch['id']]={'chat_id':ch['id'],'chat_title':ch.get('title',''),'sender_id':sender['id'],'input_message_id':m['message_id'],'update_id':u['update_id'],'command':m['text']}
 if len(found)!=1:raise ValueError('Expected one authorized pilot group command')
 return next(iter(found.values()))
def cost(usage,rates):
 i=int(usage['input_tokens']);o=int(usage['output_tokens']);c=int((usage.get('input_tokens_details')or{}).get('cached_tokens',0))
 if min(i,o,c)<0 or c>i:raise ValueError('Invalid usage receipt')
 return (Decimal(i-c)*Decimal(str(rates['input']))+Decimal(c)*Decimal(str(rates['cached_input']))+Decimal(o)*Decimal(str(rates['output'])))/Decimal(1000000)
def model_message(policy):
 facts={'period_day':policy['snapshot']['day'],'period_three':policy['snapshot']['three_days'],'observed_at':policy['snapshot']['advertising_at'],'currency':'KGS','totals':policy['snapshot']['totals']}
 instructions='Ты облачный аналитик ООО VESCHI. Только короткий ответ на вопрос по переданному датированному кэшу. Покажи расходы, сумму атрибутированных заказов и ДРР за день и3дня. ДРР=расход/сумма заказов*100. Не называй это всеми продажами или прибылью. Срез не текущий онлайн. Не давай команд на изменение. Никаких инструментов, WB, SQL, файлов или рассылок. Не придумывай недостающие данные. Ответ по-русски, до1200символов.'
 question='Пилот /pilot: какие расходы, рекламные заказы и ДРР у ООО за последний полный день и три дня по готовому утреннему кэшу?'
 msg=[{'role':'developer','content':instructions},{'role':'user','content':json.dumps({'question':question,'facts':facts},ensure_ascii=False)}]
 if len(json.dumps(msg,ensure_ascii=False).encode())>6000:raise ValueError('Input byte bound exceeded; no model submission')
 return msg
def render(snapshot,budgets=False):
 from PIL import Image,ImageDraw,ImageFont
 fontpath='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
 boldpath='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
 if os.name=='nt':fontpath='C:/Windows/Fonts/arial.ttf';boldpath='C:/Windows/Fonts/arialbd.ttf'
 f=lambda n,b=False:ImageFont.truetype(boldpath if b else fontpath,n)
 im=Image.new('RGB',(2200,1500),'#edf3f7');d=ImageDraw.Draw(im);d.rectangle((0,0,2200,175),fill='#193e52')
 d.text((30,25),'ООО VESCHI · облачный пилот · '+('бюджеты'if budgets else'реклама'),font=f(38,True),fill='white')
 d.text((30,88),'Кэш: '+snapshot['observed_msk']+' · день05.11 / 3дня03–05.11 · KGS',font=f(27),fill='white')
 heads=['РК','Остаток KGS','Расход день / 3дня','ДРР день / 3дня']if budgets else['РК','Расход день / 3дня','Заказы день / 3дня','ДРР день / 3дня']
 xs=[30,450,1060,1610]
 for x,t in zip(xs,heads):d.text((x,205),t,font=f(26,True),fill='#193e52')
 ratio=lambda spend,amount:'—'if not float(amount)else f'{float(spend)/float(amount)*100:.2f}%'
 for j,r in enumerate(snapshot['campaigns']):
  y=270+j*76;d.rounded_rectangle((15,y-10,2185,y+55),8,fill='white')
  spend=f"{float(r['spend_day']):.2f} / {float(r['spend3']):.2f}"
  vals=[r['cid'],str(snapshot['budgets'][r['cid']]),spend,ratio(r['spend_day'],r['amount_day'])+' / '+ratio(r['spend3'],r['amount3'])]if budgets else[r['cid'],spend,str(r['orders_day'])+' / '+str(r['orders3']),ratio(r['spend_day'],r['amount_day'])+' / '+ratio(r['spend3'],r['amount3'])]
  for x,t in zip(xs,vals):d.text((x,y),t,font=f(27),fill='#172c38')
 y=990;t=snapshot['totals'];day=t['day'];three=t['three'];d.rounded_rectangle((15,y,2185,y+155),10,fill='#193e52')
 for off,txt in [(15,'ИТОГО · весь кабинет ООО · 9 РК'),(65,f"Расход день {day['sum']:.2f} KGS / 3дня {three['sum']:.2f} KGS"),(110,'ДРР день '+ratio(day['sum'],day['sum_price'])+' / 3дня '+ratio(three['sum'],three['sum_price']))]:d.text((30,y+off),txt,font=f(29,True),fill='white')
 notes=['Только проверка облачного пути по датированному кэшу. Не новый торговый отчёт.', 'Модель не формировала изображение. Новых запросов WB и действий в кабинете нет.', 'Пополнения не предлагаются и не выполняются.'if budgets else'Итог РК не заменён прямыми SKU; отсутствие заказов не равно ДРР0%.']
 for i,txt in enumerate(notes):d.text((30,1180+i*45),txt,font=f(25),fill='#506776')
 b=io.BytesIO();im.crop((0,0,2200,1340)).save(b,format='PNG');return b.getvalue()
def send_once(cache,key,method,send,chat_id,body,files=None):
 prior=cache.get(key)
 if prior:
  if prior.get('status')=='sent':return prior
  raise RuntimeError('Delivery unresolved; no blind resend')
 cache.once(key,{'status':'submitting','chat_id':chat_id,'submitted_at':stamp()})
 try:
  value=send(method,body,files)
  if value.get('chat',{}).get('id')!=chat_id or type(value.get('message_id'))is not int:raise ValueError('Delivery response not scoped')
 except Exception:
  cache.update(key,{'status':'uncertain','chat_id':chat_id,'observed_at':stamp()});raise RuntimeError('Delivery outcome uncertain; no resend')from None
 receipt={'status':'sent','chat_id':chat_id,'message_id':value['message_id'],'telegram_date':value.get('date'),'sent_at':stamp()}
 cache.update(key,receipt);return receipt
def binding_resume_allowed(prior,artifacts):
 return bool(prior and prior.get('status')=='attention'and prior.get('last_stage')=='starting'and prior.get('model_calls')==0 and prior.get('safe_error')=='Expected one authorized pilot group command'and not any(artifacts))
def run(resume_binding=False):
 cache=Cache();policy=cache.get(ROOT+':authorization')or{}
 if policy.get('approved')is not True or policy.get('maximum_cloud_runs')!=1 or policy.get('wb_actions_enabled')is not False or policy.get('schedules_enabled')is not False:raise PermissionError('Exact pilot-only consent missing')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(policy['expires_at']):raise PermissionError('Pilot consent expired')
 state_key=ROOT+(':execution:binding_continuation'if resume_binding else':execution')
 if resume_binding:
  prior=cache.get(ROOT+':execution');artifacts=[cache.get(ROOT+':'+k)for k in ['budget','model_receipt','inbox','outbox','delivery:answer']]
  if not binding_resume_allowed(prior,artifacts):raise PermissionError('Binding continuation requires known uncharged unsent failure')
 if cache.get(state_key):print('Existing pilot retained; no repeated call or send');return
 state={'status':'starting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':stamp(),'model_calls':0,'wb_calls':0,'schedule_changes':0,'continuation_of':ROOT+':execution'if resume_binding else None};cache.once(state_key,state)
 token=os.environ['OOO_TELEGRAM_BOT_TOKEN'].strip()
 def tg(method,body=None,files=None):
  import requests
  allowed={'getMe','getWebhookInfo','getUpdates','getChatMember','sendMessage','sendPhoto'}
  if method not in allowed:raise PermissionError('Telegram pilot boundary')
  response=requests.post('https://api.telegram.org/bot'+token+'/'+method,data=body or{},files=files,timeout=(10,45),allow_redirects=False)
  if response.status_code!=200:raise RuntimeError('telegram_http_'+str(response.status_code))
  j=response.json()
  if not j.get('ok'):raise RuntimeError('Telegram response rejected')
  return j['result']
 try:
  bot=tg('getMe')
  if not bot.get('is_bot')or bot.get('username','').casefold()!=policy['expected_username'].casefold():raise PermissionError('Unexpected bot identity')
  hook=tg('getWebhookInfo')
  if hook.get('url'):raise RuntimeError('Existing webhook; discovery requires review, no changes made')
  trigger=select_trigger(tg('getUpdates',{'limit':20,'timeout':0,'allowed_updates':json.dumps(['message'])}),policy)
  if tg('getChatMember',{'chat_id':trigger['chat_id'],'user_id':trigger['sender_id']}).get('status')not in('creator','administrator'):raise PermissionError('Pilot sender is not group owner/admin')
  cache.once(ROOT+':inbox',{'status':'claimed','received_at':stamp(),**trigger})
  state.update(status='group_bound',bot_id=bot['id'],chat_id=trigger['chat_id'],input_message_id=trigger['input_message_id']);cache.update(state_key,state)
  msg=model_message(policy);rates=SOL_RATES;reserve=(Decimal(10000)*Decimal(str(rates['input']))+Decimal(2000)*Decimal(str(rates['output'])))/Decimal(1000000)
  if reserve>Decimal(str(policy['migration_cap_usd']))or reserve>Decimal('0.20'):raise PermissionError('Prepaid reservation exceeds consent')
  cache.once(ROOT+':budget',{'status':'reserved','reserved_usd':str(reserve),'cap_usd':policy['migration_cap_usd'],'reserved_at':stamp(),'model_calls_allowed':1})
  state.update(status='model_submitting',model_calls=1,reserved_usd=str(reserve),input_bytes=len(json.dumps(msg,ensure_ascii=False).encode()));cache.update(state_key,state)
  from openai import OpenAI
  start=time.monotonic()
  response=OpenAI(max_retries=0,timeout=90).responses.create(model=MODEL,input=msg,max_output_tokens=2000,reasoning={'effort':'low'},store=False,tools=[],extra_headers={'Idempotency-Key':ROOT})
  usage=response.usage.model_dump();actual=cost(usage,rates)
  cache.once(ROOT+':model_receipt',{'response_id':response.id,'model':response.model,'status':response.status,'usage':usage,'calculated_cost_usd':str(actual),'cost_basis':'actual API tokens multiplied by approved standard tariff, not invoice settlement','seconds':round(time.monotonic()-start,3),'received_at':stamp()})
  cache.update(ROOT+':budget',{'status':'settled','reserved_usd':str(reserve),'calculated_spend_usd':str(actual),'released_usd':str(max(Decimal(0),reserve-actual)),'cap_usd':policy['migration_cap_usd']})
  if actual>reserve:raise RuntimeError('Actual usage exceeds reservation; no further model calls')
  answer=response.output_text
  if response.status!='completed'or not answer or len(answer)>2200:raise RuntimeError('Model completion outside bounded answer contract')
  cache.once(ROOT+':outbox',{'status':'ready','chat_id':trigger['chat_id'],'answer':answer,'created_at':stamp()})
  state.update(status='delivering',calculated_model_cost_usd=str(actual),input_tokens=usage['input_tokens'],output_tokens=usage['output_tokens']);cache.update(state_key,state)
  text='Облачный пилот ООО VESCHI\n\n'+answer+f"\n\nПилот: {usage['input_tokens']} входных / {usage['output_tokens']} выходных токенов; расчёт по тарифу ${actual:.6f}. WB не менялся. Расписания выключены."
  receipts=[send_once(cache,ROOT+':delivery:answer','sendMessage',tg,trigger['chat_id'],{'chat_id':trigger['chat_id'],'text':text,'reply_parameters':json.dumps({'message_id':trigger['input_message_id'],'allow_sending_without_reply':False})})]
  images=[]
  for kind,budgets in [('advertising',False),('budgets',True)]:
   data=render(policy['snapshot'],budgets);images.append({'kind':kind,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
   receipts.append(send_once(cache,ROOT+':delivery:'+kind,'sendPhoto',tg,trigger['chat_id'],{'chat_id':trigger['chat_id'],'caption':'Пилот · '+('бюджеты'if budgets else'реклама')+' · датированный кэш, без изменений'},files={'photo':(kind+'.png',data,'image/png')}))
  cache.once(ROOT+':images',{'artifacts':images,'model_used_for_images':False})
  cache.update(ROOT+':outbox',{'status':'delivered','chat_id':trigger['chat_id'],'answer':answer,'message_ids':[v['message_id']for v in receipts],'delivered_at':stamp()})
  state.update(status='verified',message_ids=[v['message_id']for v in receipts],images=images,cache_read_payload_bytes=cache.read_bytes,cache_write_payload_bytes=cache.write_bytes,byte_counters_basis='application payload estimates, not Supabase billing egress',finished_at=stamp(),seconds=round(time.monotonic()-started,3))
  cache.update(state_key,state)
 except Exception as e:
  safe=str(e)[:160]if isinstance(e,(ValueError,RuntimeError,PermissionError))else None
  state.update(status='attention',error_type=type(e).__name__,error_code=getattr(e,'code',None),http_status=getattr(e,'status_code',None),safe_error=safe,failed_at=stamp(),last_stage=state.get('status'));cache.update(state_key,state)
  print('Pilot stopped; private receipt preserved; no automatic retry');return
 print('Pilot verified; private delivery and usage receipts saved')
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Expected main repository')
 started=time.monotonic();run(resume_binding='--continue-binding'in sys.argv)

