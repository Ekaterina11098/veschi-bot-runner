"""Failure injection tests; never use live credentials or marketplace APIs."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import run_private as runner
import select_task as selector


class IsolationTests(unittest.TestCase):
    def setUp(self):
        guard=patch.object(selector,"review_inbox_work",return_value=[])
        guard.start()
        self.addCleanup(guard.stop)
        guard=patch.object(selector,"finance_retry_work",return_value=[])
        guard.start()
        self.addCleanup(guard.stop)
        guard=patch.object(selector,"agent_due",return_value=False)
        guard.start()
        self.addCleanup(guard.stop)
        guard=patch.object(selector,"business_due",return_value=False)
        guard.start()
        self.addCleanup(guard.stop)
        guard=patch.object(selector,'mpstats_work',return_value=[])
        guard.start()
        self.addCleanup(guard.stop)
        guard=patch.object(selector,'research_work',return_value=[])
        guard.start()
        self.addCleanup(guard.stop)

    def test_agent_is_independent_of_stock_and_finance(self):
        self.assertNotEqual(selector.GROUPS["agent"],selector.GROUPS["stock"])
        self.assertNotEqual(selector.GROUPS["agent"],selector.GROUPS["finance"])
        with patch.object(selector,"agent_due",return_value=True),patch.object(selector,"database",return_value=[]),patch.object(selector,"evening_recovery_work",return_value=[]):
            self.assertEqual(selector.queue_work(),[{"task":"agent","group":"advertising-agent-conversations"}])
    def test_failed_queue_lookup_does_not_hide_other_due_work(self):
        with patch.object(selector, "evening_recovery_work", return_value=[]), patch.object(selector, "database", side_effect=[
                RuntimeError("reviews unavailable"), [{"feedback_id":"approved"}],
                [{"payload":{"pending":True,"due":0}}]]):
            work = selector.queue_work()
        self.assertEqual([item["task"] for item in work],
                         ["telegram_queue","review_queue","stock_retry"])
        self.assertEqual(len({item["group"] for item in work}), 3)

    def test_idle_queue_has_no_workers(self):
        with patch.object(selector, "evening_recovery_work", return_value=[]), patch.object(selector, "database", return_value=[]):
            self.assertEqual(selector.queue_work(), [])

    def test_stock_retry_waits_for_due_time(self):
        with patch.object(selector, "evening_recovery_work", return_value=[]), patch.object(selector, "database", side_effect=[[],[],
                [{"payload":{"pending":True,"due":float("inf")}}]]):
            self.assertEqual(selector.queue_work(), [])

    def test_stock_writers_share_lock_but_commands_are_independent(self):
        self.assertEqual(selector.GROUPS["stock"], selector.GROUPS["stock_retry"])
        self.assertNotEqual(selector.GROUPS["stock"], selector.GROUPS["telegram_queue"])
        self.assertEqual(selector.GROUPS["finance"], selector.GROUPS["advertising"])

    def test_dispatch_output_contains_matrix(self):
        with tempfile.NamedTemporaryFile() as output:
            with patch.dict(os.environ, {"GITHUB_EVENT_NAME":"workflow_dispatch",
                    "REQUESTED_TASK":"stock","GITHUB_OUTPUT":output.name}):
                selector.main()
            with open(output.name) as saved:
                values = dict(line.rstrip().split("=",1) for line in saved)
        self.assertEqual(json.loads(values["matrix"]), {"include":[
            {"task":"stock","group":"stock-and-commands"}]})

    def test_evening_recovery_window_includes_next_morning(self):
        for at,expected in (("2026-10-05T19:29:00+00:00",None),
                            ("2026-10-05T19:30:00+00:00",None),
                            ("2026-10-05T20:00:00+00:00","2026-10-05"),
                            ("2026-10-06T05:10:00+00:00","2026-10-05"),
                            ("2026-10-06T06:00:00+00:00",None)):
            self.assertEqual(selector.evening_target_date(datetime.fromisoformat(at)),expected)

    def test_missing_evening_marker_enqueues_only_advertising_recovery(self):
        at=datetime.fromisoformat("2026-10-06T05:10:00+00:00")
        with patch.object(selector,"database",return_value=[]):
            self.assertEqual(selector.evening_recovery_work(at),[{
                "task":"advertising_report_retry","group":"advertising-and-finance"}])

    def test_completed_evening_is_not_repeated(self):
        at=datetime.fromisoformat("2026-10-06T05:10:00+00:00")
        with patch.object(selector,"database",return_value=[{
                "payload":{"date":"2026-10-05","complete":True}}]):
            self.assertEqual(selector.evening_recovery_work(at),[])

    def test_incomplete_delivery_and_backend_failure_are_retried(self):
        at=datetime.fromisoformat("2026-10-06T05:10:00+00:00")
        with patch.object(selector,"database",return_value=[{
                "payload":{"date":"2026-10-05","complete":False}}]):
            self.assertEqual(len(selector.evening_recovery_work(at)),1)
        with patch.object(selector,"database",side_effect=RuntimeError("offline")):
            self.assertEqual(len(selector.evening_recovery_work(at)),1)

    def test_legacy_queue_runs_siblings_after_failure(self):
        with patch.object(runner.subprocess, "run", side_effect=[
                SimpleNamespace(returncode=1),SimpleNamespace(returncode=0),
                SimpleNamespace(returncode=0),SimpleNamespace(returncode=0)]) as run:
            with self.assertRaises(RuntimeError):
                runner.queue()
        self.assertEqual([call.args[0][-1] for call in run.call_args_list],
                         ["review_queue","telegram_queue","stock_retry","business_agent"])

    def test_business_agents_have_their_own_worker_group(self):
        with patch.object(selector,"business_due",return_value=True),patch.object(selector,"database",return_value=[]),patch.object(selector,"evening_recovery_work",return_value=[]):
            self.assertEqual(selector.queue_work(),[{"task":"business_agent","group":"business-agent-conversations"}])
        self.assertNotEqual(selector.GROUPS['business_agent'],selector.GROUPS['stock'])
        self.assertNotEqual(selector.GROUPS['business_agent'],selector.GROUPS['agent'])

    def test_failed_stock_retry_finishes_original_claim_as_failed(self):
        db = Mock(side_effect=[{"claim":"original"},True])
        with patch.dict("sys.modules", {"wb_runtime_state":SimpleNamespace(db=db)}), \
                patch.object(runner, "validate_stock", side_effect=RuntimeError("failed")), \
                patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                runner.stock_retry()
        self.assertEqual(db.call_args.kwargs["payload"],
                         {"p_claim":"original","p_success":False})

    def test_idle_stock_retry_never_validates_or_writes(self):
        with patch.dict("sys.modules", {"wb_runtime_state":SimpleNamespace(db=Mock(return_value=None))}), \
                patch.object(runner, "execute") as execute, \
                patch.object(runner, "validate_stock") as validate:
            runner.stock_retry()
        execute.assert_not_called()
        validate.assert_not_called()

class FinanceRetryTests(unittest.TestCase):
    def test_partial_cache_refresh_does_not_hide_pending_retry(self):
        rows=[{"status":"partial", "collected_at":"2026-10-07T07:45:27+00:00"},
              {"status":"deferred", "collected_at":"2026-10-07T07:43:23+00:00",
               "detail":"Finance API 429; retry_after=42800"}]
        with patch.object(selector,"database",return_value=rows):
            self.assertEqual(selector.finance_retry_work(datetime.fromisoformat("2026-10-07T19:37:00+00:00")),[])
            self.assertEqual(selector.finance_retry_work(datetime.fromisoformat("2026-10-07T19:38:00+00:00")),
                             [{"task":"finance_retry","group":selector.GROUPS["finance"]}])
            for status in ("complete","error"):
                rows.insert(0,{"status":status})
                self.assertEqual(selector.finance_retry_work(datetime.fromisoformat("2026-10-07T19:38:00+00:00")),[])
                rows.pop(0)
    def test_retry_waits_for_wb_cooldown_and_uses_shared_lock(self):
        row = {"status": "deferred", "collected_at": "2026-10-07T07:19:39+00:00",
               "detail": "Finance API 429; retry_after=650"}
        with patch.object(selector, "database", return_value=[row]):
            self.assertEqual(selector.finance_retry_work(datetime.fromisoformat("2026-10-07T07:30:00+00:00")), [])
            work = selector.finance_retry_work(datetime.fromisoformat("2026-10-07T07:32:00+00:00"))
            self.assertEqual(work, [{"task": "finance_retry", "group": selector.GROUPS["finance"]}])
            self.assertEqual(selector.finance_retry_work(datetime.fromisoformat("2026-10-08T07:32:00+00:00")), [])

    def test_completed_or_unknown_state_does_not_retry(self):
        for rows in ([], [{"status": "complete"}], [{"status": "partial"}], [{"status": "error"}]):
            with patch.object(selector, "database", return_value=rows):
                self.assertEqual(selector.finance_retry_work(), [])
        with patch.object(selector, "database", side_effect=RuntimeError("offline")):
            self.assertEqual(selector.finance_retry_work(), [])

    def test_queued_retry_rechecks_state_before_request(self):
        with patch.object(selector, "finance_retry_work", return_value=[]), patch.object(runner.os, "chdir"), patch.object(runner, "execute") as execute:
            runner.main("finance_retry")
        execute.assert_not_called()

class ReviewInboxSelectorTests(unittest.TestCase):
    def test_before_morning_does_not_query(self):
        with patch.object(selector,'database') as db:
            self.assertEqual(selector.review_inbox_work(datetime.fromisoformat('2026-10-09T04:44:00+00:00')),[])
            db.assert_not_called()
    def test_missing_states_are_initialized(self):
        with patch.object(selector,'database',return_value=[]):
            self.assertEqual(selector.review_inbox_work(datetime.fromisoformat('2026-10-09T08:00:00+00:00')),[{'task':'review_inbox_retry','group':'review-replies'}])
    def test_complete_today_waits_and_due_retry_runs(self):
        rows=[{'payload':{'observed_at':'2026-10-09T07:00:00+00:00'}} for _ in range(3)]
        at=datetime.fromisoformat('2026-10-09T08:00:00+00:00')
        with patch.object(selector,'database',return_value=rows):
            self.assertEqual(selector.review_inbox_work(at),[])
            rows[0]['payload']['next_retry_at']='2026-10-09T09:00:00+00:00'
            self.assertEqual(selector.review_inbox_work(at),[])
            rows[0]['payload']['next_retry_at']='2026-10-09T07:59:00+00:00'
            self.assertEqual(len(selector.review_inbox_work(at)),1)
    def test_database_failure_is_safe(self):
        with patch.object(selector,'database',side_effect=RuntimeError('offline')):
            self.assertEqual(selector.review_inbox_work(datetime.fromisoformat('2026-10-09T08:00:00+00:00')),[])

if __name__ == "__main__":
    unittest.main()


