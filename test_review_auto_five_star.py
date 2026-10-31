import unittest,sqlite3,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,sha,identity,Rejected
from review_auto_five_star import classify,answer_for,enqueue,authorized_card,CONFIG_KEY,POLICY_VERSION
from review_approval_bridge import DurableBridge
from review_approval_executor import Executor
class MemorySource:
 def __init__(self):self.data={}
 def read(self,k):return self.data.get(k)
 def insert(self,k,v):self.data.setdefault(k,v)
 def matching(self,cabinet,kind,item_id,prefix):
  return [v for k,v in reversed(list(self.data.items())) if k.startswith(prefix) and v.get('cabinet')==cabinet and v.get('kind')==kind and v.get('item_id')==item_id]
 def journal(self,k):return None
class WB:
 def __init__(self):self.posts=0;self.answer=''
 def pause(self,c):return 0
 def read(self,i):return self.answer
 def post(self,i):self.posts+=1;self.answer=i['answer']
class PolicyTests(unittest.TestCase):
 def item(self,**kw):
  return dict(id='review-a',productValuation=5,text='',pros='',cons='',userName='Анна',orderStatus='buyout',productDetails={'supplierArticle':'test'},**kw)
 def setUp(self):
  self.conn=sqlite3.connect(':memory:');self.repo=Repository(self.conn);self.repo.setup()
  self.app=Approval(self.repo,'secret','owner','chat','bot',enabled=True,clock=lambda:200)
  self.source=MemorySource();self.bridge=DurableBridge(self.app,self.source)
  self.policy=dict(enabled=True,version=POLICY_VERSION,authorization_channel='owner_chat',authorization_ref='owner-policy-test',owner_id='owner',chat_id='chat',cabinets=['token_1','token_2','token_3'],cutover=100)
  self.source.data[CONFIG_KEY]=self.policy
 def review(self,text='',**kw):
  i=self.item();i.update(text=text,**kw);return i
 def test_positive_and_empty(self):
  for text in ('','Отличная сумка! Рекомендую к покупке.','Очень качественная сумочка, рекомендую','Спасибо, всё прекрасно!','Супер!!! 👍','Хорошая сумка, без нареканий','Красивая, удобная и вместительная'):
   with self.subTest(text=text):self.assertTrue(classify(self.review(text))['eligible'])
 def test_complaints_questions_uncertainty(self):
  cases=['Хорошая сумка, но молния заедает','Спасибо, но пришла порванная','5 звезд, шов разошёлся','Красиво, только ремень короткий','Не рекомендую','Хочу вернуть товар','Зонт не открывается','Отличная сумка?','Когда вернут деньги','Отличное качество 😂','Сумка пахнет','Рекомендую, если заменить молнию','Пока всё хорошо','Без нареканий, но цвет другой','Вместительная, качество супер. Измените размер','Хорошая сумка. Вчера обнаружила дыру']
  for text in cases:
   with self.subTest(text=text):self.assertFalse(classify(self.review(text))['eligible'])
 def test_other_ratings_cons_and_types(self):
  for rating in (1,2,3,4,None,'5'):
   self.assertFalse(classify(self.review(productValuation=rating))['eligible'])
  self.assertFalse(classify(self.review(cons='Молния заедает'))['eligible'])
  self.assertFalse(classify(self.review(text=['отлично']))['eligible'])
  self.assertFalse(classify(self.review(answer='broken'))['eligible'])
  self.assertFalse(classify(self.review(answer={'text':'already'}))['eligible'])
  self.assertFalse(classify(self.review(),'questions')['eligible'])
 def test_positive_cons_and_real_complaints_in_every_field(self):
  praise='Сумка потрясающая! Маленькая, но вместительна, качество отменное!'
  # A contrast can describe a benefit, but unknown contrasts remain manual.
  accepted=(praise,'Отличная сумка!', 'Качество отличное!', 'Сумка потрясающая! Маленькая, вместительная, качество отличное!')
  complaints=('Не рекомендую','Отличная, но молния заедает','Качество не отличное',
   'Маленькая, но неудобная','Отличная сумка, ремень порвался','Красивая, но',
   'Без нареканий?','Потрясающе плохая сумка','Спасибо, не понравилась')
  for key in ('text','pros','cons'):
   for value in accepted:
    with self.subTest(key=key,value=value):self.assertTrue(classify(self.review(**{key:value}))['eligible'])
   for value in complaints:
    with self.subTest(key=key,value=value):self.assertFalse(classify(self.review(**{key:value}))['eligible'])
  self.assertFalse(classify(self.review(text='Отличная сумка',cons='Молния заедает'))['eligible'])
 def test_positive_customer_phrases_and_complaint_suffix(self):
  examples=["Прекрасная сумочка , очень нравится как сшита , кожа прелестного качества , внутри органайзер .","Зонт понравился, расцветка приятная. Дожди закончились. Буду ждать, чтобы испытать","Зонт красивый. Большой. Закрывает меня всю. Дизайн зонта интересный. Всё работает. Открывается и закрывается быстро. Я довольна. Всем спасибо.","Просто супер. Дешево и сердито. Это ❤️","Сумка красивая. Такая должна быть в ассортименте. Цвет красивый."]
  for key in ('text','pros','cons'):
   for text in examples:
    with self.subTest(key=key,text=text):
     self.assertTrue(classify(self.review(**{key:text}))['eligible'])
     self.assertFalse(classify(self.review(**{key:text+' Но молния заедает.'}))['eligible'])
     self.assertFalse(classify(self.review(**{key:'Не '+text}))['eligible'])
  for text in ('Большой, но тяжёлый','Хорошая, но не мой размер','Дешево и сердито?','Прекрасная, внутри органайзер порвался','Все работает, но закрывается с трудом'):
   self.assertFalse(classify(self.review(text))['eligible'])
 def test_positive_size_price_and_fur_descriptions(self):
  examples=('Аккуратная, небольшая, мне такая и нужна была. И цена устроила на 💯 %','Панама классная,тактильно и визуально очень симпатичная. Цвет красивый. Пушистая. Внутри есть шнурок чтобы отрегулировать по размеру своей головы. Панама объёмная.','')
  for key in ('text','pros','cons'):
   for value in examples:
    self.assertTrue(classify(self.review(**{key:value}))['eligible'])
    self.assertFalse(classify(self.review(**{key:value+' Но шнурок порвался'}))['eligible'])
  for value in ('Не симпатичная','Объемная, но тяжёлая','Шнурок неудобный','Небольшая, но не подошла','Цена не устроила на 💯 %'):
   self.assertFalse(classify(self.review(value))['eligible'])
 def test_more_verified_praise_preserves_complaints(self):
  for value in ('На мой 58 подошло четко, миленькая 👍','🩷\\nБез запаха\\nПриятная малютка\\nЗамша\\nНе ожидала за эти деньги такое качество'):
   self.assertTrue(classify(self.review(value))['eligible'])
   self.assertFalse(classify(self.review(value+' Но ремень порвался'))['eligible'])
  for value in ('Не подошло четко','Без запаха, но молния заедает','На мой 58 не подошло четко'):
   self.assertFalse(classify(self.review(value))['eligible'])
 def test_explicit_adoption_only_untouched_open_card(self):
  item=self.review('Отличная сумка')
  source=dict(buyer=item['userName'],rating=5,text=item['text'],pros='',cons='',article='test')
  token,_=self.app.create('token_3','feedbacks',item['id'],'old',source,['manual one','manual two'],123)
  self.assertEqual(enqueue(self.app,self.bridge,self.source,item,'token_3','new',150,self.policy)['status'],'existing')
  result=enqueue(self.app,self.bridge,self.source,item,'token_3','new',150,self.policy,adopt_existing=True)
  self.assertEqual(result['status'],'queued')
  self.assertEqual(self.repo.get('cards',token)['status'],'superseded')
  self.assertEqual(self.repo.count('intents'),1)
  self.assertEqual(enqueue(self.app,self.bridge,self.source,item,'token_3','new',150,self.policy,adopt_existing=True)['status'],'existing')
 def test_common_positive_usage_and_inflections(self):
  positives=('Ношу её каждый день','Качество огонь. Рекомендую.','Любимая сумочка!!!!@','Идеальный пошив снаружи и внутри, советую 100%','Красивый зонтик, материал отличный','Сумочка в гардероб! Форма и цвет понравились','Качественная сумка, упакована в пыльник, соответствует фото и описанию. Спасибо производителю 🌷','Пушистая, соответствует фото','Отличная сумка, от упаковки до самой','Очень понравилась, хорошо упакована, качественная и вместительная')
  complaints=('Ношу её каждый день, но ремень порвался','Качество огонь, но есть запах','Упакована плохо','Не советую 100%','Не соответствует фото','Пошив снаружи хороший, внутри дырка','Красивая, но асимметрия','Не каждый день могу носить','Упаковка рваная','Классная, но для меня большая')
  for key in ('text','pros','cons'):
   for value in positives:self.assertTrue(classify(self.review(**{key:value}))['eligible'],value)
   for value in complaints:self.assertFalse(classify(self.review(**{key:value}))['eligible'],value)
 def test_natural_positive_descriptions_and_complaint_suffixes(self):
  positives=('Действительно натуральная кожа,мягкая,внутреннее отделение на замке,очень довольна,рекомендую к покупке','Сумка бомба,очень понравилась, качество отличное, смотрится красиво, спасибо','очень приятная сумочка за свои деньги. Подошла к цвету ботильонов. Вместительная и подойдет ко всему','Замечательная сумка,среднего размера,кожа мягкая,вместительная,я довольна','Сумка понравилась, пришла быстро, спасибо продавцу 👍👍👍','Красивая,удобная,стильная, Спасибо Вам!!!!','Такие классные сумочки ! Неудержалась взяла в 2х расцветках.')
  for key in ('text','pros','cons'):
   for value in positives:
    self.assertTrue(classify(self.review(**{key:value}))['eligible'],value)
    for suffix in (' Но молния заедает.',' Но кожа красится.','?'):
     self.assertFalse(classify(self.review(**{key:value+suffix}))['eligible'],value+suffix)
    self.assertFalse(classify(self.review(**{key:'Не '+value}))['eligible'])
  for value in ('Прикольная шапочка, только вместо верёвки (утяжки) сделать резинку и будет хорошо','Не натуральная кожа','Сумка бомба, но пахнет','Внутреннее отделение на замке порвалось','Пришла быстро, но брак'):
   self.assertFalse(classify(self.review(value))['eligible'],value)
 def test_october28_positive_descriptions_and_negative_additions(self):
  positives=["Сумка отличная! Очень качественно сделано все, до мельчайших деталей фурнитуры! Мягкая, тактильный очень приятная, вполне вместительная для маленькой сумочки. Цвет соответствует фотографии. Очень рекомендую всем ценителям качественных и красивых вещей!","Сумка бесподобна! качественно пошито , пришло все упаковано в отдельном мешочке , все супер спасибо большое","Качественная, красивая сумка. Мне такой размер как раз и нужен был. Я осталась довольна покупкой 👍","Понравилось все: качество, цвет. Выкупила уже вторую в другом цвете.","Отличная маленькая сумочка, натуральная кожа. Рекомендую.","Теплая","Идеальная сумочка","Прелесть, упакована пришла не хуже Шанель ☺️ в шёлковой сумочке🤗 качество, цвет, размер - всё идеально👌👍 🥰","Классная","","Долго думала купить или нет. Когда открыла, посмотрела Ура!!! Это моя","Отличная сумочка.Яркая.Вместительная.Два отделения .Два кармана.На лето -супер!То что надо."]
  for key in ('text','pros','cons'):
   for value in positives:
    self.assertTrue(classify(self.review(**{key:value}))['eligible'],value)
    for suffix in (' Но ремешок дешевый.',' Молния заедает.','?'):
     self.assertFalse(classify(self.review(**{key:value+suffix}))['eligible'],value+suffix)
  self.assertFalse(classify(self.review(pros='Натуральная замша,цвет очень красивый.Маленькая но вместительная.',cons='Хотелось бы еще дополнительный ремешок, а то этот не очень...Кожзам самый дешевый.'))['eligible'])
 def test_figurative_praise_and_qualified_negation(self):
  positives=('Сумочка класс, довольная как розовый слон. Спасибо за качество и дизайн!','Очень классная сумочка, качественно сшита, цвет благородный, фурнитура не дишманская, очень благородно и дорого смотрится. Цена очень порадовала. Спасибо большое продавцу.')
  for key in ('text','pros','cons'):
   for value in positives:
    self.assertTrue(classify(self.review(**{key:value}))['eligible'],value)
    self.assertFalse(classify(self.review(**{key:value+' Но фурнитура сломалась.'}))['eligible'])
    self.assertFalse(classify(self.review(**{key:value+' Но запах присутствует.'}))['eligible'])
    self.assertFalse(classify(self.review(**{key:value+'?'}))['eligible'])
  self.assertFalse(classify(self.review('Быстрая доставка. Очень аккуратно упаковано, есть пыльник. Сумочка прекрасная,маленькая, качественная. Запах при распаковке присутствует, но не критично. Рекомендую!'))['eligible'])
  for value in ('Фурнитура дишманская','Не довольная как розовый слон','Фурнитура не качественная'):
   self.assertFalse(classify(self.review(value))['eligible'])
 def test_october31_verified_positive_reviews(self):
  positives=["Очень милая, красивая сумочка. Сшита качественно, довольно вместительная, поместится всё необходимое. Я довольна","Сумка просто Шик! Брала в подарок, сама себе захотела!","Товар пришел в фабричной упаковке, без повреждений. Замечательная сумочка, на вид маленькая, но очень вместительная. Качественный материал, фурнитура, все в прекрасном состоянии.","Сумочка очень красивая удобная хорошо работают молнии красивая кожа качественная рекомендую","Сумочка очень красивая, уютная, яркая. Отказалась в пользу модели побольше"]
  for key in ('text','pros','cons'):
   for value in positives:
    self.assertTrue(classify(self.review(**{key:value}))['eligible'],value)
    for suffix in (' Но молния заедает.',' Не кожа.','?'):
     self.assertFalse(classify(self.review(**{key:value+suffix}))['eligible'],value+suffix)
  for value in ('Не милая','Не сшита качественно','Отказалась в пользу модели побольше, потому что ремень порвался','Хорошо работают молнии, но шов разошелся','Без повреждений, но пахнет','Сумка просто шик, не рекомендую'):
   self.assertFalse(classify(self.review(value))['eligible'],value)
 def test_purchase_status_neutral(self):
  for status in ('buyout','rejected','returned',None):
   answer=answer_for(self.review(orderStatus=status))
   self.assertNotIn('пользова',answer)
   self.assertNotIn('служ',answer)
   self.assertIn('Спасибо',answer)
 def test_all_cabinets_once_and_existing_answer(self):
  for cab in ('token_1','token_2','token_3'):
   item=self.review(cons='Сумка потрясающая! Маленькая, но вместительна, качество отменное!');item['id']=cab
   result=enqueue(self.app,self.bridge,self.source,item,cab,'v1',150,self.policy)
   self.assertEqual(result['status'],'queued')
   self.assertEqual(enqueue(self.app,self.bridge,self.source,item,cab,'v1',150,self.policy)['status'],'existing')
   intent=self.repo.get('intents',result['intent_id']);card=self.repo.get('cards',intent['card_token'])
   self.assertIsNone(card['message_id'])
   self.assertTrue(authorized_card(self.app,self.source,card))
   wb=WB();executor=Executor(self.app,lambda _:True,wb,enabled=True)
   self.assertEqual(executor.run(result['intent_id'])['status'],'confirmed')
   executor.run(result['intent_id']);self.assertEqual(wb.posts,1)
 def test_policy_disabled_wrong_owner_and_before_cutover(self):
  for change in ({'enabled':False},{'owner_id':'other'},{'cabinets':['token_3']},{'cutover':151}):
   p=dict(self.policy,**change)
   with self.assertRaises(Rejected):enqueue(self.app,self.bridge,self.source,self.review(),'token_1','v',150,p)
  self.assertEqual(self.repo.count('intents'),0)
 def test_existing_human_card_is_not_adopted(self):
  ref=identity('token_1','feedbacks','review-a')
  with self.repo.transaction():self.repo.put('items',ref,{'status':'rework','token':'human'})
  self.assertEqual(enqueue(self.app,self.bridge,self.source,self.review(),'token_1','v',150,self.policy)['status'],'existing')
  self.assertEqual(self.repo.count('intents'),0)
 def test_policy_rechecked_before_publication(self):
  result=enqueue(self.app,self.bridge,self.source,self.review(),'token_1','v',150,self.policy)
  intent=self.repo.get('intents',result['intent_id']);card=self.repo.get('cards',intent['card_token'])
  self.source.data[CONFIG_KEY]=dict(self.policy,enabled=False)
  self.assertFalse(authorized_card(self.app,self.source,card))
  wb=WB();out=Executor(self.app,lambda c:authorized_card(self.app,self.source,c),wb,enabled=True).run(intent['id'])
  self.assertEqual(out['status'],'blocked');self.assertEqual(wb.posts,0)
 def test_existing_manual_wb_answer_never_overwritten(self):
  result=enqueue(self.app,self.bridge,self.source,self.review(),'token_1','v',150,self.policy)
  wb=WB();wb.answer='Already answered in seller portal'
  out=Executor(self.app,lambda _:True,wb,enabled=True).run(result['intent_id'])
  self.assertEqual(out['status'],'manual_present');self.assertEqual(wb.posts,0)
 def test_unknown_write_result_is_never_repeated(self):
  class Uncertain(WB):
   def post(self,i):self.posts+=1;raise TimeoutError()
  result=enqueue(self.app,self.bridge,self.source,self.review(),'token_1','v',150,self.policy)
  wb=Uncertain();ex=Executor(self.app,lambda _:True,wb,enabled=True)
  self.assertEqual(ex.run(result['intent_id'])['status'],'verify')
  ex.run(result['intent_id']);self.assertEqual(wb.posts,1)
 def test_fresh_wb_review_changed_requires_manual(self):
  from review_approval_executor import AutomaticPolicyChanged
  class Changed(WB):
   def read(self,i):raise AutomaticPolicyChanged()
  result=enqueue(self.app,self.bridge,self.source,self.review(),'token_1','v',150,self.policy)
  wb=Changed();out=Executor(self.app,lambda _:True,wb,enabled=True).run(result['intent_id'])
  self.assertEqual(out['status'],'blocked');self.assertEqual(wb.posts,0)
 def test_silent_telegram_lifecycle_for_policy(self):
  from review_approval_card_delivery import notify_owner_receipt
  from review_approval_cleanup import cleanup_completed
  class NoTelegram:
   def call(self,*a,**kw):raise AssertionError('Automatic review has no Telegram card')
  result=enqueue(self.app,self.bridge,self.source,self.review(),'token_1','v',150,self.policy)
  intent=self.repo.get('intents',result['intent_id'])
  self.assertEqual(notify_owner_receipt(self.app,NoTelegram(),intent)['status'],'suppressed')
  self.assertEqual(cleanup_completed(self.app,NoTelegram())['deleted'],0)
if __name__=='__main__':unittest.main()
