"""Prepare/apply exact cohort percent prices via existing verified price engine."""
import base64,hashlib,json,os,sys,requests
from datetime import datetime,timezone
from decimal import Decimal
from china_price_apply import IO,plan,process,PREFIX,POLICY,day,sha
from china_zero_order_price_command import ROOT,handle
from china_zero_orders_correction28 import W
CHAT=-1004342917488;BOT=8780468043
def render(rows,title,percent):
 from PIL import Image,ImageDraw,ImageFont
 import io
 def font(n,b=False):
  for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf','C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf')]:
   try:return ImageFont.truetype(p,n)
   except OSError:pass
  return ImageFont.load_default(size=n)
 parts=[rows[i:i+22] for i in range(0,len(rows),22)];out=[]
 for page,part in enumerate(parts,1):
  im=Image.new('RGB',(1900,400+len(part)*75),'#eef3f7');d=ImageDraw.Draw(im);d.rectangle((0,0,1900,170),fill='#193e52');d.text((35,25),title,font=font(34,True),fill='white');d.text((35,85),str(len(rows))+' товаров из списка без заказов · +'+percent+'% · цена продавца, CNY · '+str(page)+'/'+str(len(parts)),font=font(24),fill='white')
  for x,t in [(35,'Артикул'),(900,'Было, ¥'),(1130,'Цель, ¥'),(1380,'Статус')]:d.text((x,195),t,font=font(24,True),fill='#193e52')
  for i,r in enumerate(part):
   y=235+i*75;d.rounded_rectangle((20,y-2,1880,y+64),8,fill='white');s=r.get('selection',r)
   status={'ready':'Готово к применению','applied':'Проверено в WB','already_at_target':'Уже установлена','blocked':'Не изменено','failed':'Не подтверждено','unavailable':'Не изменено'}.get(r.get('status'),str(r.get('status')))
   if r.get('reason'):d.text((35,y+43),r['reason'][:140],font=font(17),fill='#9b3434')
   for x,t in [(35,s['article']),(900,str(s.get('current_cny','?'))),(1130,str(s.get('target_cny','?'))),(1380,status)]:d.text((x,y+12),t,font=font(23),fill='#111111')
  y=255+len(part)*75;d.text((35,y),'Ровно запрошенный процент, без округления. Прочие товары не затрагиваются.',font=font(22),fill='#455568');d.text((35,y+35),'Неподтвержденные значения не считаются выполнением; результат по WB в журнале.',font=font(22),fill='#455568')
  b=io.BytesIO();im.save(b,format='PNG');out.append(dict(b64=base64.b64encode(b.getvalue()).decode(),sha256=hashlib.sha256(b.getvalue()).hexdigest(),page=page,total=len(parts)))
 return out

def working(io,key):
 k=key+':working'
 if io.get(k):return
 io.create(k,dict(status='sending'))
 r=io.tg('sendMessage',dict(chat_id=CHAT,text='Павел, предыдущий ответ ошибочно повторил список вместо вашей команды. Цены тем ответом не менялись. Исправляю обработку: ровно +30% к цене продавца для всех 72 товаров из списка, включая товары без остатка. Точные цены и результат проверю в WB; неподтвержденное не выдам за выполненное.',reply_parameters=dict(message_id=415,allow_sending_without_reply=False)))
 if r['chat']['id']!=CHAT or r['from']['id']!=BOT:raise ValueError('Telegram identity')
 io.put(k,dict(status='sent',message_id=r['message_id'],receipt=r))

def prepare(io,job_id):
 job=io.db('business_agent_jobs?id=eq.'+str(job_id)+'&agent_id=eq.china&chat_id=eq.'+str(CHAT)+'&select=id,sender_id,request_text,created_at,tool_trace')[0]
 handle(W(io),job,[]);key=ROOT+str(job_id);e=io.get(key)
 if not e:raise ValueError('No exact price command')
 if e['status']!='requested':return e
 e['input_message_id']=next(t['message_id'] for t in job['tool_trace'] if t.get('name')=='china_saved_question' and t.get('bot_id')==BOT)
 if io.tg('getMe',{}).get('id')!=BOT:raise ValueError('Bot mismatch')
 member=io.tg('getChatMember',dict(chat_id=CHAT,user_id=e['actor_user_id']))
 if member.get('user',{}).get('is_bot') or member.get('status') not in ['member','administrator','creator']:raise ValueError('Human membership required')
 if job_id==155:working(io,key)
 data=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0');goods=data.get('listGoods',[])
 if len(goods)>=1000:raise ValueError('Price pagination incomplete')
 prices={str(p['nmID']):p for p in goods};ss=[];rows=[]
 for row in e['cohort']:
  p=prices.get(row['nm_id']);s=dict(row,action='Повышение');x=dict(selection=s,status='blocked')
  try:
   if not p or not p.get('sizes'):raise ValueError('Текущая карточка/цена WB отсутствует')
   old=Decimal(str(p['sizes'][0]['discountedPrice']));target=old*(1+Decimal(e['percent'])/100)
   s.update(current_cny=str(old),target_cny=str(target),base_cny=str(p['sizes'][0]['price']),seller_discount=p['discount'],club_discount=p.get('clubDiscount'))
   if target!=target.quantize(Decimal('.01')):raise ValueError('Точный процент требует долей копейки; округление не согласовано')
   req=plan(s,p);ss.append(s);x.update(status='ready',request=req)
  except ValueError as ex:x['reason']=str(ex)
  rows.append(x)
 keyhash=sha(json.dumps(dict(command=e['signature'],selections=ss),sort_keys=True));ak=PREFIX+str(CHAT)+':'+str(job_id)+':'+str(e['actor_user_id'])+':'+keyhash
 a=dict(schema_version=2,execution_authorized=True,execution_policy=POLICY,approval_policy='all_current_human_group_members',decision='approved_recommendation',chat_id=CHAT,bot_id=BOT,report_job_id=job_id,report_date=day(),report_sha256=sha(job['request_text']),actor_user_id=e['actor_user_id'],created_at=datetime.now(timezone.utc).isoformat(),selections=ss,basis='explicit_zero_order_percent',approval_key=ak)
 e.update(status='prepared',selections=ss,rows=rows,approval_key=ak,prepared_at=datetime.now(timezone.utc).isoformat(),files=render(rows,'Точные цены по команде участника',e['percent']),prepared_approval=a)
 io.put(key,e)

 return e

