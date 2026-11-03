"""Owner-requested corrected report; bounded reads and exact Telegram publication only."""
import os,json,copy,base64,hashlib
from datetime import datetime,timezone,timedelta
from urllib.parse import quote
from china_price_apply import IO
from china_advertising_v2 import collect,sums,event_time,MSK
from china_advertising_midday import prepare_midday,only_completed_day_actions,render_midday
from china_midday_completed_review import include_closed,attach
from china_advertising_delivery import deliver,telegram_sender,CHAT,BOT
from china_daily_ad_actions import plan,bind
ROOT='china_agent:owner_midday_corrected:2026-11-03:v1'
DAY='2026-11-03'
def stamp():return datetime.now(timezone.utc).isoformat()
class ReadIO(IO):
 def wb(self,path,method='GET',body=None):
  if method!='GET':raise ValueError('No WB writes in corrected report')
  return super().wb(path,method,body)
def save(io,key,value):
 old=io.get(key)
 if old is None:
  if not io.create(key,value):raise ValueError('Concurrent correction')
 else:io.put(key,value)
def prepare(io):
 if io.get(ROOT+':artifacts'):print('Already prepared');return
 state=dict(status='preparing',started_at=stamp(),wb_writes=0,telegram_calls=0);save(io,ROOT+':preparation',state)
 try:
  current=include_closed(io,collect(io,DAY,current=True),DAY)
  if current.get('cabinet')!='token_3' or current.get('status')!='complete':raise ValueError('Wrong/incomplete current source')
  b=only_completed_day_actions(attach(io,prepare_midday(io,DAY,current),DAY))
  if set(b.get('recommendation_directions',{}))!={'raise','add','reduce','exclude'}:raise ValueError('Four-direction review absent')
  unknown=[c['id']for c in b['campaigns']if c['today']is None]
  known=sums([c['today']for c in b['campaigns']if c['today']is not None])
  pointer=io.get('china_agent:hourly_sales_api:v1:latest')or{}
  snap=io.get(pointer.get('source_key',''))or{}
  prior=(snap.get('advertising')or{}).get('totals')or{}
  if prior.get('spend_cny',0)>0 and known['spend']<prior['spend_cny']*.8:raise ValueError('Current advertising data collapsed versus dated hourly snapshot')
  # Current report, completed-day action evidence and own economics remain distinct.
  b['correction_of_message_ids']=[661];b['fresh_current_totals']=known;b['current_unknown_campaigns']=unknown
  if unknown:raise ValueError('Current advertising campaign coverage incomplete: '+','.join(map(str,unknown)))
  completed=io.get('china_agent:advertising_midday_completed:'+DAY+':v1')
  if not completed or completed.get('status')!='complete':raise ValueError('Completed review missing')
  # Save the exact completed source used, independent of the mutable canonical pointer.
  if not io.create(ROOT+':completed_review',completed):raise ValueError('Completed review already frozen')
  fs=render_midday(b);files=[]
  for index,f in enumerate(fs):
   p=plan(io,DAY,f,index,slot='midday-corrected-owner3')
   files.append(dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],action_count=len(p['items']),sha256=hashlib.sha256(f['bytes']).hexdigest(),b64=base64.b64encode(f['bytes']).decode()))
  art=dict(status='prepared',day=DAY,observed_at=b['observed_at'],prepared_at=stamp(),bundle=b,files=files,wb_writes=0)
  if not io.create(ROOT+':artifacts',art):raise ValueError('Concurrent artifacts')
  state.update(status='prepared',completed_at=stamp(),page_count=len(files),totals=known,directions=b['recommendation_directions'],growth_review=b.get('growth_review'),unknown_campaigns=unknown);save(io,ROOT+':preparation',state)
  print('Prepared privately; Telegram not sent')
 except Exception as ex:
  state.update(status='blocked',error=type(ex).__name__+': '+str(ex),completed_at=stamp());save(io,ROOT+':preparation',state);raise
def review_prepared(io):
 if io.get(ROOT+':reviewed_artifacts'):print('Already reviewed');return
 from china_advertising_economic_review import apply
 from china_advertising_directions import attach as attach_directions
 from china_midday_completed_review import merge_completed
 art=io.get(ROOT+':artifacts');completed=io.get(ROOT+':completed_review')
 if not art or not completed:raise ValueError('Prepared source missing')
 source=completed['source'];old=completed['review']
 minima={str(c['id'])+':'+str(r['nm']):r['minimum_bid_minor']for c in old['campaigns']for r in c.get('focus',[])if type(r.get('minimum_bid_minor'))is int}
 reviewed=attach_directions(apply(old,source,minima),source)
 if reviewed.get('economic_review_complete')is not True:raise ValueError('Reviewed economics incomplete')
 if not io.create(ROOT+':reviewed_completed',dict(source=source,review=reviewed,status='complete',observed_at=stamp(),wb_writes=0)):raise ValueError('Concurrent reviewed source')
 b=only_completed_day_actions(merge_completed(art['bundle'],reviewed,ROOT+':reviewed_completed'))
 files=[]
 for index,f in enumerate(render_midday(b)):
  p=plan(io,DAY,f,index,slot='midday-corrected-owner3-reviewed')
  files.append(dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],action_count=len(p['items']),sha256=hashlib.sha256(f['bytes']).hexdigest(),b64=base64.b64encode(f['bytes']).decode()))
 for f in art['files']:
  key='china_agent:loss_plan:v1:'+f['plan_id'];p=io.get(key)
  if p and not p.get('report_message_ids'):
   p.update(invalidated_at=stamp(),invalidation_reason='Superseded by owner final evidence review before any delivery');io.put(key,p)
 value=dict(art,bundle=b,files=files,reviewed_at=stamp())
 if not io.create(ROOT+':reviewed_artifacts',value):raise ValueError('Concurrent reviewed artifacts')
 total=b['fresh_current_totals'];t=event_time(b['observed_at']).astimezone(MSK).strftime('%H:%M')
 reply='На '+t+' МСК: расходы '+f"{total['spend']:.2f}".replace('.',',')+' CNY, ДРР '+f"{100*total['spend']/total['amount']:.2f}".replace('.',',')+'%.'
 manifest=dict(status='reviewed',observed_at=b['observed_at'],artifact_sha256=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),page_count=len(files),action_count=sum(f['action_count']for f in files),directions={k:{x:v.get(x)for x in ['status','count','note']}for k,v in b['recommendation_directions'].items()},totals=total,pavel_reply=reply,wb_writes=0,telegram_calls=0)
 if not io.create(ROOT+':review_manifest',manifest):raise ValueError('Concurrent manifest')
 print('Reviewed privately; no Telegram sends')

