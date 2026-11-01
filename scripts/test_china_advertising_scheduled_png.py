import unittest
from unittest.mock import patch
import china_table_png as p

class State:
    def __init__(self): self.data={}; self.active_report_key='report:a:2026-11-01'
    def get(self,k): return self.data.get(k)
    def save(self,k,v,insert=False):
        if insert and k in self.data:return False
        self.data[k]=v; return True

class ScheduledPngTests(unittest.TestCase):
    text='Данные\n\n| Артикул | ДРР |\n| --- | --- |\n| 143 | 12.34% |'
    def parts(self,w):
        with patch.object(p,'render',return_value=[b'png-bytes']):
            return p.scheduled_parts(w,w.active_report_key,-100,self.text,lambda x:[x])
    def test_frozen_and_scoped(self):
        w=State(); parts=self.parts(w); marker=parts[-1]
        self.assertTrue(marker.startswith('CHINA_SCHEDULED_TABLE_PNG:'))
        self.assertEqual(p.photo(w,-100,marker)[0],b'png-bytes')
        self.assertEqual(self.parts(w),parts)
        with self.assertRaises(PermissionError):p.photo(w,-101,marker)
        w.active_report_key='report:b:2026-11-01'
        with self.assertRaises(PermissionError):p.photo(w,-100,marker)
    def test_hash_and_answer_immutable(self):
        w=State(); marker=self.parts(w)[-1]
        with self.assertRaises(PermissionError):
            p.scheduled_parts(w,w.active_report_key,-100,self.text+'changed',lambda x:[x])
        record=next(iter(w.data.values())); record['files'][0]['sha256']='wrong'
        with self.assertRaises(ValueError):p.photo(w,-100,marker)
    def test_partial_delivery_preserved(self):
        w=State();w.data['china_agent:conversion_watch_delivery:v1:'+w.active_report_key+':part:0']={'status':'sent'}
        self.assertEqual(self.parts(w),[self.text])
    def test_plain_text_unchanged(self):
        w=State()
        self.assertEqual(p.scheduled_parts(w,w.active_report_key,-100,'plain',lambda x:[x]),['plain'])
    def test_question_route_unchanged(self):
        w=State();w.active_question_id=42
        with patch.object(p,'render',return_value=[b'png']):
            parts=p.delivery_parts(w,{'id':42,'chat_id':-100},self.text,lambda x:[x])
        self.assertEqual(p.photo(w,-100,parts[-1])[0],b'png')

if __name__=='__main__':unittest.main()
