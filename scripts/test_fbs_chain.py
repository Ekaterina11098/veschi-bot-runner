import copy
import unittest
import fbs_document_chain as m

def ref(kind, ident):
    return {"meta": {"href": m.MS+"entity/"+kind+"/"+ident, "type": kind, "mediaType": "application/json"}}

class Cache:
    def __init__(self): self.data={}
    def get(self,key): return copy.deepcopy(self.data.get(key))
    def put(self,key,val): self.data[key]=copy.deepcopy(val)
    def pending(self): return []

class Fake:
    def __init__(self):
        self.docs={t:[] for t in m.TYPES}
        self.writes=[]
        self.supply={"id":"WB-GI-123","name":"test","done":True,"createdAt":"2026-10-20T08:00:00Z","closedAt":"2026-10-20T09:00:00Z"}
    def request(self,base,path,method="GET",body=None,params=None):
        if base==m.WB:
            if path.endswith("/order-ids"): return {"orderIds":[1,2]}
            return self.supply
        kind=path.split("/")[1]
        if method=="POST":
            doc=copy.deepcopy(body); doc.update(id=kind,name=body.get("name",kind),sum=0,**ref(kind,kind))
            self.docs[kind].append(doc); self.writes.append(kind); return doc
        if path.endswith("/positions"):
            vals=self.docs[kind][0]["positions"]
        else:
            vals=self.docs[kind]
            filt=(params or {}).get("filter","")
            if filt:
                key,val=filt.split("=",1)
                vals=[d for d in vals if d.get(key)==val]
        return {"rows":copy.deepcopy(vals),"meta":{"size":len(vals)}}

class Tests(unittest.TestCase):
    def setUp(self):
        self.t=Fake(); self.db=Cache()
        common=dict(organization=ref("organization","org"),agent=ref("counterparty","buyer"),store=ref("store","msk"))
        self.c={"templates":{t:copy.deepcopy(common) for t in m.TYPES},"scope_confirmed":True,"writes_enabled":False,"status":"configured_pending_verification"}
        self.c["templates"]["salesreturn"]["store"]=ref("store","hongkong")
        self.w=m.Worker(self.t,self.db,self.c)
        self.state={"supply":self.t.supply,"positions":[dict(quantity=2,price=0,discount=0,assortment=ref("product","p"))],"order_ids":[1,2]}
    def test_complete_chain_and_rerun(self):
        self.w.process(self.state)
        self.assertEqual(self.t.writes,list(m.TYPES))
        self.assertEqual(self.state["status"],"complete")
        self.assertEqual(m.href(self.t.docs["salesreturn"][0]["store"]),m.href(self.c["templates"]["salesreturn"]["store"]))
        self.w.process(self.state)
        self.assertEqual(len(self.t.writes),3)
    def test_later_uncertain_marker_survives_earlier_readback(self):
        self.w.process(self.state)
        self.t.docs["demand"]=[]; self.t.docs["salesreturn"]=[]
        self.state["inflight"]="demand"
        with self.assertRaises(m.Stop): self.w.process(self.state)
        self.assertEqual(self.state["inflight"],"demand")
        self.assertEqual(len(self.t.writes),3)
    def test_manual_order_blocks_create(self):
        self.t.docs["customerorder"]=[{"name":self.t.supply["id"]}]
        with self.assertRaises(m.Stop): self.w.process(self.state)
        self.assertEqual(self.t.writes,[])
    def test_disabled_run_has_no_api_calls(self):
        self.t.request=lambda *a,**k: self.fail("Disabled run made API call")
        self.assertEqual(self.w.run("run")["writes"],0)
    def test_composition_change_blocks_create(self):
        self.state["order_ids"]=[1]
        with self.assertRaises(m.Stop): self.w.process(self.state)
        self.assertEqual(self.t.writes,[])

if __name__=="__main__": unittest.main()

