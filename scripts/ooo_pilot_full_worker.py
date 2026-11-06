"""One bounded report completion, using private cache and acknowledged Telegram photos."""
import os,json,time,datetime,hashlib
from decimal import Decimal
from openai import OpenAI
from ooo_cloud_pilot_20261106 import Cache,ROOT,stamp,cost,send_once
from ooo_pilot_full_renderer import render
CHILD=ROOT+':full_report'
def validate_decision(value,bundle):
 if set(value)!={'selected','assessment'}:raise ValueError('Unexpected decision fields')
 if not isinstance(value['selected'],list)or len(set(value['selected']))!=len(value['selected'])or not set(value['selected'])<=set(bundle['actions']):raise ValueError('Unscoped action')
 if not isinstance(value['assessment'],list)or not 1<=len(value['assessment'])<=6 or any(not isinstance(x,str)or len(x)>800 for x in value['assessment']):raise ValueError('Unbounded assessment')
 return value
def run():
 c=Cache();a=c.get(CHILD+':authorization')or{};original=c.get(ROOT+':authorization')or{};bound=c.get(ROOT+':execution:binding_continuation')or{}
 if a.get('approved')is not True or a.get('max_calls')!=1 or a.get('wb_actions_enabled')is not False or a.get('schedules_enabled')is not False:raise PermissionError('Exact continuation consent missing')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(original['expires_at']):raise PermissionError('Consent expired')
 if bound.get('status')!='verified':raise PermissionError('Original delivery binding missing')
 if c.get(CHILD+':execution'):print('Existing completion retained; no repeated paid call or delivery');return
 bundle=c.get(CHILD+':input');raw=json.dumps(bundle['model_facts'],ensure_ascii=False)
 instructions=bundle['instructions']
 messages=[{'role':'developer','content':instructions},{'role':'user','content':raw}]
 size=len(json.dumps(messages,ensure_ascii=False).encode())
 if size>16000:raise ValueError('Prompt byte limit')
 prior=c.get(ROOT+':model_receipt');spent=Decimal(prior['calculated_cost_usd']);cap=Decimal(str(a['migration_cap_usd']));rates=original['rates_per_million']
 reserve=(Decimal(16000)*Decimal(str(rates['input']))+Decimal(2000)*Decimal(str(rates['output'])))/1000000
 if spent+reserve>cap:raise PermissionError('Cumulative migration cap')
 state={'status':'model_submitting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':stamp(),'model_calls':1,'wb_calls':0,'schedule_changes':0,'input_bytes':size}
 c.once(CHILD+':execution',state);c.once(CHILD+':budget',{'status':'reserved','previous_spend_usd':str(spent),'reserved_usd':str(reserve),'cap_usd':str(cap)})
 try:
  started=time.monotonic();response=OpenAI(max_retries=0,timeout=90).responses.create(model=original['model'],input=messages,max_output_tokens=2000,reasoning={'effort':'low'},store=False,tools=[],extra_headers={'Idempotency-Key':CHILD})
  usage=response.usage.model_dump();actual=cost(usage,rates);total=spent+actual
  c.once(CHILD+':model_receipt',{'model':original['model'],'response_id':response.id,'usage':usage,'seconds':round(time.monotonic()-started,3),'calculated_cost_usd':str(actual),'cumulative_usd':str(total)})
  c.update(CHILD+':budget',{'status':'settled','actual_usd':str(actual),'previous_usd':str(spent),'cumulative_usd':str(total),'remaining_usd':str(cap-total),'cap_usd':str(cap)})
  if total>cap:raise RuntimeError('Cost cap reached; no further paid processing')
  decision=validate_decision(json.loads(response.output_text),bundle);c.once(CHILD+':decision',decision)
  chat=bound['chat_id'];token=os.environ['OOO_TELEGRAM_BOT_TOKEN']
  def tg(method,body=None,files=None):
   import requests
   if method not in('getMe','editMessageMedia','sendMessage'):raise PermissionError('Delivery-only boundary')
   res=requests.post('https://api.telegram.org/bot'+token+'/'+method,data=body or{},files=files,timeout=(10,60),allow_redirects=False)
   if res.status_code!=200 or not res.json().get('ok'):raise RuntimeError('Telegram operation not confirmed')
   return res.json()['result']
  bot=tg('getMe')
  if bot.get('username','').casefold()!=original['expected_username'].casefold():raise PermissionError('Unexpected bot')
  edits=[]
  for kind in ['advertising','budgets']:
   old=c.get(ROOT+':delivery:'+kind)or{}
   if old.get('status')!='sent'or old.get('chat_id')!=chat:raise PermissionError('Unconfirmed photo binding')
   data=render(bundle,decision,kind);key=CHILD+':delivery:'+kind
   if c.get(key):raise RuntimeError('Unresolved existing edit; no blind repeat')
   c.once(key,{'status':'submitting','chat_id':chat,'message_id':old['message_id'],'submitted_at':stamp()})
   try:
    media={'type':'photo','media':'attach://photo','caption':bundle['titles'][kind]+' · полный разбор; новые действия только предложения'}
    result=tg('editMessageMedia',{'chat_id':chat,'message_id':old['message_id'],'media':json.dumps(media,ensure_ascii=False)},{'photo':(kind+'.png',data,'image/png')})
    if result.get('message_id')!=old['message_id']or result.get('chat',{}).get('id')!=chat:raise RuntimeError('Photo edit not scoped')
   except Exception:
    c.update(key,{'status':'uncertain','chat_id':chat,'message_id':old['message_id'],'observed_at':stamp()});raise RuntimeError('Photo outcome uncertain; no blind repeat')from None
   receipt={'status':'edited_verified','chat_id':chat,'message_id':old['message_id'],'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'edited_at':stamp()};c.update(key,receipt);edits.append(receipt)
  answer=bundle['answer_prefix']+'\n\n'.join(bundle['actions'][i]['display']for i in decision['selected'])+'\n\n'+ '\n'.join(decision['assessment'])+'\n\n'+bundle['answer_totals']+f' Расход API этого продолжения ${actual}; весь пилот ${total} из$1 (по usage и тарифу; не итоговый счёт провайдера).'
  if len(answer)>4000:raise ValueError('Answer length bound')
  delivery=send_once(c,CHILD+':delivery:answer','sendMessage',tg,chat,{'chat_id':chat,'text':answer})
  state.update(status='verified',finished_at=stamp(),edits=edits,answer_delivery=delivery,selected=decision['selected'],cumulative_usd=str(total),app_cache_read_bytes=c.read_bytes,app_cache_write_bytes=c.write_bytes)
  c.update(CHILD+':execution',state)
 except Exception as e:
  state.update(status='attention',failed_at=stamp(),error_type=type(e).__name__);c.update(CHILD+':execution',state);print('Stopped; private receipts retained, no automatic retries');return
 print('Full report model analysis and acknowledged delivery completed')
if __name__=='__main__':run()

