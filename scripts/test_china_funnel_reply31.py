import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import china_conversion_context as c
class W:now=datetime(2026,10,31,19,45,tzinfo=timezone.utc)
class ReplyFunnel(unittest.TestCase):
 def test_real_pavel207_reply_uses_whole_funnel_handler(self):
  state=dict(current=dict(day='2026-10-31',views=43464,carts=2009,orders=279),previous=dict(day='2026-10-30',views=1,carts=1,orders=1),observed_at=W.now.isoformat(),source_key='private-full',matched_clock=False)
  state['current']=c.metrics(state['current']);state['previous']=c.metrics(state['previous'])
  j=dict(request_text='Вот такой отчет за сегодня',tool_trace=[dict(name='china_saved_question',reply_text='Общая воронка WB, срез30.10. Карточка→корзина4.33%')])
  with patch('china_intraday_analysis.handle',return_value=None),patch.object(c,'collect',return_value=state) as read:
   text,trace=c.handle(W(),j,[])
  read.assert_called_once();self.assertIn('43 464',text);self.assertIn('279',text);self.assertIn('4,62%',text)
 def test_reply_does_not_turn_sku_or_ad_request_into_general_funnel(self):
  j=dict(request_text='Вот такой отчет по РК за сегодня',tool_trace=[dict(name='china_saved_question',reply_text='Общая воронка WB. Карточка→корзина')])
  with patch('china_intraday_analysis.handle',return_value=None),patch.object(c,'collect') as read:
   self.assertIsNone(c.handle(W(),j,[]))
  read.assert_not_called()
if __name__=='__main__':unittest.main()
