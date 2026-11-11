"""Resume only a prospective human price confirmation blocked before WB by decimal display mismatch."""
import json
from urllib.parse import quote
from china_price_apply import IO,process,validate_approval,PREFIX,now,MINIMUM_POLICY,sha
K='china_agent:owner_price297_format_recovery:2026-11-11:v1'
def run():
 io=IO();cfg=io.get(K);assert cfg and cfg['status']in ('authorized_repair','sent')
 if cfg['status']=='sent':print('Exact correction already delivered');return
 key=cfg['approval_key'];a=io.get(key);validate_approval(key,a)
 assert a['confirmation_source']=='telegram_callback' and a['report_job_id']==297 and a['report_message_id']==870 and a['actor_user_id']==5122667182
 assert a['selections']==cfg['confirmed_selections']
 ek='china_agent:price_execution:v1:'+key[len(PREFIX):];e=io.get(ek)
 if e and e.get('status')=='blocked':
  assert e==dict(status='blocked',reason='Согласованные цены отсутствуют в отчёте',items=[])
  io.validate(a) # Exact report hash, delivered source, human membership and numeric values.
  archive=K+':original_validation_block'
  if not io.get(archive):assert io.create(archive,dict(execution_key=ek,original=e,reason='decimal_comma_dot_only_before_write',at=now().isoformat()))
  new=dict(status='preflight',approval_key=key,actor_user_id=a['actor_user_id'],created_at=now().isoformat(),items=[],minimum_price_policy=MINIMUM_POLICY,recovered_from=archive)
  changed=io.db('telegram_api_cache?cache_key=eq.'+quote(ek,safe='')+'&payload=eq.'+quote(json.dumps(e,ensure_ascii=False,separators=(',',':')),safe=''),'PATCH',dict(payload=new),'return=representation')
  assert len(changed)==1
 e=process(io,key,polls=8)
 lines=['Результат подтверждения цен']
 for x in e.get('items',[]):
  s=x['selection'];status={'applied':'применено и проверено WB','already_at_target':'уже установлена; повторно не меняли','blocked':'не изменено: '+x.get('reason',''),'failed':'результат WB не подтверждён','ready':'WB обрабатывает изменение'}[x['status']]
  lines.append(s['article']+': '+s['current_cny'].replace('.',',')+' → '+s['target_cny'].replace('.',',')+' CNY — '+status)
 if e.get('reason'):lines.append(e['reason'])
 text='\n'.join(lines)
 noticekey=cfg['original_notice_key'];notice=io.get(noticekey);assert notice['status']=='sent'and notice['message_id']==871 and notice['chat_id']==-1004342917488
 if not io.get(K+':original_notice'):assert io.create(K+':original_notice',notice)
 receipt=io.tg('editMessageText',dict(chat_id=-1004342917488,message_id=871,text=text))
 assert receipt['message_id']==871 and receipt['chat']['id']==-1004342917488
 nk='china_agent:price_execution_notice:v1:'+sha(key+':'+e['status'])
 payload=dict(status='sent',message_id=871,chat_id=-1004342917488,text=text,receipt=receipt,edited_at=now().isoformat(),execution_key=ek)
 if io.get(nk):io.put(nk,payload)
 else:assert io.create(nk,payload)
 cfg.update(status='sent',execution_key=ek,execution_status=e['status'],item_statuses=[x['status']for x in e.get('items',[])],receipt=receipt);io.put(K,cfg)
 print(json.dumps(dict(execution_status=e['status'],items=cfg['item_statuses'],message_id=871)))
if __name__=='__main__':run()