def deliver(io,key,e):
 for i,f in enumerate(e['files']):
  k=key+':result:'+str(i);prior=io.get(k)
  if prior:
   if prior.get('status')=='sent':continue
   raise ValueError('Telegram uncertain; no retry')
  if not io.create(k,dict(status='sending',sha256=f['sha256'])):raise ValueError('Notice race')
  body=base64.b64decode(f['b64']);n=sum(r['status'] in ['applied','already_at_target'] for r in e['rows']);b=len(e['rows'])-n
  caption='Команда +'+e['percent']+'%: WB проверено '+str(n)+' из '+str(len(e['cohort']))+'. Не изменено/не подтверждено: '+str(b)+'. '+str(i+1)+'/'+str(len(e['files']))+'. Полный журнал сохранен; повторных изменений нет.'
  r=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data=dict(chat_id=CHAT,caption=caption,reply_parameters=json.dumps(dict(message_id=e['input_message_id'],allow_sending_without_reply=False))),files={'photo':('prices.png',body,'image/png')},timeout=45).json()
  if not r.get('ok'):raise ValueError('Telegram failed; no repeat')
  r=r['result']
  if r['chat']['id']!=CHAT or r['from']['id']!=BOT:raise ValueError('Receipt mismatch')
  io.put(k,dict(status='sent',message_id=r['message_id'],receipt=r,sha256=f['sha256']))
 e['notice_status']='sent';io.put(key,e)

def apply(io,job_id,review=False):
 key=ROOT+str(job_id);e=io.get(key)
 if not e or e['status'] not in ['prepared','applied','partial','uncertain']:raise ValueError('Prepared command required')
 if review and e.get('visual_review')!='approved':raise ValueError('Review required')
 if e['status']=='prepared':
  if e['selections'] and not io.get(e['approval_key']):io.create(e['approval_key'],e['prepared_approval'])
  result=process(io,e['approval_key'],polls=12) if e['selections'] else dict(status='done',items=[])
  by={x['selection']['nm_id']:x for x in result.get('items',[])}
  for r in e['rows']:
   if r['selection']['nm_id'] in by:r.update(by[r['selection']['nm_id']])
  verified=sum(r['status'] in ['applied','already_at_target'] for r in e['rows'])
  e.update(status='applied' if verified==len(e['cohort']) else ('uncertain' if result['status'] in ['submitted','uncertain'] else 'partial'),execution_key='china_agent:price_execution:v1:'+e['approval_key'][len(PREFIX):],completed_at=datetime.now(timezone.utc).isoformat())
  e['files']=render(e['rows'],'Результат проверки цен WB',e['percent']);io.put(key,e)
 if e.get('notice_status')!='sent':deliver(io,key,e)
 return e

def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=IO();args=sys.argv[1:]
 if args==['--drain']:
  pending=io.db('telegram_api_cache?cache_key=like.'+ROOT+'*&payload->>status=eq.requested&select=cache_key&limit=5')
  for row in pending:
   job_id=int(row['cache_key'][len(ROOT):]);prepare(io,job_id);apply(io,job_id)
  return
 cfg=json.load(open('ops/china-price155-trigger.json'));job_id=cfg['job_id'];e=prepare(io,job_id) if cfg['mode']=='prepare' else apply(io,job_id,review=True)
 print(json.dumps(dict(status=e['status'],ready=len(e['selections']),blocked=[dict(article=r['selection']['article'],reason=r.get('reason')) for r in e['rows'] if r['status']=='blocked']),ensure_ascii=False))
if __name__=='__main__':main()


