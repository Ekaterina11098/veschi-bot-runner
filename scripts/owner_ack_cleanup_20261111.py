"""Delete duplicate acceptance notices explicitly withdrawn by owner; no sends or WB calls."""
from china_loss_execute import IO
def run():
 io=IO();K='china_agent:owner_ack_cleanup:2026-11-11:v1';old=io.get(K)
 if old:
  assert old['status']=='completed';return
 assert io.get('china_agent:owner_final_execution_cleanup:2026-11-11:v1')['status']=='completed'
 pairs=[(294,863),(295,864)];archive={}
 for job,mid in pairs:
  key='china_agent:conversion_watch_delivery:v1:question:'+str(job)+':0';v=io.get(key)
  assert v['status']=='sent'and v['message_id']==mid;archive[key]=v
 rec=dict(status='deleting',archive=archive,deletions=[]);assert io.create(K,rec)
 for job,mid in pairs:
  assert io.tg('deleteMessage',dict(chat_id=-1004342917488,message_id=mid))is True
  rec['deletions'].append(dict(message_id=mid,status='deleted_verified'));io.put(K,rec)
 rec['status']='completed';io.put(K,rec)
 print('Acceptance notices863864 removed; final868 retained')
if __name__=='__main__':run()
