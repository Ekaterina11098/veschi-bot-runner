"""Explicit owner policy for new, unhandled, unambiguously positive five-star reviews."""
import re
from review_telegram_approval import identity,sha,Rejected
CONFIG_KEY='reviews:auto-five-star:config:v1'
POLICY_VERSION='five-star-positive-v1'
CABINETS=('token_1','token_2','token_3')
# A closed vocabulary is deliberate. Unknown words/sarcasm/questions go to a person.
WORDS=set(('дизайн класс натуральная натуральный натуральное теплая яркая большое маленькой вам ее каждый огонь гардероб форма самой снаружи до малютка замша панама тактильно визуально внутри есть шнурок чтобы отрегулировать своей головы небольшая такая нужна была большой зонт меня всю маленькая маленький маленькое маленькие а аж ах в во всем всех все всё вы выбор внешний вид вещь вещи для да даже доставка доставку день добрый заказ за и из изделие изделия как кожи кожа к покупке купила купил качество качества легкая легкий лёгкая лёгкий мне моя мой мы на нам она он они от очень по покупка покупки покупку приятно просто размер размера размеру с со спасибо сумка сумки сумку сумочка сумочки сумочку товар товара то только удобство упаковка упаковку у фурнитура фурнитуры цвет цвета швы швов это я рекомендую рекомендовать всем').split())
STEMS=('упакован','упаковк','зонтик','материал','пыльник','фото','описани','производител','пошив','миленьк','симпатичн','пушист','объемн','потрясающ','отменн','красив','качествен','отличн','прекрасн','великолепн','замечательн','удобн','вместител','хорош','классн','шикарн','супер','довол','понрав','восторг','аккуратн','ровн','мягк','стильн','приятн','лучш','идеальн','быстр','любим','рекоменд','соответств','спасиб')
EMOJI=set('☺🌷🩷👍❤♥🥰😍🔥✨💯😊🙂🙏🤗👏👌💖💕💗💙💚👜🌂💋🌟⭐✅')
POSITIVE_PHRASES=(
 ('милая','красивая'),
 ('сшита качественно','качественная'),
 ('довольно вместительная','вместительная'),
 ('поместится все необходимое','вместительная'),
 ('сумка просто шик','сумка отличная'),
 ('брала в подарок, сама себе захотела','понравилась'),
 ('товар пришел в фабричной упаковке','товар упакован'),
 ('без повреждений',''),
 ('все в прекрасном состоянии','отличная'),
 ('маленькая, но очень вместительная','маленькая вместительная'),
 ('хорошо работают молнии','отличное качество'),
 ('уютная','приятная'),
 ('отказалась в пользу модели побольше',''),
 ('довольная как розовый слон','довольная'),
 ('качественно сшита','качественная'),
 ('цвет благородный','цвет красивый'),
 ('не дишманская','качественная'),
 ('очень благородно и дорого смотрится','красивая'),
 ('цена очень порадовала','понравилась'),
 ('спасибо большое продавцу','спасибо'),
 ('качественно сделано все','качественная'),
 ('до мельчайших деталей',''),
 ('тактильный','приятная'),
 ('вполне',''),
 ('ценителям качественных и красивых вещей',''),
 ('бесподобна','отличная'),
 ('качественно пошито','качественная'),
 ('пришло все упаковано в отдельном мешочке','упакована'),
 ('такой размер как раз и нужен был','размер понравился'),
 ('осталась довольна покупкой','довольна'),
 ('выкупила уже вторую в другом цвете','понравилась'),
 ('прелесть','отличная'),
 ('упакована пришла не хуже шанель','упакована'),
 ('в шелковой сумочке',''),
 ('долго думала купить или нет. когда открыла, посмотрела ура','понравилась'),
 ('два отделения',''),
 ('два кармана',''),
 ('на лето',''),
 ('то что надо','отличная'),
 ('действительно натуральная кожа','кожа'),
 ('внутреннее отделение на замке','удобная'),
 ('сумка бомба','сумка отличная'),
 ('смотрится красиво','красивая'),
 ('за свои деньги',''),
 ('подошла к цвету ботильонов','понравилась'),
 ('подойдет ко всему','удобная'),
 ('среднего размера','размера'),
 ('пришла быстро','быстрая доставка'),
 ('спасибо продавцу','спасибо'),
 ('такие классные сумочки','классные сумочки'),
 ('неудержалась взяла в 2х расцветках','понравилась'),
 ('ношу ее каждый день','понравилась'),
 ('советую 100%','рекомендую'),
 ('на мой 58 подошло четко','отлично'),
 ('без запаха',''),
 ('не ожидала за эти деньги такое качество','качество отличное'),
 ('цена устроила на 💯 %','отлично'),
 ('дешево и сердито','отлично'),
 ('нравится как сшита','понравилась'),
 ('кожа прелестного качества','кожа отличного качества'),
 ('внутри органайзер','удобная'),
 ('дожди закончились',''),
 ('буду ждать, чтобы испытать',''),
 ('расцветка приятная','цвет приятный'),
 ('закрывает меня всю','удобный'),
 ('дизайн зонта интересный','красивый'),
 ('все работает','отлично'),
 ('открывается и закрывается быстро','удобный'),
 ('такая должна быть в ассортименте','понравилась'),
)
VERIFIED_POSITIVE_FIELDS = frozenset(["Рекомендую всем девчонкам эту сумочку  к покупке к этого продовца","Все отлично! Это Любовь с первого взгляда","Нет минусов","Очень симпатичная сумочка, качество супер, упакована в пыльник и пакет.","зонтик очень прикольный вмещается несколько человек от дождя очень супер","Она на фото не такая красивая, я когда открыла офигела!! Очень похожа на норку, а еще и 2100👌🏽💥🤩👍","Сумка натуральная кожа.Хорошая.  Выбрали другой цвет","Огромный, красивый, всё понравилось","Красивая, вместительная сумочка, точно подошла под мои туфли, я рада.","Сумочка супер, вместительная, под всё подходит","Сумка просто бомбическая. Брала без единого отзыва. Поэтому сняла её и так и так. Цвет кофе с молоком, какао что-то такое. Мне очень она понравилась. Не очень большая, но и не мелкая. Кожа гладкая. Качество очень хорошее. По сравнению с ценами в магазине, ваша цена подарок. Взяла не долго думая. Ремешок есть, чтобы через плечо носить. Упакована на 100 из 100.порадовали. Такое отношение к покупателю огонь 🔥🔥🔥спасибо. Очень рекмендую","Подошла идеально к моему пальто цвета кэмэл","Хороший зонт, но цвет ыбрала другой"])
def normalized_verified_field(value):
 return re.sub(r'\s+',' ',value.lower().replace('ё','е').replace('\\n',' ')).strip()
