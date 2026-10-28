import unittest
from china_zero_order_price_command import parse,signature,validate_command,ROOT
from china_zero_orders import recognizes
from decimal import Decimal
TEXT='Отлично. Все товары что ты собрал без заказов добавь на них увеличение цены на 30%'
class T(unittest.TestCase):
 def test_command_not_a_list(self):self.assertFalse(recognizes(TEXT));self.assertEqual(parse(TEXT),'30')
 def test_report_still_recognized(self):self.assertTrue(recognizes('Дай списком товары которые не имеют заказов последние 14 дней'))
 def test_question_not_authorization(self):self.assertIsNone(parse('Может все товары без заказов поднять цену на 30%?'))
 def test_no_implicit_percentage(self):self.assertIsNone(parse('Все товары без заказов добавь увеличение цены'))
 def test_no_ad_write_as_list(self):self.assertFalse(recognizes('Все товары без заказов исключи из рекламы'))
 def data(self):
  j=dict(id=155,sender_id=3,request_text=TEXT);s=dict(nm_id='1',article='a',current_cny='100',target_cny='130');e=dict(actor_user_id=3,percent='30',source_key='source',signature=signature(j,'source','30'),approval_key='approval',selections=[s],cohort=[dict(nm_id='1',article='a')]);a=dict(report_job_id=155,actor_user_id=3,approval_key='approval',selections=[s],report_sha256=__import__('hashlib').sha256(TEXT.encode()).hexdigest());source=dict(status='sent',report=dict(zero=[dict(nm_id=1,article='a')]));io=type('IO',(),{'get':lambda _,k:e if k==ROOT+'155' else source})();return io,a,j,e
 def test_exact_binding(self):
  io,a,j,e=self.data();validate_command(io,a,j)
 def test_wrong_target_rejected(self):
  io,a,j,e=self.data();a['selections'][0]['target_cny']='131'
  with self.assertRaises(ValueError):validate_command(io,a,j)
 def test_cohort_expansion_rejected(self):
  io,a,j,e=self.data();e['cohort'].append(dict(nm_id='2',article='b'))
  with self.assertRaises(ValueError):validate_command(io,a,j)
 def test_declared_legal_step(self):
  io,a,j,e=self.data();s=a['selections'][0];s.update(current_cny='188',target_cny='244.5',base_cny='376',seller_discount=50,nominal_target_cny='244.4',rounding_policy='nearest_WB_base_unit_preserve_discount');validate_command(io,a,j)
 def test_wrong_step_rejected(self):
  io,a,j,e=self.data();s=a['selections'][0];s.update(current_cny='188',target_cny='245',base_cny='376',seller_discount=50,nominal_target_cny='244.4',rounding_policy='nearest_WB_base_unit_preserve_discount')
  with self.assertRaises(ValueError):validate_command(io,a,j)
 def test_changed_original_command_rejected(self):
  io,a,j,e=self.data();j['request_text']=TEXT.replace('30','50')
  with self.assertRaises(ValueError):validate_command(io,a,j)
class StatusTests(unittest.TestCase):
 def worker(self,execution):
  return type('W',(),{'db':lambda *a,**k:[dict(cache_key=ROOT+'155',execution_key='exec',cohort=[{},{}])],'get':lambda _,k:execution})()
 def test_status_uses_verified_readback(self):
  from china_zero_order_price_command import status_answer
  x=dict(status='applied',selection=dict(article='a',target_cny='130'),readback=dict(currencyIsoCode4217='CNY',vendorCode='a',sizes=[dict(discountedPrice=130)]))
  answer,trace=status_answer(self.worker(dict(items=[x])),dict(request_text='Ты цены поднял?'),[])
  self.assertEqual(trace[0]['wb_verified'],1)
 def test_green_flag_without_matching_price_not_success(self):
  from china_zero_order_price_command import status_answer
  x=dict(status='applied',selection=dict(article='a',target_cny='130'),readback=dict(currencyIsoCode4217='CNY',vendorCode='a',sizes=[dict(discountedPrice=100)]))
  self.assertEqual(status_answer(self.worker(dict(items=[x])),dict(request_text='Ты цены поднял?'),[])[1][0]['wb_verified'],0)
 def test_unrelated_clarification_not_intercepted(self):
  from china_zero_order_price_command import status_answer
  self.assertIsNone(status_answer(self.worker({}),dict(request_text='Не понимаю'),[dict(request_text='Расскажи про остатки')]))
if __name__=='__main__':unittest.main()

