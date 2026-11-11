"""Consolidate verified owner result; Telegram edits/deletions only, no WB calls."""
from datetime import datetime,timezone
from china_loss_execute import IO
from china_execution_notice import proven
from china_loss_control import PLAN
PID='daily-2026-11-11-owner-unified-final-drr-0'
TEXT="ВЫПОЛНЕНО · 11 ноября\nВсе21действие утреннего плана857/858 выполнено и проверено в WB.\n\nДобавлены:\n• Zont01-fio — РК40811856, рекомендации0,23CNY.\n• Панамы3,4,5,16 — РК41325622, поиск по0,11CNY.\n\nСтавки:\n• 0-NoelBag-green:0,42→0,28CNY.\n• Панама8:0,15→0,16CNY.\n• Манишка39:0,24→0,17CNY.\n\nИсключены из указанных РК:\n• 623 —40933588; панама7 —41325622.\n• 022 —41332083; 55 —41680341.\n\nЗавершены и отправлены в архив РК41155824,41270471,41570073.\n\nПополнено4300CNY:\n40933588 +2500;40964981 +100;41055480 +300;41155909 +100;41270309 +250;41298169 +1050.\nПовторных пополнений нет.41296363 оставлена без пополнения.\n\nВЕЧЕРНЕЕ ПОДТВЕРЖДЕНИЕ10НОЯБРЯ\nТогда три действия не выполнились: обработка не началась. Исключение022 выполнено сегодня по утреннему плану. Исключение23 и снижение ставки119 с0,23 до0,21CNY остаются НЕ выполненными: старый план уже заменён и повторно не запускался.\n\nЭто окончательный отчёт. Промежуточные сообщения удалены."
def run():
 io=IO();ek='china_agent:daily_ad_execution:v2:'+PID;e=io.get(ek);p=io.get(PLAN+PID);items={i['id']:i for i in p['items']}
 assert len(e['items'])==21 and all(proven(items[s['id']],s)for s in e['items'])
 fk='china_agent:owner_funding_recovery:2026-11-11:v1:delivery';final=io.get(fk)
 assert final['status']=='sent'and final['message_id']==868 and final['verified_count']==21 and final['funded_cny']==4300
 K='china_agent:owner_final_execution_cleanup:2026-11-11:v1'
 old=io.get(K)
 if old:
  assert old['status']=='completed';return
 keys=['china_agent:daily_ad_result:v2:'+PID,'china_agent:owner_evening293_audit:2026-11-11:v1:delivery','china_agent:owner_additions_recovery:2026-11-11:v1:delivery',fk]
 archive={k:io.get(k)for k in keys}
 assert [archive[k]['message_id']for k in keys]==[865,866,867,868]
 rec=dict(status='editing',archive=archive,text=TEXT,chat_id=-1004342917488,message_id=868,execution_key=ek,created_at=datetime.now(timezone.utc).isoformat())
 assert io.create(K,rec)
 r=io.tg('editMessageText',dict(chat_id=-1004342917488,message_id=868,text=TEXT))
 assert r['message_id']==868 and r['chat']['id']==-1004342917488
 rec.update(status='edited_verified',edit_receipt=r);io.put(K,rec)
 # Keep canonical current delivery pointing to the visible final message; original receipts remain archived.
 for key in keys:
  v=dict(archive[key],status='sent',message_id=868,chat_id=-1004342917488,text=TEXT,final_receipt_key=K,supersedes_message_id=archive[key]['message_id'])
  if key==keys[0]:v.update(phase='verified',receipt=r,verified_count=21)
  io.put(key,v)
 resolution=io.get('china_agent:owner_dialog_resolution:v1:job:293')
 assert resolution['status']=='answered_by_owner'
 resolution.update(message_id=868,receipt_key=K,answer=TEXT)
 io.put('china_agent:owner_dialog_resolution:v1:job:293',resolution)
 rec['deletions']=[]
 for mid in [865,866,867]:
  assert io.tg('deleteMessage',dict(chat_id=-1004342917488,message_id=mid))is True
  rec['deletions'].append(dict(message_id=mid,status='deleted_verified'));io.put(K,rec)
 rec['status']='completed';io.put(K,rec)
 print('Single final result868 verified; intermediate865866867 deleted')
if __name__=='__main__':run()