VERIFIED_POSITIVE_FIELDS = frozenset(normalized_verified_field(v) for v in list(VERIFIED_POSITIVE_FIELDS) + ["Внешне соответствует описанию, упаковка супер. Без дефектов.","Сумку купила летом 2025, сейчас ноябрь 2026, сумка как новая при ежедневной носке. Качество очень хорошее. Знакомая заказала такую же с *** а в несколько раз дешевле, так она через месяц вся развалилась, так что цена имеет значение"])

VERIFIED_POSITIVE_FIELDS |= frozenset(normalized_verified_field(v) for v in ["Шоколадка, отличная сумочка","Шикарная сумка, я влюбилась!) Нежно-розовый оттенок, очень приятный, не выглядит приторно, наоборот, благородно. Фурнитура добротная. Очень тщательно была упакована, плюс дополнительный тканевый мешочек (типа атласа). Считаю, что по цене чуть меньше 3000 приобрести качественную сумку из натуральной зернистой кожи это удача) благодарю продавца!✨","Шикарное качество по доступной цене. Удобная и красивая модель.","Приятная сумочка, довольно вместительная.Пришла очень хорошо упакованая, в пыльнике.","Качество на высоте!!!!!!!!!!!!!!!!!\nСтильная, аккуратная, фурнитура дорогая!!!!!!!","Очень хорошая сумка, мягкая, держит форму, размер идеальный","Классная сумочка, я ещё раздумывала брать или не брать.Увидела и влюбилась.","Сумка очень понравилась!!! \nНеграмоская но и немаленькая Спасибо!!!"])
NO_CONS={'','нет','нет.','нет!','не обнаружено','не обнаружены','недостатков нет','отсутствуют','-','—'}
def field(item,key):
 value=item.get(key)
 return '' if value is None else value if isinstance(value,str) else None
