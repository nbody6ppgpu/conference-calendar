from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from cleanup_calendar import apply_cleanup, plan_cleanup, verify_cleanup  # noqa: E402
from calendar_core import ValidationError  # noqa: E402


def conference_block(conference_id: str, end_date: str) -> str:
    start_date = end_date
    return f"""  - id: {conference_id}
    title: {conference_id}
    url: https://example.com/{conference_id}
    location: Somewhere
    start_date: {start_date}
    end_date: {end_date}
    registration_deadlines: []
    abstract_deadlines: []
    registration_display: \"\"
    abstract_display: \"\"
    comments: \"\"
"""


def calendar_text(past: list[str], active: list[str]) -> str:
    return "conferences:\n  # Past events\n" + "".join(past) + "  # Conference Calendar\n" + "".join(active)


class CleanupCalendarTests(unittest.TestCase):
    def test_plan_finds_only_the_overdue_active_entry(self) -> None:
        source = calendar_text(
            past=[conference_block("already-past", "2026-07-03")],
            active=[conference_block("expanding-horizons-2026", "2026-07-17")],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "conferences.yml"
            path.write_text(source, encoding="utf-8")
            plan = plan_cleanup(path, date(2026, 8, 4))
            self.assertEqual(plan.overdue_ids, ("expanding-horizons-2026",))
            self.assertEqual(plan.expected_ids, ("expanding-horizons-2026",))
            self.assertTrue(plan.changed)

    def test_dates_drive_reorganization_even_when_existing_marker_is_wrong(self) -> None:
        source = calendar_text(
            past=[conference_block("future-in-past", "2026-09-10")],
            active=[
                conference_block("expired-active", "2026-07-17"),
                conference_block("future-active", "2026-09-11"),
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "conferences.yml"
            path.write_text(source, encoding="utf-8")

            plan = plan_cleanup(path, date(2026, 8, 4))
            self.assertEqual(plan.overdue_ids, ("expired-active",))
            self.assertEqual(plan.expected_ids, ("future-in-past", "expired-active"))

            apply_cleanup(path, date(2026, 8, 4))
            result = path.read_text(encoding="utf-8")
            marker = result.index("  # Conference Calendar")
            self.assertLess(result.index("expired-active"), marker)
            self.assertLess(marker, result.index("future-in-past"))
            baseline_path = Path(temp_dir) / "baseline.yml"
            baseline_path.write_text(source, encoding="utf-8")
            verify_cleanup(
                path,
                date(2026, 8, 4),
                ("future-in-past", "expired-active"),
                baseline_path,
            )

            second_plan = apply_cleanup(path, date(2026, 8, 4))
            self.assertFalse(second_plan.changed)

    def test_missing_section_marker_is_rejected(self) -> None:
        source = calendar_text([], [conference_block("future", "2026-09-10")]).replace(
            "  # Conference Calendar\n", ""
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "conferences.yml"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "Conference Calendar"):
                plan_cleanup(path, date(2026, 8, 4))


if __name__ == "__main__":
    unittest.main()
