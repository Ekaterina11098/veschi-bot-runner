import unittest
import fbs_document_chain as m
from test_fbs_chain import Fake,Cache,Tests,ref

class AnnotatedFake(Fake):
    def request(self,base,path,method="GET",body=None,params=None):
        if base==m.MS and path=="entity/customerorder/metadata":
            return {"states":[dict(name="Возврат на ФБО",**ref("state","fbo"))]}
        if base==m.MS and path=="entity/customerorder/customerorder":
            doc=self.docs["customerorder"][0]
            if method=="PUT":
                assert len(self.docs["salesreturn"])==1
                doc.update(body);self.writes.append("annotation")
            return doc
        return super().request(base,path,method,body,params)

class AnnotationTests(Tests):
    def setUp(self):
        super().setUp()
        self.t=AnnotatedFake()
        self.c["order_annotation"]={"state_name":"Возврат на ФБО"}
        self.w=m.Worker(self.t,self.db,self.c)
        self.state["supply"]["name"]="Зонты Китай"
    def test_annotation_after_return_and_idempotent(self):
        self.w.process(self.state)
        order=self.t.docs["customerorder"][0]
        self.assertEqual(order["description"],"20 10 26  Гонконг Зонты")
        for kind in m.TYPES:
            self.assertEqual(self.t.docs[kind][0]["description"],"20 10 26  Гонконг Зонты")
        self.assertEqual(m.href(order["state"]),m.href(ref("state","fbo")))
        self.assertEqual(self.t.writes,["customerorder","demand","salesreturn","annotation"])
        self.w.process(self.state)
        self.assertEqual(len(self.t.writes),4)
    def test_moscow_date(self):
        supply=dict(self.t.supply,name="Сумки Китай",closedAt="2026-10-20T22:00:00Z")
        self.assertEqual(self.w.order_annotation(supply)["description"],"21 10 26  Гонконг Сумки")
    def test_complete_chain_and_rerun(self):
        self.test_annotation_after_return_and_idempotent()
    def test_later_uncertain_marker_survives_earlier_readback(self):
        self.w.process(self.state)
        self.t.docs["demand"]=[];self.t.docs["salesreturn"]=[]
        self.state["inflight"]="demand"
        with self.assertRaises(m.Stop):self.w.process(self.state)
        self.assertEqual(self.state["inflight"],"demand")
        self.assertEqual(len(self.t.writes),4)

if __name__=="__main__":unittest.main()

