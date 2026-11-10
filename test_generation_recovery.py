import sys,types,unittest,os
from unittest.mock import patch
from types import SimpleNamespace as NS
sys.modules['dotenv']=NS(load_dotenv=lambda:None)
sys.modules['openai']=NS(OpenAI=None)
sys.modules['review_benchmarks']=NS(example_context=lambda *a:'',recent_benchmarks=lambda:[])
sys.modules['review_purchase_context']=NS(purchase_instructions=lambda f:'Статус: отказ. Не приглашать в чат.',purchase_status=lambda f:f.get('orderStatus'),purchase_conflicts=lambda *a:[])
import openai_client as client
class Recovery(unittest.TestCase):
 def test_double_space_customer_and_validation_retry(self):
  texts=iter([
   'Вера Лур, добрый день. Оформите возврат.\nС уважением, команда VESCHI',
   'Вера Лур, добрый день. Нам жаль, что длина манишки вам не подошла.\nС уважением, команда VESCHI',
   'Вера Лур, добрый день. Спасибо, что рассказали о посадке. Понимаем ваше разочарование: ожидания от модели не оправдались. Желаем удачных покупок.\nС уважением, команда VESCHI'])
  prompts=[]
  def create(**kw):
   prompts.append(kw['messages'][-1]['content'])
   return NS(choices=[NS(message=NS(content=next(texts)))])
  fake=NS(chat=NS(completions=NS(create=create)))
  with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}),patch.object(client,'OpenAI',return_value=fake),patch.object(client,'load_system_prompt',return_value='rules'):
   out=client.generate_draft({'userName':'Вера  Лур','text':'Модель слишком короткая','orderStatus':'rejected','productValuation':3})
  self.assertTrue(out['variant1'].startswith('Вера  Лур, добрый день.'))
  self.assertIn('запрещённое слово',prompts[1])
  self.assertNotIn('чат с продавцом',out['variant1'])
if __name__=='__main__':unittest.main()

