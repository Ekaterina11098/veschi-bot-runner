import copy
import unittest
from unittest.mock import patch
import fbs_comment_audit as a

class AuditTests(unittest.TestCase):
    def fixture(self):
        docs = {kind: {"id": kind, "description": "shared" if kind == "customerorder" else None} for kind in a.TYPES}
        class Transport:
            def __init__(self): self.writes = []
            def request(self, base, path, method="GET", body=None):
                kind = path.split("/")[1]
                if method == "PUT":
                    self.writes.append(copy.deepcopy(body))
                    docs[kind].update(body)
                return copy.deepcopy(docs[kind])
        class Cache:
            def get(self, key):
                return {"order_annotation": True, "templates": {kind: {} for kind in a.TYPES}}
        state = {"supply": {"id": "pilot"}, "positions": [{"quantity": 17}],
                 "order_annotation": {"description": "shared"},
                 "documents": {kind: {"id": kind} for kind in a.TYPES}}
        return Transport(), Cache(), state

    def test_repair_is_comment_only_and_repeat_is_noop(self):
        t, db, state = self.fixture()
        with patch.object(a.Worker, "verify") as verify:
            result = a.audit_chain(t, db, "china", state)
            self.assertEqual(result["repaired"], ["demand", "salesreturn"])
            self.assertEqual(t.writes, [{"description": "shared"}] * 2)
            self.assertEqual(verify.call_count, 6)
            self.assertEqual(a.audit_chain(t, db, "china", state)["repaired"], [])
            self.assertEqual(len(t.writes), 2)

    def test_preflight_failure_prevents_every_write(self):
        t, db, state = self.fixture()
        with patch.object(a.Worker, "verify", side_effect=a.Stop("positions differ")):
            with self.assertRaises(a.Stop): a.audit_chain(t, db, "china", state)
        self.assertEqual(t.writes, [])

    def test_missing_expected_comment_blocks(self):
        t, db, state = self.fixture()
        state["order_annotation"] = {}
        with self.assertRaises(a.Stop): a.audit_chain(t, db, "china", state)
        self.assertEqual(t.writes, [])

if __name__ == "__main__": unittest.main()