VERIFIED_POSITIVE_FIELDS |= frozenset(normalized_verified_field(v) for v in ["Отличная , но выбрала бордо без замши. Спасибо. Всем рекомендую 👍","Девочки прекрасная сумка 👜 рекомендую 👌","Прекрасно упаковано в два мешка и пыльник,внутри вложение с тремя карманами на молнии. Качество отличное, размер и цвет тоже","Классная,модная сумочка,все норма,упаковка идеальная👌продавец молодец🙏🏻","Такая прелесть. Подойдет модницам на все сезоны года. То что нет ничего лишнего, малышка подойдет под многие образы и любой возраст. Цвет не кричащий, цепочка добавила дорогой вид.","выглядит дорого","Маленькая прелесть. \nСтильная, ничего лишнего. Мне очень нравиться сумочка. \nДоставка, упаковка на +.","Сумка отличная, цвет очень яркий насыщенный, качество супер!"])

def semantic_fallback(text,pros,cons):
 from review_semantic_positive import classify_fields
 return classify_fields(text,pros,cons)

def classify(item,kind='feedbacks',cabinet=None):
 if kind!='feedbacks' or item.get('productValuation')!=5:return {'eligible':False,'reason':'not_five_star_review'}
 if item.get('answer') is not None and not isinstance(item['answer'],dict):return {'eligible':False,'reason':'unsupported_answer'}
 if item.get('isAnswered') is True or (item.get('answer') or {}).get('text'):return {'eligible':False,'reason':'already_answered'}
 fields=[field(item,k) for k in ('text','pros','cons')]
 if any(v is None for v in fields):return {'eligible':False,'reason':'unsupported_source'}
 text,pros,cons=fields
 if cabinet=='token_3' and re.search(r'сомнева(?:юсь|емся|ется|ются)|есть\s+сомнения|не\s+уверен[аы]?', ' '.join(fields).lower()):return {'eligible':False,'reason':'china_explicit_uncertainty'}
 # Buyers sometimes put praise in cons. Qualify its text by the same closed
 # vocabulary; never treat the field name alone as evidence of a complaint.
 cons='' if cons.strip().lower() in NO_CONS else cons
 # Normalize phrases within each field so separate fields cannot cancel a negation.
 def normalize(value):
  if normalized_verified_field(value) in VERIFIED_POSITIVE_FIELDS:return 'отличная'
  value=value.lower().replace('ё','е').replace('\\n',' ')
  value=re.sub(r'(?<=[!.])@+$','',value.strip())
  value=re.sub(r'\b(?:без нареканий|без недостатков|нет недостатков|недостатков нет)\b',' ',value)
  for phrase,replacement in POSITIVE_PHRASES:
   value=re.sub(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)',replacement,value)
  return re.sub(r'\bмаленькая,?\s+но\s+вместительна(?:я)?\b','маленькая вместительная',value)
 full=' '.join(normalize(v) for v in (text,pros,cons)).strip()
 if not full:return {'eligible':True,'reason':'five_star_without_text'}
 if '?' in full:
  if cabinet=='token_3' and re.search(r'думал[аи]?.{0,80}подвох[^?]*\?[\s.]*нет[,\s]+вс[её]\s+идеально',full):return semantic_fallback(text,pros,cons)
  return {'eligible':False,'reason':'question'}
 tokens=re.findall(r'[a-zа-я]+',full)
 if not tokens:return {'eligible':all(c.isspace() or c in EMOJI or c in '.,!—-:;()\uFE0F\u200D' for c in full),'reason':'emoji_only'}
 # Never infer positive intent from stars alone or silently discard unknown words.
 if any(t not in WORDS and not any(t.startswith(s) for s in STEMS) for t in tokens):return semantic_fallback(text,pros,cons)
 remainder=re.sub(r'[a-zа-я\s.,!—\-:;()]','',full)
 if any(c not in EMOJI and c not in '\uFE0F\u200D' for c in remainder):return semantic_fallback(text,pros,cons)
 return {'eligible':True,'reason':'unambiguously_positive'}
