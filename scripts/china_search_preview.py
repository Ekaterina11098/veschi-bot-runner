"""Read-only preview. No Telegram method is called; no business job created."""
import json,os
from conversion_watches import runtime,saved_network_guard
w=runtime();cfg=w.config()
if cfg['chat_id']!=-1004342917488 or cfg['bot_id']!=8780468043:raise RuntimeError('China scope')
job=dict(id=0,agent_id='china',chat_id=cfg['chat_id'],sender_id=cfg['owner_user_id'],request_text='Проанализируй поисковые запросы и позиции артикула119 и предложи продвижение. Сравни с текущей рекламой, ничего не меняй. Покажи период, цифры и ограничения.',tool_trace=[{'name':'china_saved_question'}])
with saved_network_guard():
 answer,trace=w.saved_question(job,[])
search=[x for x in trace if x['name']=='get_search_analytics']
if len(search)!=1 or search[0]['result'].get('nm_id')!='1473243898' or not search[0]['result'].get('complete'):raise RuntimeError('Complete search context missing')
result=dict(status='verified',answer=answer,trace=trace,telegram_calls=0,wb_writes=0)
w.save('china_agent:search_analytics_preview:'+os.environ['GITHUB_RUN_ID'],result)
print(json.dumps(dict(status='verified',tool_calls=len(trace),telegram_calls=0,wb_writes=0)))