def publish(io,a):
 art=io.get(ROOT+':reviewed_artifacts')
 if not art or art.get('status')!='prepared':raise ValueError('Reviewed artifacts missing')
 if (datetime.now(timezone.utc)-event_time(art['observed_at'])).total_seconds()>1800:raise ValueError('Prepared source stale; do not publish')
 if a.get('artifact_sha256')!=hashlib.sha256(json.dumps(art,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest():raise ValueError('Reviewed artifact hash mismatch')
 files=[]
 for f in art['files']:
  raw=base64.b64decode(f['b64'],validate=True)
  if hashlib.sha256(raw).hexdigest()!=f['sha256']:raise ValueError('PNG hash mismatch')
  cap='Китай · исправленный промежуточный отчёт · 03.11 · '+str(f['page'])+'/'+str(f['total'])+'. Заменяет отчёт №661. '
  cap+=('Ответьте «Сделай всё» для '+str(f['action_count'])+' новых действий только этого PNG.'if f['action_count']else'Новых действий для исполнения нет.')
  files.append(dict(f,bytes=raw,caption=cap))
 delivery=deliver(io,DAY,files,telegram_sender(io),binder=lambda f,r:bind(io,f,r),delivery_key=ROOT+':delivery',expected_families={'drr'})
 if delivery.get('status')!='delivered' or any(p.get('status')!='sent' or not p.get('message_id')for p in delivery['parts']):raise ValueError('Report delivery incomplete')
 # Update the current report pointers only after all parts have actual receipts.
 for key in ['china_agent:advertising_midday_artifacts:'+DAY+':v1','china_agent:advertising_midday_delivery:'+DAY+':v1']:
  old=io.get(key)
  if not io.get(ROOT+':original:'+key):io.create(ROOT+':original:'+key,old)
 canonical_art=dict(art,status='frozen',correction_root=ROOT)
 io.put('china_agent:advertising_midday_artifacts:'+DAY+':v1',canonical_art)
 io.put('china_agent:advertising_midday_delivery:'+DAY+':v1',dict(delivery,correction_root=ROOT,replaces_message_ids=[661]))
 key=ROOT+':pavel_reply';prior=io.get(key)
 text=a['pavel_reply']
 if not prior:
  prior=dict(status='sending',chat_id=CHAT,reply_to_message_id=662,answer=text,created_at=stamp())
  if not io.create(key,prior):raise ValueError('Concurrent Pavel reply')
  try:
   r=io.tg('sendMessage',dict(chat_id=CHAT,reply_parameters=dict(message_id=662,allow_sending_without_reply=False),text=text,disable_web_page_preview=True))
   if r.get('chat',{}).get('id')!=CHAT or type(r.get('message_id'))is not int:raise ValueError('Reply target receipt mismatch')
   prior.update(status='sent',message_id=r['message_id'],receipt=r,sent_at=stamp());io.put(key,prior)
  except Exception:
   prior['status']='uncertain';io.put(key,prior);raise RuntimeError('Uncertain reply; never resend blindly')from None
 if prior.get('status')!='sent':raise ValueError('Previous reply uncertain; manual review required')
 resolution=dict(status='answered_by_owner',chat_id=CHAT,message_id=prior['message_id'],receipt_key=key,answer=text,recorded_at=stamp())
 save(io,'china_agent:owner_dialog_resolution:v1:job:232',resolution)
 result=dict(status='delivered',completed_at=stamp(),report_message_ids=[p['message_id']for p in delivery['parts']],pavel_reply_message_id=prior['message_id'],reply_receipt_key=key,wb_writes=0)
 save(io,ROOT+':result',result);print(json.dumps(result))
def main():
 io=ReadIO();a=io.get(ROOT+':approval')or{}
 if a.get('owner_user_id')!=5122667182 or a.get('chat_id')!=CHAT or a.get('bot_id')!=BOT or a.get('wb_writes_authorized')is not False or datetime.now(timezone.utc)>=event_time(a.get('expires_at')):raise ValueError('Current owner scope missing')
 if datetime.now(MSK).date().isoformat()!=DAY:raise ValueError('Dated correction only')
 if a.get('phase')=='prepare_fast':prepare(io)
 elif a.get('phase')=='review_fast':review_prepared(io)
 elif a.get('phase')=='publish_fast':publish(io,a)
 else:raise ValueError('Unknown correction phase')
if __name__=='__main__':main()
