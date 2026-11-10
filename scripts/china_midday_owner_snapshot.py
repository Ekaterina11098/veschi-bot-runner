"""Publish the owner's exact reviewed private snapshot. No model or WB calls."""
import base64,copy,hashlib,json
from datetime import datetime,timezone

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def publish(io,day):
 key='china_agent:advertising_midday_owner_approved:'+day+':v1'
 approval=io.get(key)or{}
 if approval.get('status')!='approved':return None
 if approval.get('owner_id')!=5122667182 or approval.get('chat_id')!=-1004342917488 or approval.get('scope')!='publish_report_only':raise ValueError('Owner snapshot approval scope mismatch')
 b=copy.deepcopy(approval['bundle'])
 if b.get('day')!=day or digest(b)!=approval['bundle_sha256']:raise ValueError('Owner snapshot changed')
 actions=[r['action']for c in b['campaigns']for r in c.get('attention',[])]
 if digest(actions)!=approval['actions_sha256']:raise ValueError('Owner snapshot actions changed')
 from china_advertising_midday import render_midday
 from china_daily_ad_actions import plan,bind
 from china_advertising_delivery import deliver,telegram_sender
 art='china_agent:advertising_midday_artifacts:'+day+':owner-approved-v1'
 saved=io.get(art)
 if not saved:
  files=[]
  for i,f in enumerate(render_midday(b)):
   p=plan(io,day,f,i,slot='midday-owner-approved')
   files.append(dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],action_count=len(p['items']),b64=base64.b64encode(f['bytes']).decode()))
  saved=dict(status='frozen',day=day,bundle_sha256=approval['bundle_sha256'],approval_key=key,files=files,model_calls=0,wb_writes=0)
  if not io.create(art,saved):saved=io.get(art)
 if saved.get('bundle_sha256')!=approval['bundle_sha256']:raise ValueError('Frozen owner snapshot mismatch')
 delivery='china_agent:advertising_midday_delivery:'+day+':v1'
 prior=io.get(delivery)
 if prior and prior.get('status')=='blocked_by_owner_full_validation':
  if any(p.get('status')!='blocked_by_owner'or p.get('message_id')or p.get('receipt')for p in prior.get('parts',[])):raise ValueError('Prior delivery outcome unresolved; do not reset')
  archive=delivery+':before_owner_publish:'+approval['bundle_sha256']
  if not io.get(archive):io.create(archive,prior)
  io.put(delivery,dict(status='ready',day=day,chat_id=-1004342917488,parts=[],owner_publication_approval=key,created_at=datetime.now(timezone.utc).isoformat(),wb_writes=0))
 files=[]
 for f in saved['files']:
  caption='Китай · промежуточный отчёт · '+day+' · '+str(f['page'])+'/'+str(f['total'])+'. '
  caption+=('Ответьте «Сделай всё» для '+str(f['action_count'])+' новых действий только этого PNG.'if f['action_count']else'Новых действий для исполнения нет.')
  files.append(dict(f,bytes=base64.b64decode(f['b64'],validate=True),caption=caption))
 result=deliver(io,day,files,telegram_sender(io),binder=lambda f,r:bind(io,f,r),delivery_key=delivery,expected_families={'drr'})
 print(json.dumps(dict(status=result['status'],day=day,model_calls=0,wb_writes=0,parts=[dict(kind=p['kind'],message_id=p.get('message_id'),status=p['status'])for p in result['parts']])))
 return result