import sys,unittest,sqlite3
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_morning import eligible
from review_telegram_approval import Approval,Repository,sha
from test_review_approved_worker import Tests as FeedbackExecutorTests

class QuestionExecutorTests(FeedbackExecutorTests):
    def setUp(self):
        super().setUp()
        self.i['kind']='questions';self.card['kind']='questions'
        self.repo.put('intents','i',self.i);self.repo.put('cards','card',self.card);self.conn.commit()

class QuestionApprovalTests(unittest.TestCase):
    def test_scoped_question_notifications_and_legacy_queue_block(self):
        for cabinet in ('token_1','token_2','token_3'):
            source=Mock();source.was_notified.return_value=False;source.journal.return_value=None
            repo=Mock();repo.get.return_value=None;hold=Mock(return_value=None)
            self.assertTrue(eligible({'id':'same'},cabinet,source,repo,hold,'questions'))
            source.was_notified.assert_called_with(cabinet,'questions','same')
            source.journal.assert_called_with('veschi-review:'+cabinet+':questions:same')
            hold.assert_called_with('reviews:hold:'+cabinet+':questions:same')
            source.journal.return_value={'state':'pending'}
            self.assertFalse(eligible({'id':'same'},cabinet,source,repo,hold,'questions'))
            self.assertFalse(eligible({'id':'same','answer':{'text':'existing'}},cabinet,source,repo,hold,'questions'))
    def test_question_selection_confirmation_replay_and_context(self):
        for cabinet in ('token_1','token_2','token_3'):
            repo=Repository(sqlite3.connect(':memory:'));repo.setup()
            app=Approval(repo,'secret','owner','chat','bot',enabled=True,clock=lambda:1000)
            token,view=app.create(cabinet,'questions','q-id','v',dict(buyer='Имя',rating=0,text='Какой размер?',pros='',cons='',article='sku'),['Первый ответ','Второй ответ'],12)
            self.assertIn('[Вопросы:согласование]',view['text'])
            self.assertIn('ID вопроса: q-id',view['text'])
            self.assertIn('Вопрос: Какой размер?',view['text'])
            self.assertNotIn('Оценка:',view['text']);self.assertNotIn('Достоинства:',view['text'])
            def update(cid,action):return {'callback_query':{'id':cid,'from':{'id':'owner'},'message':{'message_id':12,'chat':{'id':'chat','type':'private'},'from':{'id':'bot'}},'data':'rv1:'+token+':'+action}}
            app.handle(update('choose','v2'),'secret')
            self.assertEqual(repo.count('intents'),0)
            selected=repo.get('cards',token)
            cb=update('confirm','ok.'+selected['nonce'])
            result=app.handle(cb,'secret');self.assertTrue(result['result']['publication_created'])
            intent=repo.get('intents',result['result']['intent_id'])
            self.assertEqual((intent['cabinet'],intent['kind'],intent['item_id'],intent['answer']),(cabinet,'questions','q-id','Второй ответ'))
            self.assertTrue(app.handle(cb,'secret')['duplicate']);self.assertEqual(repo.count('intents'),1)
            card=repo.get('cards',token);card['status']='sent'
            self.assertNotIn('Ответ опубликован.',app.view(token,card)['text'])
if __name__=='__main__':unittest.main()
