from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from calendar_core import (  # noqa: E402
    ValidationError,
    build_ics,
    build_markdown,
    build_reminder_payload,
    deadline_display,
    find_reminders,
    load_conferences,
    stable_uid,
)


def write_yaml(payload: dict) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
    with handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
    return Path(handle.name)


class CalendarCoreTests(unittest.TestCase):
    def test_validation_rejects_missing_required_fields(self) -> None:
        path = write_yaml({"conferences": [{"id": "broken"}]})
        with self.assertRaisesRegex(ValidationError, "missing required fields"):
            load_conferences(path)

    def test_validation_rejects_invalid_date_and_duplicate_ids(self) -> None:
        path = write_yaml(
            {
                "conferences": [
                    {
                        "id": "dup",
                        "title": "One",
                        "url": "https://example.com/1",
                        "location": "Somewhere",
                        "start_date": "2026-02-30",
                        "end_date": "2026-03-01",
                        "registration_deadlines": [],
                        "abstract_deadlines": [],
                        "registration_display": "",
                        "abstract_display": "",
                        "comments": "",
                    },
                    {
                        "id": "dup",
                        "title": "Two",
                        "url": "https://example.com/2",
                        "location": "Elsewhere",
                        "start_date": "2026-03-02",
                        "end_date": "2026-03-03",
                        "registration_deadlines": [],
                        "abstract_deadlines": [],
                        "registration_display": "",
                        "abstract_display": "",
                        "comments": "",
                    },
                ]
            }
        )
        with self.assertRaisesRegex(ValidationError, "YYYY-MM-DD format"):
            load_conferences(path)

    def test_validation_rejects_end_date_before_start_date(self) -> None:
        path = write_yaml(
            {
                "conferences": [
                    {
                        "id": "broken-range",
                        "title": "Broken",
                        "url": "https://example.com",
                        "location": "Somewhere",
                        "start_date": "2026-04-02",
                        "end_date": "2026-04-01",
                        "registration_deadlines": [],
                        "abstract_deadlines": [],
                        "registration_display": "",
                        "abstract_display": "",
                        "comments": "",
                    }
                ]
            }
        )
        with self.assertRaisesRegex(ValidationError, "must not be earlier"):
            load_conferences(path)

    def test_markdown_splits_and_sorts_upcoming_and_past(self) -> None:
        path = write_yaml(
            {
                "conferences": [
                    {
                        "id": "future-b",
                        "title": "Future B",
                        "url": "https://example.com/b",
                        "location": "B",
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-02",
                        "registration_deadlines": [],
                        "abstract_deadlines": [],
                        "registration_display": "TBA",
                        "abstract_display": "",
                        "comments": "",
                    },
                    {
                        "id": "past-a",
                        "title": "Past A",
                        "url": "https://example.com/a",
                        "location": "A",
                        "start_date": "2026-03-01",
                        "end_date": "2026-03-02",
                        "registration_deadlines": [],
                        "abstract_deadlines": [],
                        "registration_display": "",
                        "abstract_display": "",
                        "comments": "",
                    },
                    {
                        "id": "future-a",
                        "title": "Future A",
                        "url": "https://example.com/c",
                        "location": "C",
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-02",
                        "registration_deadlines": [],
                        "abstract_deadlines": [],
                        "registration_display": "",
                        "abstract_display": "?",
                        "comments": "",
                    },
                ]
            }
        )
        conferences = load_conferences(path)
        markdown = build_markdown(conferences, today=__import__("datetime").date(2026, 3, 30))
        self.assertLess(markdown.index("Future A"), markdown.index("Future B"))
        self.assertIn("## Past events", markdown)
        self.assertIn("Past A", markdown.split("## Past events", 1)[1])
        self.assertIn("TBA", markdown)
        self.assertIn("?", markdown)

    def test_auto_display_formats_multiple_deadlines(self) -> None:
        path = write_yaml(
            {
                "conferences": [
                    {
                        "id": "deadline-test",
                        "title": "Deadline Test",
                        "url": "https://example.com",
                        "location": "Somewhere",
                        "start_date": "2026-07-01",
                        "end_date": "2026-07-03",
                        "registration_deadlines": [
                            {"label": "Early bird", "date": "2026-05-01"},
                            {"label": "Regular", "date": "2026-06-01"},
                        ],
                        "abstract_deadlines": [],
                        "registration_display": "",
                        "abstract_display": "open",
                        "comments": "",
                    }
                ]
            }
        )
        conferences = load_conferences(path)
        conference = conferences[0]
        self.assertEqual(
            deadline_display(conference.registration_deadlines, conference.registration_display),
            "Early bird: May 1 2026; Regular: June 1 2026",
        )
        self.assertEqual(deadline_display(conference.abstract_deadlines, conference.abstract_display), "open")

    def test_ics_merges_same_day_deadlines_and_adds_two_day_alarm(self) -> None:
        path = write_yaml(
            {
                "conferences": [
                    {
                        "id": "ics-test",
                        "title": "ICS Test",
                        "url": "https://example.com",
                        "location": "Somewhere",
                        "start_date": "2026-04-10",
                        "end_date": "2026-04-12",
                        "registration_deadlines": [{"label": "Registration", "date": "2026-04-01"}],
                        "abstract_deadlines": [
                            {"label": "Poster", "date": "2026-04-01"},
                            {"label": "Abstract", "date": "2026-03-28"},
                        ],
                        "registration_display": "",
                        "abstract_display": "",
                        "comments": "",
                    }
                ]
            }
        )
        conferences = load_conferences(path)
        ics_one = build_ics(conferences)
        ics_two = build_ics(conferences)
        self.assertEqual(ics_one.count("BEGIN:VEVENT"), 2)
        self.assertIn(
            f"UID:{stable_uid('ics-test', '2026-04-01', 'abstract:Poster', 'registration:Registration')}",
            ics_one,
        )
        self.assertIn(f"UID:{stable_uid('ics-test', '2026-03-28', 'abstract:Abstract')}", ics_one)
        self.assertIn("SUMMARY:ICS Test - Abstract deadline (Poster) / Registration deadline", ics_one)
        self.assertIn("TRIGGER:-P2D", ics_one)
        self.assertEqual(
            [line for line in ics_one.splitlines() if line.startswith("UID:")],
            [line for line in ics_two.splitlines() if line.startswith("UID:")],
        )

    def test_reminders_select_only_matching_offsets_and_payload_is_deterministic(self) -> None:
        path = write_yaml(
            {
                "conferences": [
                    {
                        "id": "reminder-test",
                        "title": "Reminder Test",
                        "url": "https://example.com",
                        "location": "Somewhere",
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-02",
                        "registration_deadlines": [
                            {"label": "Registration", "date": "2026-04-29"},
                            {"label": "Final", "date": "2026-04-30"},
                        ],
                        "abstract_deadlines": [{"label": "Abstract", "date": "2026-04-14"}],
                        "registration_display": "",
                        "abstract_display": "",
                        "comments": "Bring a poster",
                    }
                ]
            }
        )
        conferences = load_conferences(path)
        reminders = find_reminders(conferences, today=__import__("datetime").date(2026, 3, 31))
        self.assertEqual([item["days_until"] for item in reminders], [14, 30])
        payload_one = build_reminder_payload(conferences, __import__("datetime").date(2026, 3, 31), "Europe/Berlin")
        payload_two = build_reminder_payload(conferences, __import__("datetime").date(2026, 3, 31), "Europe/Berlin")
        self.assertEqual(payload_one["title"], "Deadline reminders for 2026-03-31")
        self.assertEqual(payload_one, payload_two)

    def test_repository_data_builds_and_preserves_known_entries(self) -> None:
        conferences = load_conferences(REPO_ROOT / "data" / "conferences.yml")
        markdown = build_markdown(conferences, today=__import__("datetime").date(2026, 3, 30))
        payload = build_reminder_payload(conferences, __import__("datetime").date(2026, 3, 30), "Europe/Berlin")
        self.assertIn("APRIM 2026", markdown)
        self.assertIn("ACAMAR 11", markdown)
        self.assertIn("MODEST26", payload["body"])
        self.assertEqual(json.loads(json.dumps(payload))["label"], "deadline-reminder")

    def test_build_script_writes_nojekyll_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            markdown_output = Path(temp_dir) / "calendar.md"
            site_dir = Path(temp_dir) / "site"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "build_calendar.py"),
                    "--data",
                    str(REPO_ROOT / "data" / "conferences.yml"),
                    "--markdown-output",
                    str(markdown_output),
                    "--site-dir",
                    str(site_dir),
                    "--today",
                    "2026-03-30",
                ],
                check=True,
                cwd=REPO_ROOT,
            )
            self.assertTrue((site_dir / ".nojekyll").exists())


if __name__ == "__main__":
    unittest.main()
