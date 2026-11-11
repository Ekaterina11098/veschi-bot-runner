"""Explicit owner resolution and useful replies, independent of model output."""
import re
def resolved(w,job):
 p=w.get('china_agent:owner_dialog_resolution:v1:job:'+str(job['id'])) or {}
 if p.get('status')!='answered_by_owner' or p.get('chat_id')!=job['chat_id'] or not p.get('receipt_key'):return None
 r=w.get(p['receipt_key']) or {}
 receipt=r.get('receipt')if r.get('status')=='sent'else r.get('edit_receipt')if r.get('status')=='completed'else None
 direct=r.get('status')=='sent'and r.get('chat_id')==job['chat_id']and r.get('message_id')==p.get('message_id')
 edited=isinstance(receipt,dict)and receipt.get('chat',{}).get('id')==job['chat_id']and receipt.get('message_id')==p.get('message_id')and receipt.get('from',{}).get('id')==8780468043
 if not(direct or edited):return None
 return p
def growth_reply(job,answer,trace):
 text=job.get('request_text','')
 if not re.search(r'добав|нов.{0,15}(?:товар|артикул)',text,re.I) or not re.search(r'реклам|кампан|\\bРК\\b',text,re.I):return answer
 if any(t.get('name')=='prepare_advertising_plan' and (t.get('result') or {}).get('status')=='ready' for t in trace):return answer
 checks=[t.get('result') or {} for t in trace if t.get('name')=='diagnose_article']
 if not checks:return answer
 rows=[r for c in checks for r in c.get('rows',[])]
 # A bid change on an existing campaign member is not a new SKU addition.
 additions=[r for r in rows if (r.get('action') or {}).get('kind') in ('ad_add_sku','add_sku_recommendation')]
 if additions:return answer
 if not rows:return 'Подбор новых товаров не завершён: проверенных кандидатов для добавления пока нет. Изменений в рекламе нет.'
 waiting=any(r.get('review_from') or r.get('stage')=='waiting_first_full_day' for r in rows)
 return 'Новых товаров, готовых к добавлению в рекламу, по этой проверке нет. Проверенные позиции уже участвуют в рекламе.'+(' После последних изменений ещё нужно дождаться полного дня.' if waiting else ' Проверка наличия и экономики новых кандидатов пока не завершена.')+' Новых изменений нет.'
