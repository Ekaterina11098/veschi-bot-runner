import copy
import io
import unittest
from china_table_png import blocks, delivery_parts, photo, render, PREFIX

TABLE='Учебный пример.\n\n| Артикул | Факты | Рекомендация |\n|---|---|---|\n| DEMO-001 | Условный показатель 3→2% | Сохранить уже сниженную ставку |\n\nНичего не менял.'
class Store:
    active_question_id=99
    def __init__(self): self.data={}
    def get(self,k): return copy.deepcopy(self.data.get(k))
    def save(self,k,v,insert=False):
        if insert and k in self.data:return False
        self.data[k]=copy.deepcopy(v);return True
class Tables(unittest.TestCase):
    def test_mixed_text_png_frozen_scope(self):
        w=Store();job=dict(id=99,chat_id=-1004342917488)
        parts=delivery_parts(w,job,TABLE,lambda t:[t])
        self.assertEqual(parts[0],'Учебный пример.');self.assertTrue(parts[1].startswith(PREFIX));self.assertEqual(parts[2],'Ничего не менял.')
        self.assertEqual(delivery_parts(w,job,TABLE,lambda t:[t]),parts)
        blob,_=photo(w,job['chat_id'],parts[1]);self.assertTrue(blob.startswith(b'\x89PNG'))
        with self.assertRaises(PermissionError):photo(w,1,parts[1])
        w.active_question_id=100
        with self.assertRaises(PermissionError):photo(w,job['chat_id'],parts[1])
    def test_no_accidental_table_or_code_conversion(self):
        self.assertFalse(any(k=='table' for k,_ in blocks('a | b\nnot a divider\nx | y')))
        self.assertFalse(any(k=='table' for k,_ in blocks('```\n| a | b |\n|---|---|\n| c | d |\n```')))
    def test_preserve_existing_partial_delivery(self):
        w=Store();w.data['china_agent:conversion_watch_delivery:v1:question:99:0']={'status':'sent'}
        self.assertEqual(delivery_parts(w,dict(id=99,chat_id=1),TABLE,lambda t:[t]),[TABLE])
    def test_pagination_and_all_rows(self):
        from PIL import Image
        rows=[[str(i),'Длинная конкретная рекомендация '*8] for i in range(35)]
        pages=render(['Артикул','Рекомендация'],rows)
        self.assertGreater(len(pages),1)
        for b in pages:
            im=Image.open(io.BytesIO(b));self.assertLessEqual(im.height,2450);self.assertLess(im.width+im.height,10000)
    def test_multiple_tables_and_hash(self):
        w=Store();job=dict(id=99,chat_id=1)
        parts=delivery_parts(w,job,TABLE+'\n\n'+TABLE,lambda t:[t])
        markers=[p for p in parts if p.startswith(PREFIX)];self.assertEqual(len(markers),2)
        key=markers[0][len(PREFIX):].rsplit(':',1)[0];w.data[key]['files'][0]['sha256']='bad'
        with self.assertRaises(ValueError):photo(w,1,markers[0])
if __name__=='__main__':unittest.main()

