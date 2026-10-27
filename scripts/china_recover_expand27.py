"""Dated recovery of two unsubmitted approved bids, then publish a separate completed-day proposal."""
import os,json,copy,base64
from datetime import datetime,timezone
from urllib.parse import urlencode
import requests
from china_loss_execute import IO
from conversion_watches import Worker,RECEIPTS,question_marker
import china_bid_proposals as q
import china_advertising_plans as p
import china_cloud_cost_control as cloud
R='china_agent:bid_resume:dialog-ads-139-raise:remaining2:v1'
REQUEST='china_agent:completed_day_proposal:2026-10-27:v1:request'
RESULT='china_agent:completed_day_proposal:2026-10-27:v1:result'
CHAT=-1004342917488
def upsert(io,k,v):
 if io.get(k) is None:
  if not io.create(k,v):raise RuntimeError('Concurrent cache identity')
 else:io.put(k,v)
def recover(io):
 prior=io.get(R)
 if prior:return prior
 plan=io.get(p.P+'dialog-ads-139-raise');a=io.get(p.A+'dialog-ads-139-raise');old=io.get(p.E+'dialog-ads-139-raise')
 if not plan or not a or not old:raise ValueError('Original approval absent')
 io.validate_owner(a)
 if plan.get('invalidated_at') or plan['plan_sha256']!=p.digest(plan['items']) or a['plan_sha256']!=plan['plan_sha256'] or datetime.now(timezone.utc)>datetime.fromisoformat(plan['expires_at']):raise ValueError('Original plan invalid')
 done=[s for s in old['items'] if s['status']=='verified']
 remaining=[s for s in old['items'] if s['status']=='blocked' and s.get('reason')=='WB advertising HTTP 429']
 wanted={1473243902,1473244341}
 if {s['item']['nm_id'] for s in remaining}!=wanted or len(done)!=2 or old.get('plan_sha256')!=plan['plan_sha256'] or any(s['item'] not in plan['items'] or s['index'] not in [1,2] for s in remaining) or any(k.startswith(('1:','2:')) for k in old['steps']):raise ValueError('Only never-submitted exact two bids may resume')
 e=dict(status='preflight',plan_id=plan['plan_id'],approval_job_id=a['job_id'],source_execution=p.E+plan['plan_id'],items=[],wb_writes=0,created_at=p.iso(),plan_sha256=plan['plan_sha256'])
 if not io.create(R,e):raise ValueError('Recovery exists')
 wb=cloud.WB()
 try:
  cid=41270309;before=wb.campaigns([cid])[str(cid)]
  if before['status']!=9 or before['currency']!='CNY' or before['settings']['placements']!=dict(search=False,recommendations=True):raise ValueError('Campaign changed')
  ns={n['nm_id']:n for n in before['nm_settings']}
  ec=[s['item'] for s in remaining];prices=io.prices([str(i['nm_id']) for i in ec]);stock=q.fresh_stock({},[i['article'] for i in ec])
  need=[]
  for i in ec:
   if i['nm_id'] not in ns or ns[i['nm_id']]['bids_kopecks']['recommendations'] not in [i['old_minor'],i['target_minor']]:raise ValueError('Exact rate changed')
   pr=prices[str(i['nm_id'])];st=[s for s in stock if s.get('article')==i['article']]
   if pr.get('currencyIsoCode4217')!='CNY' or pr.get('vendorCode')!=i['article'] or pr['sizes'][0]['discountedPrice']!=i['economics']['seller_price_cny'] or len(st)!=1 or st[0]['stock']-st[0]['reserve']<=0 or st[0]['price']!=i['economics']['cogs_kopecks']:raise ValueError('Price/COGS/stock changed')
   if ns[i['nm_id']]['bids_kopecks']['recommendations']!=i['target_minor']:need.append(i)
  if need:
   mins=wb.minimums(cid,[i['nm_id'] for i in need],'recommendations')
   if any(mins[i['nm_id']]>i['target_minor'] for i in need):raise ValueError('Minimum changed')
   current=io.get(p.P+plan['plan_id'])
   if current.get('invalidated_at') or current['plan_sha256']!=plan['plan_sha256'] or datetime.now(timezone.utc)>datetime.fromisoformat(plan['expires_at']):raise ValueError('Plan revoked')
   e.update(status='submitting',before=before,request=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm_id'],placement='recommendations',bid_kopecks=i['target_minor']) for i in need])]))
   io.put(R,e)
   wb.req('/api/advert/v1/bids','PATCH',e['request'],write=True);e['wb_writes']=1
  after=wb.campaigns([cid])[str(cid)];expected=p.members(before)
  for i in ec:expected[str(i['nm_id'])]['bids']['recommendations']=i['target_minor']
  if p.members(after)!=expected or after['settings']!=before['settings'] or after['status']!=before['status']:raise ValueError('Exact readback not verified')
  e.update(status='verified',before=before,after=after,items=[dict(status='verified',item=i) for i in ec],verified_at=p.iso());io.put(R,e)
  child=R+':'+str(cid)
  upsert(io,child,dict(status='verified',before=before,after=after,items=ec,verified_at=e['verified_at'],parent=R,approval_job_id=a['job_id']))
  reg=io.get('china_agent:verified_campaign_state:v1') or {};reg[str(cid)]=child;upsert(io,'china_agent:verified_campaign_state:v1',reg)
  io.put(p.A+plan['plan_id'],dict(a,reconciled_by=R,reconciled_status='verified',result_status='verified'))
 except Exception as error:
  e.update(status='uncertain' if e.get('status')=='submitting' else 'blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__);io.put(R,e)
 return e
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 io=IO()
 if io.tg('getMe',{})['id']!=8780468043:raise PermissionError('Bot identity')
 recovery=recover(io)
 correction=R+':telegram'
 if not io.get(correction):
  body=('Уточнение: прежний ответ об ошибке журнала был неполным. Зонт26:0,23→0,28 ¥ и сумка529:0,28→0,34 ¥ уже были выполнены и проверены WB. '+
   ('Оставшиеся531 и448:0,28→0,34 ¥ теперь тоже выполнены и проверены WB. Все 4 готовы; повторных повышений 26/529 не было.' if recovery['status']=='verified' else '531 и448 пока не подтверждены: '+recovery.get('reason',recovery['status'])+'. Повторных изменений 26/529 не было.'))
  if io.create(correction,dict(status='sending',text=body)):
   try:
    m=io.tg('sendMessage',dict(chat_id=CHAT,text=body,reply_parameters=dict(message_id=350,allow_sending_without_reply=True)));io.put(correction,dict(status='sent',message_id=m['message_id'],chat_id=CHAT,text=body))
   except Exception:io.put(correction,dict(status='uncertain',text=body))
 class ReadWB(cloud.WB):
  def req(self,path,method='GET',body=None,write=False):
   if write:raise PermissionError('Proposal read-only')
   return super().req(path,method,body,write=False)
 cloud.WB=ReadWB
 def db(method,table,params=None,body=None,prefer=None):
  if table not in ['telegram_api_cache','business_agent_jobs','business_agent_config']:raise PermissionError('DB scope')
  if table!='telegram_api_cache' and method!='GET':raise PermissionError('Jobs immutable')
  return io.db(table+('?' +urlencode(params) if params else ''),method,body,prefer)
 w=Worker(db,lambda *args:None);w.member_check=lambda actor:io.tg('getChatMember',dict(chat_id=CHAT,user_id=actor))
 req=w.get(REQUEST)
 if not req or req.get('authorized_by')!=5122667182:raise ValueError('Proposal request absent')
 jobs=db('GET','business_agent_jobs',params=dict(id='eq.'+str(req['job_id']),agent_id='eq.china',chat_id='eq.'+str(CHAT),select='*'))
 if len(jobs)!=1:raise ValueError('Question missing')
 job=jobs[0];w.active_question_id=job['id'];w.reply_id=question_marker(job)['message_id']
 result=q.prepare(w,job,req['nm_ids'],raise_percent=20,count=30)
 if result['status']!='ready':w.save(RESULT,dict(status='blocked',reason=result.get('note'),blocked=result.get('blocked')));print('Proposal blocked; saved exact reason');return
 plan=w.get(p.P+result['plan_id']);parts=plan['delivery_text'].split('\n[[ПРЕДЛОЖЕНИЯ]]\n') if plan.get('proposal_files') else [plan['text']]
 ids=[]
 for pos,part in enumerate(parts):
  k=RECEIPTS+'completed-days-proposal27:'+str(job['id'])+':'+str(pos);receipt=w.get(k)
  if receipt:
   if receipt['status']=='sent':ids.append(receipt['message_id']);q.bind_photo(w,part,receipt['message_id']) if part.startswith(q.PNG_PREFIX) else p.bind(w,part,receipt['message_id'])
   else:raise ValueError('Uncertain proposal part; no blind retry')
   continue
  receipt=dict(status='sending',text=part,chat_id=CHAT)
  if not w.save(k,receipt,insert=True):raise ValueError('Concurrent delivery')
  try:
   if part.startswith(q.PNG_PREFIX):
    blob,caption=q.photo(w,CHAT,part)
    caption='Дополнительный план +20%: '+str(len(plan['items']))+' товаров. Только завершённые дни24–26.10; сегодня исключено. Большинство — тесты малого трафика, их эффективность ещё не доказана. '+caption
    if len(caption)>1024:raise ValueError('Caption too long')
    rr=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data=dict(chat_id=CHAT,caption=caption,reply_parameters=json.dumps(dict(message_id=w.reply_id,allow_sending_without_reply=True))),files={'photo':('completed-day-bid-tests.png',blob,'image/png')},timeout=40).json()
    if not rr.get('ok'):raise RuntimeError('Telegram photo rejected')
    msg=rr['result']
   else:msg=io.tg('sendMessage',dict(chat_id=CHAT,text=part,reply_parameters=dict(message_id=w.reply_id,allow_sending_without_reply=True)))
   if msg.get('chat',{}).get('id')!=CHAT:raise ValueError('Wrong chat')
   receipt.update(status='sent',message_id=msg['message_id']);w.save(k,receipt);ids.append(msg['message_id'])
   if part.startswith(q.PNG_PREFIX):q.bind_photo(w,part,msg['message_id'])
   else:p.bind(w,part,msg['message_id'])
  except Exception:receipt['status']='uncertain';w.save(k,receipt);raise
 w.save(RESULT,dict(status='sent',plan_id=plan['plan_id'],items=len(plan['items']),message_ids=ids,recovery_status=recovery['status'],wb_new_proposal_writes=0,observed_at=p.iso()))
 print(json.dumps(dict(status='sent',items=len(plan['items']),message_ids=ids,recovery_status=recovery['status'])))
if __name__=='__main__':main()