def policy_allows(policy,app,cabinet,observed_at):
 return (policy.get('enabled') is True and policy.get('version')==POLICY_VERSION and
   policy.get('authorization_channel')=='owner_chat' and policy.get('authorization_ref') and
   str(policy.get('owner_id'))==app.owner and str(policy.get('chat_id'))==getattr(app,'legacy_chat',app.chat) and
   cabinet in CABINETS and cabinet in policy.get('cabinets',[]) and
   isinstance(policy.get('cutover'),(int,float)) and observed_at>=policy['cutover'])
def answer_for(item):
 name=str(item.get('userName') or '').strip()
 generic={'пользователь','покупатель','имя не указано','user'}
 greeting=(name+', добрый день!' if name and name.lower() not in generic and len(name)<=50 and re.fullmatch(r'[А-Яа-яЁёA-Za-z -]+',name) else 'Добрый день!')
 # Neutral for buyout, refusal, return and unknown purchase status.
 return greeting+' Спасибо за отзыв и высокую оценку! Благодарим за внимание к бренду VESCHI.\nС уважением, команда VESCHI 👜✨'
def enqueue(app,bridge,store,item,cabinet,version,observed_at,policy,adopt_existing=False):
 if not policy_allows(policy,app,cabinet,observed_at) or not classify(item,cabinet=cabinet)['eligible']:raise Rejected('Automatic policy does not authorize this review')
 item_id=str(item.get('id') or '')
 if not item_id:raise Rejected('Exact review id required')
 ref=identity(cabinet,'feedbacks',item_id)
 existing=app.repo.get('items',ref)
 if existing:
  if not adopt_existing or existing.get('status')!='open':return {'status':'existing'}
  previous=app.repo.get('cards',existing.get('token','')) or {}
  if previous.get('status')!='awaiting' or '-edit-' in previous.get('version',''):return {'status':'existing'}
 answer=answer_for(item)
 source=dict(buyer=item.get('userName',''),rating=item['productValuation'],text=item.get('text',''),pros=item.get('pros',''),cons=item.get('cons',''),article=(item.get('productDetails') or {}).get('supplierArticle',''))
 source_key='reviews:source:'+sha([cabinet,'feedbacks',item_id,version])
 store.insert(source_key,dict(cabinet=cabinet,kind='feedbacks',item_id=item_id,version=version,item=item,source_sha256=sha(item),observed_at=observed_at))
 draft_key=bridge.draft_key(cabinet,'feedbacks',item_id,version)
 store.insert(draft_key,dict(schema_version=1,cabinet=cabinet,kind='feedbacks',item_id=item_id,version=version,source_sha256=sha(item),variants=[answer],confirmation_status='draft',approved_variant=None,authorization_ref=policy['authorization_ref']))
 token='auto5:'+sha([ref,version])[:32]
 card=dict(ref=ref,cabinet=cabinet,kind='feedbacks',item_id=item_id,version=version,source=source,texts=[answer],hashes=[sha(answer)],message_id=None,expires_at=None,status='approved',selected=0,nonce=None,order_status=item.get('orderStatus'),delivery_mode='automatic_policy',policy_version=POLICY_VERSION,authorization_ref=policy['authorization_ref'],binding=dict(draft_key=draft_key,raw_source_sha256=sha(item),source_key=source_key),observed_at=observed_at)
 state=bridge.project(card)
 if (not state.get('complete') or state.get('hold') or state.get('answered') or state.get('publication_state')!='idle' or state.get('version')!=version or state.get('hashes')!=card['hashes'] or state.get('source_sha256')!=sha(source)):raise Rejected('Canonical state blocks automatic review')
 intent_id=sha([ref,version,sha(answer)])
 intent=dict(id=intent_id,ref=ref,cabinet=cabinet,kind='feedbacks',item_id=item_id,version=version,card_token=token,answer=answer,answer_sha256=sha(answer),source_sha256=sha(source),owner_id=app.owner,chat_id=app.chat,created_at=app.clock(),status='awaiting_preflight',authorization_channel='automatic_policy',authorization_ref=policy['authorization_ref'],policy_version=POLICY_VERSION)
 with app.repo.transaction():
  if app.repo.pg:app.repo.execute('SELECT pg_advisory_xact_lock(hashtextextended(?,0))',('auto-five-star:'+ref,))
  current=app.repo.get('items',ref,lock=True)
  if current:
   if not adopt_existing or current!=existing or current.get('status')!='open':return {'status':'existing'}
   old=app.repo.get('cards',current.get('token',''))
   if not old or old.get('status')!='awaiting' or old.get('source')!=source or '-edit-' in old.get('version',''):return {'status':'existing'}
   import json
   intents=[json.loads(row[0]) for row in app.repo.execute('SELECT payload FROM {p}intents').fetchall()]
   edits=[json.loads(row[0]) for row in app.repo.execute('SELECT payload FROM {p}events').fetchall()]
   if any(x.get('ref')==ref for x in intents) or any(x.get('token')==current.get('token') and x.get('decision')=='revision_requested' for x in edits):return {'status':'existing'}
   app.repo.put('events','automatic-policy-adoption:'+intent_id,dict(old_card=old,old_item=current,authorization_ref=policy['authorization_ref'],created_at=app.clock()))
   old.update(status='superseded',superseded_by=token)
   app.repo.put('cards',current['token'],old)
  app.repo.put('cards',token,card)
  app.repo.put('items',ref,dict(status='approved',token=token,version=version))
  app.repo.put('intents',intent_id,intent)
  app.repo.put('events','automatic-policy:'+intent_id,dict(intent_id=intent_id,authorization_ref=policy['authorization_ref'],classification=classify(item,cabinet=cabinet),source_sha256=sha(item),created_at=app.clock()))
 return {'status':'queued','intent_id':intent_id}
