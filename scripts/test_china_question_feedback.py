import unittest,copy,types,sys
from datetime import datetime,timezone
from unittest.mock import patch
import china_question_feedback as f
from conversion_watches import Worker,RECEIPTS
NOW=datetime(2026,10,24,4,tzinfo=timezone.utc)
def job(text):
    return dict(id=101,agent_id='china',chat_id=-1004342917488,sender_id=7,
      status='pending',attempts=0,request_text=text,tool_trace=[dict(name='china_saved_question',message_id=42)])
class W(Worker):
    def __init__(self,text):
        self.now=NOW;self.mem={};self.sent=[];self.j=job(text);self.history=[];self.analyses=0
        self.db=self.database;self.transport=self.send
    def config(self):return dict(chat_id=self.j['chat_id'])
    def database(self,method,table,params=None,body=None,prefer=None):
        if method=='GET' and str((params or {}).get('id','')).startswith('lt.'):return self.history
        if method=='GET':return [copy.deepcopy(self.j)]
        self.j.update(body or {});return [copy.deepcopy(self.j)]
    def get(self,k):return copy.deepcopy(self.mem.get(k))
    def save(self,k,v,insert=False):
        if insert and k in self.mem:return False
        self.mem[k]=copy.deepcopy(v);return True
    def send(self,chat,text):
        self.sent.append(text);return dict(ok=True,result=dict(chat={'id':chat},message_id=len(self.sent)))
    def saved_question(self,j,h):
        self.analyses+=1;self.effective_request=j['request_text']
        return 'Готовый отчёт: продажи и прибыль.',[]
def modules():
    migration=types.ModuleType('china_chat_migration');migration.previous_chats=lambda *a:[]
    table=types.ModuleType('china_table_png');table.delivery_parts=lambda w,j,a,s:[a]
    rule=types.ModuleType('china_ad_rule');rule.bind=lambda *a:None
    model=types.ModuleType('china_model_transport');model.ModelResponseError=type('ModelResponseError',(Exception,),{})
    return {'china_chat_migration':migration,'china_table_png':table,'china_ad_rule':rule,'china_model_transport':model}
class FeedbackTests(unittest.TestCase):
    def test_ambiguous_report_asks_type_before_collection(self):
        w=W('Привет робот дай пожалуйста отчет за вчера сейчас')
        with patch.dict(sys.modules,modules()):self.assertEqual(w.question(101),'sent')
        self.assertEqual(w.analyses,0);self.assertEqual(len(w.sent),1)
        self.assertIn('23.10.2026',w.sent[0]);self.assertIn('реклама и ДРР',w.sent[0])
        self.assertFalse(any('question_ack' in k for k in w.mem))
    def test_explicit_types_do_not_require_another_choice(self):
        for t in ['Дай отчет по продажам за вчера','Пришли отчет по рекламе','Нужен отчет по ценам за3дня','Покажи убыточные товары в отчете сейчас']:
            self.assertIsNone(f.clarification(job(t),[],NOW))
    def test_known_reply_context_avoids_redundant_question(self):
        j=job('Дай такой же отчёт за вчера');j['tool_trace'][0]['reply_text']='Китай · реклама и ДРР'
        self.assertIsNone(f.clarification(j,[],NOW))
    def test_unrelated_old_history_is_not_an_implicit_choice(self):
        self.assertIsNotNone(f.clarification(job('дай отчет за вчера'),[dict(answer='Продажи и прибыль')],NOW))
    def test_short_type_selection_keeps_original_period(self):
        h=[dict(request_text='дай отчет за вчера',answer='Какой отчёт за23.10.2026 нужен?')]
        j=f.resolved_job(job('Продажи и прибыль'),h)
        self.assertIn('дай отчет за вчера',j['request_text']);self.assertIn('Уточнение',j['request_text'])
    def test_explanation_and_approval_are_not_report_requests(self):
        for t in ['Какие бывают отчеты?','Согласен','Делай','Не готовь отчет за вчера']:
            self.assertIsNone(f.clarification(job(t),[],NOW));self.assertFalse(f.request(t))
    def test_ack_before_work_and_final_answer(self):
        w=W('Дай отчет по продажам за вчера')
        with patch.dict(sys.modules,modules()):w.question(101)
        self.assertEqual(w.sent,['Принял, готовлю отчёт.','Готовый отчёт: продажи и прибыль.'])
        self.assertEqual(w.analyses,1)
    def test_sent_and_uncertain_ack_never_blindly_repeat(self):
        w=W('Пришли отчет по рекламе')
        with patch.dict(sys.modules,modules()):
            f.acknowledge(w,w.j);f.acknowledge(w,w.j)
            self.assertEqual(len(w.sent),1)
            w.mem[RECEIPTS+'question_ack:101']['status']='uncertain'
            self.assertEqual(f.acknowledge(w,w.j),'uncertain');self.assertEqual(len(w.sent),1)
    def test_failed_ack_does_not_block_analysis(self):
        w=W('Пришли отчет по продажам за вчера');old=w.send_once
        def send_once(key,*args):
            if key.startswith('question_ack'):raise OSError('network')
            return old(key,*args)
        w.send_once=send_once
        with patch.dict(sys.modules,modules()):w.question(101)
        self.assertEqual(w.analyses,1);self.assertEqual(w.j['status'],'done')
    def test_failure_notice_once(self):
        w=W('Пришли отчет по продажам за вчера')
        with patch.dict(sys.modules,modules()):
            f.failure_notice(w,w.j);f.failure_notice(w,w.j)
        self.assertEqual(len(w.sent),1)
if __name__=='__main__':unittest.main()

