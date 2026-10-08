import json,os,tempfile,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import select_task as s

class DailySelectorTests(unittest.TestCase):
    def test_morning_schedule_runs_three_isolated_jobs(self):
        with tempfile.NamedTemporaryFile() as output:
            with patch.dict(os.environ,{"GITHUB_EVENT_NAME":"schedule","EVENT_SCHEDULE":"17 4 * * *","GITHUB_OUTPUT":output.name}):
                s.main()
            output.seek(0)
            fields=dict(line.split("=",1) for line in output.read().decode().splitlines())
        tasks=json.loads(fields["matrix"])["include"]
        self.assertEqual([r["task"] for r in tasks],["analytics","daily_context","finance"])
        self.assertEqual(tasks[1]["group"],s.GROUPS["finance"])
        self.assertNotEqual(tasks[0]["group"],tasks[1]["group"])

    def test_stock_requests_wake_mpstats_worker_after_daily_plan_completed(self):
        now=datetime(2026,10,8,9,tzinfo=timezone.utc)
        state={"planned_day":"2026-10-08","requests":[]}
        stock={"payload":{"mpstats_requests":[{"key":"missing-day"}]},"updated_at":now.isoformat()}
        with patch.object(s,"database",side_effect=[[{"payload":state}],[],[stock]]):
            self.assertEqual(s.mpstats_work(now),[{"task":"mpstats_recovery","group":"mpstats-data"}])

    def test_already_ingested_stock_queue_does_not_wake_worker(self):
        now=datetime(2026,10,8,9,tzinfo=timezone.utc)
        state={"planned_day":"2026-10-08","requests":[],"last_stock_ingested_at":now.isoformat()}
        stock={"payload":{"mpstats_requests":[{"key":"done"}]},"updated_at":now.isoformat()}
        with patch.object(s,"database",side_effect=[[{"payload":state}],[],[stock],[]]):
            self.assertEqual(s.mpstats_work(now),[])

if __name__=="__main__":unittest.main()
