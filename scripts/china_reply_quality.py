"""Plain Telegram formatting and cached current advertising membership, no network."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
RULES=('Пиши обычным текстом без Markdown ** и буквальных символов обратный слеш+n. '
 'Высокая историческая ДРР не означает, что товар сейчас рекламируется в той же РК. '
 'Перед списком товаров с высокой ДРР используй read_recent_actions и текущий состав РК; '
 'в каждой строке укажи отдельно: РК/период показателя, уже исключён здесь или ещё активен, '
 'где остался в других РК и текущая ставка. Исключение из одной РК не равно исключению из всех. '
 'Число всех проблемных позиций называй только после проверки всех РК; при частичных данных явно напиши число проверенных и неполноту. '
 'Скрытые здоровые SKU входят в расходы РК: нельзя объяснять маленький расход РК скрытием товаров. '
 'Сначала сверь даты: сегодня неполный день против полных вчерашних суток. '
 'Если причин расхождения не проверено, не выдумывай объяснение.')
def normalize_answer(text):
 if not isinstance(text,str) or '[[' in text:return text
 if r'\n\n' in text:text=text.replace(r'\n','\n')
 return re.sub(r'\*\*([^\n]+?)\*\*',r'\1',text)
def current_memberships(w):
 day=str(w.now.astimezone(MSK).date())
 cached=w.get('china_agent:advertising_intraday:'+day+':v1') or {}
 if not cached.get('complete') or not cached.get('observed_at'):return dict(available=False,note='Текущий состав не подтверждён в общем кэше; исторический расход не доказывает текущую рекламу.')
 labels=dict(w.catalog());rows={}
 camps=cached.get('campaigns',[])
 if isinstance(camps,dict):camps=list(camps.values())
 for c in camps:
  if c.get('status')!=9:continue
  zone='поиск' if c.get('settings',{}).get('placements',{}).get('search') else 'рекомендации'
  for n in c.get('nm_settings',[]):
   nm=n['nm_id'];article=labels.get(str(nm),labels.get(nm,'WB '+str(nm)))
   rows.setdefault(article,[]).append(dict(rc=c['id'],zone=zone,bid_cny=(n.get('bids_kopecks',{}).get('search' if zone=='поиск' else 'recommendations',0))/100))
 return dict(available=True,observed_at=cached['observed_at'],active_memberships=rows,wb_reads=0,
  note='Актуальный сохранённый состав ВСЕХ активных РК, независимо от даты статистики. Отсутствие здесь означает отсутствие в этом срезе активных РК; не стирать исторический расход.')
