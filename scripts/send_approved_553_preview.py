"""Send only the human-approved PNG and bind its single immutable pending action."""
import os,json,base64,hashlib,io
from datetime import datetime,timezone
import requests
from PIL import Image
from conversion_watches import runtime
KEY='china_agent:approved_553_delivery:2026-10-24:v1'
def main():
 w=runtime();p=w.get(KEY);plan=w.get('china_agent:loss_plan:v1:'+p['plan_id'])
 assert p['bot_id']==8780468043 and p['chat_id']==-1004342917488
 items=plan['items']
 assert len(items)==1 and items[0]['nm_id']==1473243455 and items[0]['campaign_id']==41055480 and items[0]['old_minor']==38 and items[0]['target_minor']==28 and items[0]['kind']=='ad_set_bid'
 digest=hashlib.sha256(json.dumps(items,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 assert digest==p['plan_sha256']==plan['plan_sha256']
 def stamp():return datetime.now(timezone.utc).isoformat()
 def tg(method,**kw):return requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()+'/'+method,timeout=45,**kw).json()
 if p['delivery_status'] in ('sending','uncertain'):raise SystemExit('Uncertain send: no blind retry')
 if p['delivery_status']!='sent':
  assert datetime.now(timezone.utc)<datetime.fromisoformat(plan['expires_at'])
  me=tg('getMe');chat=tg('getChat',json=dict(chat_id=p['chat_id']))
  assert me.get('ok') and me['result']['id']==p['bot_id'] and chat.get('ok') and chat['result']['id']==p['chat_id']
  chunks=[w.get(KEY+':chunk:'+str(i)) for i in range(p['chunks'])]
  assert all(c['index']==i and c['sha256']==p['sha256'] for i,c in enumerate(chunks))
  blob=base64.b64decode(''.join(c['data'] for c in chunks),validate=True)
  assert len(blob)==p['bytes'] and hashlib.sha256(blob).hexdigest()==p['sha256']
  Image.open(io.BytesIO(blob)).verify()
  p.update(delivery_status='sending',sending_at=stamp())
  claim=w.db('PATCH','telegram_api_cache',params={'cache_key':'eq.'+KEY,'payload->>delivery_status':'eq.ready'},body=dict(payload=p,updated_at=stamp()),prefer='return=representation')
  assert claim
  try:r=tg('sendPhoto',data=dict(chat_id=p['chat_id'],caption=p['caption']),files={'photo':('china-recommendations.png',blob,'image/png')})
  except Exception:
   p['delivery_status']='uncertain';w.save(KEY,p);raise SystemExit('Transport uncertain')
  if not r.get('ok'):
   p.update(delivery_status='rejected',error_code=r.get('error_code'));w.save(KEY,p);raise SystemExit('Telegram rejected')
  m=r['result'];assert m['chat']['id']==p['chat_id'] and m['from']['id']==p['bot_id']
  p.update(delivery_status='sent',message_id=m['message_id'],sent_at=stamp(),receipt=dict(message_id=m['message_id'],bot_id=m['from']['id'],chat_id=m['chat']['id'],date=m['date']))
  w.save(KEY,p)
 mid=p['message_id']
 plan['report_message_ids']=sorted(set(plan.get('report_message_ids',[])+[mid]));w.save('china_agent:loss_plan:v1:'+plan['plan_id'],plan)
 binding=dict(plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],chat_id=p['chat_id'])
 w.save('china_agent:ad_rule_message:'+str(mid),binding)
 assert w.get('china_agent:ad_rule_message:'+str(mid))==binding
 p.update(binding_status='verified',pending_count=1,wb_writes=0);w.save(KEY,p)
 print(json.dumps(dict(status=p['delivery_status'],message_id=mid,binding_status=p['binding_status'],pending_count=1,wb_writes=0)))
if __name__=='__main__':
 assert os.environ.get('GITHUB_REPOSITORY')=='Ekaterina11098/veschi-bot-runner'
 main()
