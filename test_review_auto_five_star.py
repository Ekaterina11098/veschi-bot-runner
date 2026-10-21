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
 def test_purchase_status_neutral(self):
  for status in ('buyout','rejected','returned',None):
   answer=answer_for(self.review(orderStatus=status))
   self.assertNotIn('пользова',answer)
   self.assertNotIn('служ',answer)
   self.assertIn('Спасибо',answer)
 def test_all_cabinets_once_and_existing_answer(self):
  for cab in ('token_1','token_2','token_3'):
   item=self.review();item['id']=cab
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
