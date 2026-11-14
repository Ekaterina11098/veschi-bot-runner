"""Read the exact current umbrella minimum; never change the approved price."""
import json
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_finish326:2026-11-14:v1:minimum_read'
def main():
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(ROOT):return
 campaigns=w.campaigns([41325637]);state=campaigns['41325637'];ids=sorted(n['nm_id']for n in state['nm_settings'])
 minimums=w.minimums(41325637,ids,'search')
 out=dict(status='complete',observed_at=stamp(),campaign=state,minimums=minimums,approved_target_minor=23,all_at_approved_minimum=all(v<=23 for v in minimums.values()),wb_writes=0,telegram_calls=0)
 assert c.create(ROOT,out);print(json.dumps(dict(status='complete',minimums=minimums,all_at_approved_minimum=out['all_at_approved_minimum'],wb_writes=0)))
 from china_loss_execute import IO
 from china_loss_control import PLAN,APPROVAL
 from china_daily_ad_actions import EXEC,execute
 from china_execution_notice import deliver_result
 import copy
 io=IO();a=io.get(APPROVAL+'326');p=io.get(PLAN+a['plan_id']);key=EXEC+p['plan_id'];e=io.get(key)
 pending=next(s for s in e['items']if s['id']=='recover:41325637')
 assert e['status']=='done'and pending['status']=='blocked'and not pending.get('steps')and not pending.get('request')
 assert all(s['status']=='verified'for s in e['items']if s['id']!='recover:41325637')
 if not out['all_at_approved_minimum']:
  values=sorted(set(minimums.values()));label='/'.join(format(v/100,'.2f')for v in values)
  pending['reason']='Минимум WB сейчас '+label+' CNY; подтверждено 0.23 CNY. Снижение, пополнение 100 CNY и запуск не выполнены.'
  pending['minimum_readback_key']=ROOT;io.put(key,e)
  notice=deliver_result(io,a,p,e);assert notice and notice['status']=='sent'
  out['result_notice_key']='china_agent:daily_ad_result:v2:'+p['plan_id']+':revision:'+__import__('hashlib').sha256(notice['text'].encode()).hexdigest()[:16]
  out['result_message_id']=notice['message_id'];c.put(ROOT,out)
 else:
  assert c.create(ROOT+':recovery',dict(status='preflight',prior=e,grants_action_permission=False))
  fresh=copy.deepcopy(e);fresh['items']=[s for s in fresh['items']if s['id']!='recover:41325637'];fresh['status']='running';io.put(key,fresh)
  result=execute(io,a,p);c.put(ROOT+':recovery',dict(status='verified'if all(s['status']=='verified'for s in result['items'])else'attention_required',execution_key=key))
if __name__=='__main__':main()
