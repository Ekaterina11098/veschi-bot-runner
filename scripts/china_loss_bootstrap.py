"""Register only the exact owner approved PNG102 and recover genuine TG job66.
No writes to WB; no replay of the generic question or price queues.
"""
import json,os
from china_price_apply import IO
from china_loss_control import *
from china_loss_policy import POLICY
def run():
 io=IO();receipt=io.get('china_agent:loss_actions_send:2026-10-22:v1')
 if not receipt or receipt.get('status')!='delivered' or receipt.get('message_id')!=102 or receipt.get('chat_id')!=CHAT:raise ValueError('PNG receipt missing')
 if receipt.get('sha256')!='56ff96f0e58af5e069374fc785d690b0279affec61cdf3c1284ae1879cf01770':raise ValueError('PNG changed')
 items=[]
 def need(id,article,nm,q):items.append(dict(id=id,kind='needs_data',article=article,nm_id=nm,question=q))
 def color(id,article,nm,old,new):items.append(dict(id=id,kind='card_text_replace',article=article,nm_id=nm,replacements=[[old,new]]))
 need('590_ad','590-PamelaBag-brown',1473245510,'ДРР2% — целевой результат, не ставка WB. Точная корректировка ставок/запросов пока не подготовлена; нужно получить свежую детализацию рекламы. Цену сохраняю.')
 need('57_material','57-NoelBag-burgundy',1473243909,'Пришлите ширину верха в см, материал корпуса и ремня именно бордового варианта, крупный план фактуры. Выдавать ответ о ремне бежевого61 за данные57 нельзя.')
 need('57_ad','57-NoelBag-burgundy',1473243909,'Пауза рекламы не выполнена: нужно подтвердить все текущие РК этогоSKU и возможность отключить только его, не останавливая остальные товары общейРК.')
 need('575_ad','575-AngelaBag-black',1473244355,'Для снижения ДРР до5% нужна точная корректировка ставок/запросов по свежей детализации; проценты ДРР нельзя записать в WB как ставку.')
 color('63_color','63-NoelBag-zdarkblue',1473243915,'винно-красный','тёмно-синий')
 need('63_media','63-NoelBag-zdarkblue',1473243915,'Нужно фото синего варианта при дневном свете и подтверждение материала корпуса; новые фото без исходников не публикую.')
 need('63_ad','63-NoelBag-zdarkblue',1473243915,'Отключение только этогоSKU в общейРК ещё не подготовлено; всю общуюРК не останавливаю.')
 need('37_measure','37-FurManizhka-dbrown',1560345288,'Нужны обхват горловины в см, фото/видео ворса крупно, фото спереди/сзади с замерами60/40см и примерка на54. Универсальную посадку не обещаю без примерки.')
 need('60_material','60-NoelBag-black',1473243912,'Подтвердите натуральную замшу именно чёрного варианта и пришлите фото ворса/вместимости с телефоном. После этого можно точно поправить название.')
 need('60_ad','60-NoelBag-black',1473243912,'Нужно подготовить отключение только этогоSKU во всех текущихРК без остановки остальных товаров.')
 color('67_color','67-NoelBag-zginger',1473243918,'винно-красный','рыжий/терракотовый')
 need('67_material','67-NoelBag-zginger',1473243918,'Нужно фото рыжего варианта без фильтра и подтверждение материала корпуса.')
 need('67_ad','67-NoelBag-zginger',1473243918,'Точное отключение только этогоSKU в текущихРК ещё не подготовлено; остальные товары не затрагиваю.')
 color('4_color','4-FurPanama-white',1535337772,'серый','белый')
 need('4_measure','4-FurPanama-white',1535337772,'Нужны обхват и глубина панамы в см, фото посадки54/58 и подкладки; подтвердите состав и реальный сезон. Цвет исправляется отдельно.')
 need('123_ad','123-Zont-pink',1556488210,'Цена82¥ сохранена; сначала завершить наблюдение21–24октября. Тест ДРР5% не запущен: точные настройки рекламы ещё не подготовлены.')
 need('21_ad','21-FurBigScarf-gray',1560345285,'Для теста ДРР5% нужно подготовить конкретные ставки/запросы на свежих данных; текущая цена сохраняется.')
 p=dict(plan_id='loss-20261022-102',cabinet='token_3',chat_id=CHAT,bot_id=BOT,owner_user_id=OWNER,created_at='2026-10-22T11:13:25+00:00',expires_at='2026-10-23T11:13:25+00:00',report_message_ids=[102],png_sha256=receipt['sha256'],price_changes=False,items=items,plan_sha256=digest(items))
 if not io.create(PLAN+p['plan_id'],p):
  if io.get(PLAN+p['plan_id'])!=p:raise ValueError('Existing plan differs')
 latest=dict(plan_id=p['plan_id'],reply_ids=[102]);old=io.get(LATEST)
 if old and old['plan_id']!=p['plan_id']:raise ValueError('Newer plan exists')
 if not old:io.create(LATEST,latest)
 policy=dict(version='2026-10-22',scope='token_3',algorithm=POLICY,prices_frozen=True)
 if not io.create('china_agent:loss_policy:2026-10-22:v1',policy):pass
 jobs=io.db('business_agent_jobs?id=eq.66&agent_id=eq.china&chat_id=eq.'+str(CHAT)+'&sender_id=eq.'+str(OWNER)+'&select=*')
 if len(jobs)!=1:raise ValueError('Command missing')
 j=jobs[0]
 if j['update_id']!=532552690 or marker(j).get('reply_message_id')!=102 or j['request_text']!='сделай все':raise ValueError('Command scope changed')
 class W:
  now=datetime.now(timezone.utc)
  get=staticmethod(io.get)
  def save(self,k,v,insert=False):return io.create(k,v) if insert else io.put(k,v)
 answer,trace=handle(W(),j)
 if not io.get(APPROVAL+'66'):raise ValueError('Approval recovery failed')
 # Retain original answer; mark it excluded from conversational history.
 if not any(t.get('name')=='china_loss_answer_invalid' for t in j.get('tool_trace',[])):
  io.db('business_agent_jobs?id=eq.66','PATCH',dict(tool_trace=j['tool_trace']+[dict(name='china_loss_answer_invalid',reason='wrong119_context_and_unknown_expenses_zero',deleted_message_id=104),*trace]))
 print(json.dumps(dict(status='registered',plan_id=p['plan_id'],recovered_job=66,ready_card_items=3,wb_writes=0,telegram_calls=0)))
if __name__=='__main__':run()