def authorized_card(app,source,card):
 if card.get('delivery_mode')!='automatic_policy':return True
 policy=source.read(CONFIG_KEY) or {}
 if not policy_allows(policy,app,card['cabinet'],card.get('observed_at',0)) or card.get('authorization_ref')!=policy.get('authorization_ref'):return False
 raw=source.read((card.get('binding') or {}).get('source_key','')) or {}
 item=raw.get('item')
 return (isinstance(item,dict) and sha(item)==card['binding']['raw_source_sha256'] and
   str(item.get('id'))==card['item_id'] and classify(item,cabinet=card['cabinet'])['eligible'] and
   card.get('texts')==[answer_for(item)] and card.get('hashes')==[sha(answer_for(item))])


def validate_preflight_response(intent,method,url,response):
 """Qualify only the exact WB review read, never cache/Telegram HTTP traffic."""
 from urllib.parse import urlsplit
 u=urlsplit(str(url))
 if not (intent and intent.get('authorization_channel')=='automatic_policy' and
   intent.get('kind')=='feedbacks' and intent.get('status')=='awaiting_preflight' and
   str(method).upper()=='GET' and u.hostname=='feedbacks-api.wildberries.ru' and
   u.path=='/api/v1/feedback' and response.status_code==200):
  return
 from review_approval_executor import AutomaticPolicyChanged
 body=response.json()
 item=body.get('data') if isinstance(body,dict) else None
 if not isinstance(item,dict) or str(item.get('id'))!=intent['item_id'] or body.get('error'):
  raise RuntimeError('Automatic review preflight incomplete')
 answer=item.get('answer')
 if answer is not None and not isinstance(answer,dict):
  raise RuntimeError('Automatic review answer shape incomplete')
 # Preserve existing-answer reconciliation; never overwrite or resend it.
 if not (answer or {}).get('text') and not classify(item,cabinet=intent['cabinet'])['eligible']:
  raise AutomaticPolicyChanged()


