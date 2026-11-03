import unittest
from datetime import datetime, timezone

from retry_gate import should_run, RETRY_CRON


class RetryTests(unittest.TestCase):
    now = datetime(2026, 11, 3, 17, 7, tzinfo=timezone.utc)  # 北京 11月4日 01:07

    def run_record(self, conclusion="success", created="2026-11-03T16:07:00Z", event="schedule", run_id=1):
        return {"id": run_id, "conclusion": conclusion, "created_at": created, "event": event}

    def test_same_china_day_success_skips(self):
        self.assertFalse(should_run("schedule", RETRY_CRON, [self.run_record()], 2, self.now))

    def test_failure_or_missing_run_retries(self):
        for runs in ([], [self.run_record("failure")], [self.run_record(None)]):
            self.assertTrue(should_run("schedule", RETRY_CRON, runs, 2, self.now))

    def test_previous_china_day_does_not_skip(self):
        self.assertTrue(should_run("schedule", RETRY_CRON, [self.run_record(created="2026-11-03T15:59:59Z")], 2, self.now))

    def test_manual_and_midnight_always_run(self):
        for event, schedule in (("workflow_dispatch", RETRY_CRON), ("schedule", "7 16 * * *")):
            self.assertTrue(should_run(event, schedule, [self.run_record()], 2, self.now))

    def test_manual_success_and_current_run_not_counted(self):
        self.assertTrue(should_run("schedule", RETRY_CRON, [self.run_record(event="workflow_dispatch")], 2, self.now))
        self.assertTrue(should_run("schedule", RETRY_CRON, [self.run_record(run_id=2)], 2, self.now))
