"""Explicit owner policy for new, unhandled, unambiguously positive five-star reviews."""
import re
from review_telegram_approval import identity,sha,Rejected
CONFIG_KEY='reviews:auto-five-star:config:v1'
POLICY_VERSION='five-star-positive-v1'
CABINETS=('token_1','token_2','token_3')
# A closed vocabulary is deliberate. Unknown words/sarcasm/questions go to a person.
WORDS=set(('маленькая маленький маленькое маленькие а аж ах в во всем всех все всё вы выбор внешний вид вещь вещи для да даже доставка доставку день добрый заказ за и из изделие изделия как кожи кожа к покупке купила купил качество качества легкая легкий лёгкая лёгкий мне моя мой мы на нам она он они от очень по покупка покупки покупку приятно просто размер размера размеру с со спасибо сумка сумки сумку сумочка сумочки сумочку товар товара то только удобство упаковка упаковку у фурнитура фурнитуры цвет цвета швы швов это я рекомендую рекомендовать всем').split())
STEMS=('потрясающ','отменн','красив','качествен','отличн','прекрасн','великолепн','замечательн','удобн','вместител','хорош','классн','шикарн','супер','довол','понрав','восторг','аккуратн','ровн','мягк','стильн','приятн','лучш','идеальн','быстр','любим','рекоменд','соответств','спасиб')
EMOJI=set('👍❤♥🥰😍🔥✨💯😊🙂🙏🤗👏👌💖💕💗💙💚👜🌂💋🌟⭐✅')
NO_CONS={'','нет','нет.','нет!','не обнаружено','не обнаружены','недостатков нет','отсутствуют','-','—'}
def field(item,key):
 value=item.get(key)
 return '' if value is None else value if isinstance(value,str) else None
def classify(item,kind='feedbacks'):
 if kind!='feedbacks' or item.get('productValuation')!=5:return {'eligible':False,'reason':'not_five_star_review'}
 if item.get('answer') is not None and not isinstance(item['answer'],dict):return {'eligible':False,'reason':'unsupported_answer'}
 if item.get('isAnswered') is True or (item.get('answer') or {}).get('text'):return {'eligible':False,'reason':'already_answered'}
 fields=[field(item,k) for k in ('text','pros','cons')]
 if any(v is None for v in fields):return {'eligible':False,'reason':'unsupported_source'}
 text,pros,cons=fields
 # Buyers sometimes put praise in cons. Qualify its text by the same closed
 # vocabulary; never treat the field name alone as evidence of a complaint.
 cons='' if cons.strip().lower() in NO_CONS else cons
 # Normalize phrases within each field so separate fields cannot cancel a negation.
 def normalize(value):
  value=value.lower().replace('ё','е')
  value=re.sub(r'\b(?:без нареканий|без недостатков|нет недостатков|недостатков нет)\b',' ',value)
  return re.sub(r'\bмаленькая,?\s+но\s+вместительна(?:я)?\b','маленькая вместительная',value)
 full=' '.join(normalize(v) for v in (text,pros,cons)).strip()
 if not full:return {'eligible':True,'reason':'five_star_without_text'}
 if '?' in full:return {'eligible':False,'reason':'question'}
 tokens=re.findall(r'[a-zа-я]+',full)
 if not tokens:return {'eligible':all(c.isspace() or c in EMOJI or c in '.,!—-:;()\uFE0F\u200D' for c in full),'reason':'emoji_only'}
 # Never infer positive intent from stars alone or silently discard unknown words.
 if any(t not in WORDS and not any(t.startswith(s) for s in STEMS) for t in tokens):return {'eligible':False,'reason':'ambiguous_or_complaint'}
 remainder=re.sub(r'[a-zа-я\s.,!—\-:;()]','',full)
 if any(c not in EMOJI and c not in '\uFE0F\u200D' for c in remainder):return {'eligible':False,'reason':'ambiguous_symbols'}
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
def enqueue(app,bridge,store,item,cabinet,version,observed_at,policy):
 if not policy_allows(policy,app,cabinet,observed_at) or not classify(item)['eligible']:raise Rejected('Automatic policy does not authorize this review')
 item_id=str(item.get('id') or '')
 if not item_id:raise Rejected('Exact review id required')
 ref=identity(cabinet,'feedbacks',item_id)
 existing=app.repo.get('items',ref)
 if existing:return {'status':'existing'}
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
  if app.repo.get('items',ref):return {'status':'existing'}
  app.repo.put('cards',token,card)
  app.repo.put('items',ref,dict(status='approved',token=token,version=version))
  app.repo.put('intents',intent_id,intent)
  app.repo.put('events','automatic-policy:'+intent_id,dict(intent_id=intent_id,authorization_ref=policy['authorization_ref'],classification=classify(item),source_sha256=sha(item),created_at=app.clock()))
 return {'status':'queued','intent_id':intent_id}
def authorized_card(app,source,card):
 if card.get('delivery_mode')!='automatic_policy':return True
 policy=source.read(CONFIG_KEY) or {}
 if not policy_allows(policy,app,card['cabinet'],card.get('observed_at',0)) or card.get('authorization_ref')!=policy.get('authorization_ref'):return False
 raw=source.read((card.get('binding') or {}).get('source_key','')) or {}
 item=raw.get('item')
 return (isinstance(item,dict) and sha(item)==card['binding']['raw_source_sha256'] and
   str(item.get('id'))==card['item_id'] and classify(item)['eligible'] and
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
 if not (answer or {}).get('text') and not classify(item)['eligible']:
  raise AutomaticPolicyChanged()
