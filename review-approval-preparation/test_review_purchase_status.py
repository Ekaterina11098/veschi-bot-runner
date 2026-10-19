import copy
from test_review_telegram import Tests
class PurchaseTests(Tests):
    def test_purchase_status_preserves_approval(self):
        original=self.repo.get('cards',self.token)
        for raw,label in [('buyout','Выкуп'),('rejected','Отказ'),('returned','Возврат'),(None,'WB не передал статус'),('new-value','WB не передал статус')]:
            card=copy.deepcopy(original);card['order_status']=raw
            view=self.a.view(self.token,card)
            self.assertIn('Статус покупки: '+label,view['text'])
            self.assertEqual(card['source'],original['source'])
            self.assertEqual(card['hashes'],original['hashes'])
            self.assertEqual(view['reply_markup'],self.view['reply_markup'])
        card['kind']='questions'
        self.assertNotIn('Статус покупки:',self.a.view(self.token,card)['text'])
