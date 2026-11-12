"""Guard China FBS routing by actual WB order warehouseId, not supply names."""
import copy
import unittest
import fbs_document_chain as m

MSK = "3c67619d-f25d-11ee-0a80-0c6f000a027a"
GUANGZHOU = "2233c6a7-d906-11f1-0a80-197e004df0d2"
HK = "c599b096-a784-11f1-0a80-15f1000f8193"

def store(ident):
    return {"meta": {"href": m.MS + "entity/store/" + ident}}

class MemoryDB:
    def __init__(self): self.data = {}
    def put(self,key,val): self.data[key] = copy.deepcopy(val)
    def get(self,key): return copy.deepcopy(self.data.get(key))

class StoresOnly:
    def __init__(self): self.reads = []
    def request(self,base,path,method="GET",body=None,params=None):
        if base != m.MS or method!="GET" or not path.startswith("entity/store/"):
            raise AssertionError("Unexpected API call")
        self.reads.append(path)
        names={MSK:"МСК",GUANGZHOU:"Гуанджоу",HK:"Гонконг WB FBO"}
        return {"name":names[path.split("/")[-1]],"archived":False}

class ChinaRoutingTests(unittest.TestCase):
    def setUp(self):
        self.transport=StoresOnly()
        self.db=MemoryDB()
        c={"cabinet":"token_3","templates":{
            "customerorder":{"store":store(MSK)},
            "demand":{"store":store(MSK)},
            "salesreturn":{"store":store(HK)},
        }}
        self.worker=m.Worker(self.transport,self.db,c)
        self.state={"supply":{"id":"WB-GI-309138172","closedAt":"2026-11-12T06:57:57Z","name":"not authoritative"},
                    "positions":[{"quantity":2}],"order_ids":[1001,1002]}
        self.worker._source_warehouse_supply_id="WB-GI-309138172"

    def select(self,warehouse_ids):
        self.worker._source_warehouse_ids={1001:warehouse_ids[0],1002:warehouse_ids[1]}
        return self.worker.china_warehouse_routing(self.state,"test")

    def test_guangzhou_order_and_demand_hongkong_return(self):
        routing=self.select([2308581,2308581])
        self.assertEqual(routing["customerorder"],m.MS+"entity/store/"+GUANGZHOU)
        self.assertEqual(routing["demand"],m.MS+"entity/store/"+GUANGZHOU)
        self.assertEqual(routing["salesreturn"],m.MS+"entity/store/"+HK)
        self.assertEqual(self.state["warehouse_routing"]["wb_warehouse_id"],2308581)

    def test_msk_warehouse_selection_ignores_supply_name(self):
        self.state["supply"]["name"]="Гуанчжоу"
        routing=self.select([2126188,2126188])
        self.assertEqual(routing["demand"],m.MS+"entity/store/"+MSK)

    def test_mixed_warehouses_stop_before_document(self):
        with self.assertRaisesRegex(m.Stop,"Mixed or unknown"):
            self.select([2126188,2308581])
        self.assertEqual(self.transport.reads,[])

    def test_unknown_warehouse_stop(self):
        with self.assertRaisesRegex(m.Stop,"Unapproved WB origin"):
            self.select([9999999,9999999])

    def test_routing_frozen_across_retries(self):
        self.select([2308581,2308581])
        self.worker._source_warehouse_ids={1001:2126188,1002:2126188}
        with self.assertRaisesRegex(m.Stop,"Frozen warehouse routing"):
            self.worker.china_warehouse_routing(self.state,"test")

    def test_before_cutoff_legacy_unchanged(self):
        self.state["supply"]["closedAt"]="2026-11-11T20:00:00Z"
        self.assertIsNone(self.select([2308581,2308581]))
        self.assertEqual(self.transport.reads,[])

    def test_non_china_worker_unchanged(self):
        self.worker.c["cabinet"]="token_2"
        self.assertIsNone(self.select([2308581,2308581]))
        self.assertEqual(self.transport.reads,[])

if __name__=="__main__":
    unittest.main()
