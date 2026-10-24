import unittest,io
from PIL import Image
import china_table_png as t
class Memory:
    def __init__(self):self.mem={}
    def get(self,k):return self.mem.get(k)
    def save(self,k,v,insert=False):
        if insert and k in self.mem:return False
        self.mem[k]=v;return True
class CombinedTests(unittest.TestCase):
    def test_profit_tables_and_explanations_are_one_frozen_png(self):
        w=Memory();j=dict(id=1,chat_id=-1004342917488)
        answer='## Прибыль за23.10\n| День | Начисления | Прогноз |\n| --- | --- | --- |\n| 23.10 | Нет закрытого расчёта | +100 |\n\nПрогноз предварительный.\n\n| Артикул | Наши изменения |\n| --- | --- |\n| demo | Изменений не было |'
        parts=t.delivery_parts(w,j,answer,lambda s:[s])
        self.assertEqual(len(parts),1);self.assertTrue(parts[0].startswith(t.PREFIX))
        w.active_question_id=1;blob,caption=t.photo(w,j['chat_id'],parts[0])
        picture=Image.open(io.BytesIO(blob));picture.verify();self.assertEqual(picture.width,1900)
        self.assertEqual(t.delivery_parts(w,j,answer,lambda s:[s]),parts)
    def test_in_progress_delivery_is_not_reformatted(self):
        w=Memory();j=dict(id=2,chat_id=-1004342917488)
        w.mem['china_agent:conversion_watch_delivery:v1:question:2:0']={'status':'sent'}
        answer='Прогноз прибыли\n| a | b |\n| --- | --- |\n| 1 | 2 |'
        self.assertEqual(t.delivery_parts(w,j,answer,lambda s:[s]),[answer])
if __name__=='__main__':unittest.main()

