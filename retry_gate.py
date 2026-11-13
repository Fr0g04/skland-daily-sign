import unittest
from datetime import datetime, timedelta, timezone

from retry_gate import already_done, CHINA


class RetryGateTests(unittest.TestCase):
    """门禁的新语义：不分触发方式，只要今天（UTC+8）已有成功运行就跳过。"""

    # 北京时间 2026-11-04 01:07 = UTC 11-03 17:07
    now = datetime(2026, 11, 3, 17, 7, tzinfo=timezone.utc)

    def record(self, conclusion="success", created="2026-11-03T16:07:00Z",
               run_id=1, event="schedule"):
        return {"id": run_id, "conclusion": conclusion, "created_at": created, "event": event}

    def test_same_china_day_success_skips(self):
        self.assertTrue(already_done([self.record()], 2, self.now))

    def test_no_run_does_not_skip(self):
        self.assertFalse(already_done([], 2, self.now))

    def test_failure_or_incomplete_does_not_skip(self):
        for conclusion in ("failure", "cancelled", "skipped", None):
            with self.subTest(conclusion=conclusion):
                self.assertFalse(already_done([self.record(conclusion)], 2, self.now))

    def test_previous_china_day_does_not_skip(self):
        # UTC 11-03 15:59:59 = 北京 11-03 23:59:59，属于"昨天"
        self.assertFalse(already_done([self.record(created="2026-11-03T15:59:59Z")], 2, self.now))

    def test_china_midnight_boundary_counts(self):
        # UTC 11-03 16:00:00 = 北京 11-04 00:00:00，属于"今天"
        self.assertTrue(already_done([self.record(created="2026-11-03T16:00:00Z")], 2, self.now))

    def test_current_run_not_counted(self):
        self.assertFalse(already_done([self.record(run_id=2)], 2, self.now))

    def test_any_trigger_event_counts(self):
        # 与旧版不同：手动触发的成功运行同样会挡住后续触发。
        for event in ("workflow_dispatch", "schedule"):
            with self.subTest(event=event):
                self.assertTrue(already_done([self.record(event=event)], 2, self.now))

    def test_future_run_does_not_count(self):
        # 创建时间晚于当前时刻（时钟异常）不应被当作"今天已成功"
        self.assertFalse(already_done([self.record(created="2026-11-03T20:00:00Z")], 2, self.now))

    def test_china_timezone_is_utc_plus_8(self):
        self.assertEqual(CHINA.utcoffset(None), timedelta(hours=8))


if __name__ == "__main__":
    unittest.main()
