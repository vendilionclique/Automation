import unittest
from datetime import datetime, timedelta

from modules.visual_scheduler import (
    SchedulerConfig,
    _assign_sessions,
    _choose_due_session,
)


class VisualSchedulerTests(unittest.TestCase):
    def test_interval_schedule_makes_sessions_due_from_plan_creation(self):
        base = datetime(2026, 5, 16, 9, 0, 0)
        selected = [{"keyword": f"kw{i}"} for i in range(4)]
        scheduler = SchedulerConfig(daily_session_count=4, session_due_interval_minutes=3)

        sessions = _assign_sessions(selected, 4, base, scheduler)

        self.assertEqual(sessions[0]["due_at"], "2026-05-16T09:00:00")
        self.assertEqual(sessions[1]["due_at"], "2026-05-16T09:03:00")
        self.assertEqual(sessions[3]["schedule_mode"], "interval_from_plan_start")

        manifest = {
            "records": [
                {"status": "success", "extra": {"daily_session_index": 1}},
                {"status": "pending", "extra": {"daily_session_index": 2}},
                {"status": "pending", "extra": {"daily_session_index": 3}},
            ]
        }
        plan = {"daily_session_count": 4, "sessions": sessions}

        self.assertEqual(_choose_due_session(plan, manifest, now=base + timedelta(minutes=2)), 0)
        self.assertEqual(_choose_due_session(plan, manifest, now=base + timedelta(minutes=3)), 2)
        self.assertEqual(_choose_due_session(plan, manifest, now=base + timedelta(minutes=6)), 2)

    def test_fixed_session_due_times_are_explicit_and_ordered(self):
        base = datetime(2026, 5, 16, 8, 30, 0)
        selected = [{"keyword": f"kw{i}"} for i in range(4)]
        scheduler = SchedulerConfig(
            daily_session_count=4,
            session_due_times="09:00,13:00,17:00,21:00",
        )

        sessions = _assign_sessions(selected, 4, base, scheduler)
        manifest = {
            "records": [
                {"status": "pending", "extra": {"daily_session_index": 1}},
                {"status": "pending", "extra": {"daily_session_index": 2}},
            ]
        }
        plan = {"daily_session_count": 4, "sessions": sessions}

        self.assertEqual(sessions[0]["due_at"], "2026-05-16T09:00:00")
        self.assertEqual(sessions[1]["due_time"], "13:00")
        self.assertEqual(sessions[0]["schedule_mode"], "fixed_time")
        self.assertEqual(_choose_due_session(plan, manifest, now=base.replace(hour=8, minute=59)), 0)
        self.assertEqual(_choose_due_session(plan, manifest, now=base.replace(hour=9, minute=0)), 1)

    def test_fixed_session_due_times_count_must_match_session_count(self):
        with self.assertRaises(ValueError):
            _assign_sessions(
                [{"keyword": "kw"}],
                4,
                datetime(2026, 5, 16, 9, 0, 0),
                SchedulerConfig(daily_session_count=4, session_due_times="09:00,13:00"),
            )

    def test_fixed_session_due_times_must_be_strictly_increasing(self):
        base = datetime(2026, 5, 16, 8, 30, 0)
        with self.assertRaises(ValueError):
            _assign_sessions(
                [{"keyword": f"kw{i}"} for i in range(4)],
                4,
                base,
                SchedulerConfig(daily_session_count=4, session_due_times="13:00,09:00,17:00,21:00"),
            )
        with self.assertRaises(ValueError):
            _assign_sessions(
                [{"keyword": f"kw{i}"} for i in range(4)],
                4,
                base,
                SchedulerConfig(daily_session_count=4, session_due_times="09:00,09:00,17:00,21:00"),
            )

    def test_legacy_plan_without_due_at_uses_even_day_fallback(self):
        sessions = [
            {"session_index": 1, "keyword_count": 1, "status": "pending"},
            {"session_index": 2, "keyword_count": 1, "status": "pending"},
            {"session_index": 3, "keyword_count": 1, "status": "pending"},
            {"session_index": 4, "keyword_count": 1, "status": "pending"},
        ]
        manifest = {
            "records": [
                {"status": "success", "extra": {"daily_session_index": 1}},
                {"status": "pending", "extra": {"daily_session_index": 2}},
            ]
        }
        plan = {"daily_session_count": 4, "sessions": sessions}

        self.assertEqual(_choose_due_session(plan, manifest, now=datetime(2026, 5, 16, 8, 0)), 2)

    def test_partial_or_invalid_due_at_fails_loudly(self):
        manifest = {
            "records": [
                {"status": "pending", "extra": {"daily_session_index": 1}},
                {"status": "pending", "extra": {"daily_session_index": 2}},
            ]
        }
        partial_plan = {
            "daily_session_count": 2,
            "sessions": [
                {"session_index": 1, "due_at": "2026-05-16T09:00:00"},
                {"session_index": 2},
            ],
        }
        invalid_plan = {
            "daily_session_count": 2,
            "sessions": [
                {"session_index": 1, "due_at": "not-a-time"},
                {"session_index": 2, "due_at": "2026-05-16T10:00:00"},
            ],
        }

        with self.assertRaises(ValueError):
            _choose_due_session(partial_plan, manifest, now=datetime(2026, 5, 16, 9, 0))
        with self.assertRaises(ValueError):
            _choose_due_session(invalid_plan, manifest, now=datetime(2026, 5, 16, 9, 0))

    def test_fixed_session_due_times_catch_up_from_current_time(self):
        base = datetime(2026, 5, 16, 15, 0, 0)
        selected = [{"keyword": f"kw{i}"} for i in range(4)]
        scheduler = SchedulerConfig(
            daily_session_count=4,
            session_due_times="09:00,13:00,17:00,21:00",
        )
        sessions = _assign_sessions(selected, 4, base, scheduler)
        manifest = {
            "records": [
                {"status": "success", "extra": {"daily_session_index": 1}},
                {"status": "pending", "extra": {"daily_session_index": 2}},
                {"status": "pending", "extra": {"daily_session_index": 3}},
            ]
        }
        plan = {"daily_session_count": 4, "sessions": sessions}

        self.assertEqual(_choose_due_session(plan, manifest, now=base), 2)


if __name__ == "__main__":
    unittest.main()
