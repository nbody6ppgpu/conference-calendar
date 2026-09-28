from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from unittest.mock import patch
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from calendar_core import (  # noqa: E402
    ValidationError,
    build_ics,
    build_index_html,
    build_markdown,
    build_json,
    build_meeting_ics,
    build_past_events_html,
    deadline_display,
    load_conferences,
    stable_uid,
)
from build_meeting_ics import write_meeting_ics_files  # noqa: E402


def write_yaml(payload: dict) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
    with handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
    return Path(handle.name)


def _dtstamp_lines(ics: str) -> list[str]:
    return [line for line in ics.splitlines() if line.startswith("DTSTAMP:")]


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
                        "other_deadlines": [],
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
                        "other_deadlines": [],
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
                        "other_deadlines": [],
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
                        "other_deadlines": [],
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
                        "other_deadlines": [],
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
                        "other_deadlines": [],
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

    def test_site_splits_past_events_onto_archive_page(self) -> None:
        path = write_yaml(
            {
                "conferences": [
                    {
                        "id": "future",
                        "title": "Future Event",
                        "url": "https://example.com/future",
                        "location": "Future City",
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-02",
                        "registration_deadlines": [],
                        "abstract_deadlines": [],
                        "registration_display": "TBA",
                        "abstract_display": "",
                        "other_deadlines": [],
                        "comments": "",
                    },
                    {
                        "id": "past",
                        "title": "Past Event",
                        "url": "https://example.com/past",
                        "location": "Past City",
                        "start_date": "2026-03-01",
                        "end_date": "2026-03-02",
                        "registration_deadlines": [],
                        "abstract_deadlines": [],
                        "registration_display": "",
                        "abstract_display": "",
                        "other_deadlines": [],
                        "comments": "",
                    },
                ]
            }
        )
        conferences = load_conferences(path)
        today = __import__("datetime").date(2026, 3, 30)
        index_html = build_index_html(conferences, today, "https://github.com/nbody6ppgpu/conference-calendar")
        past_html = build_past_events_html(conferences, today)

        self.assertIn("./past-events.html", index_html)
        self.assertIn("Click here to see past events", index_html)
        self.assertIn("Get meeting schedule .ics", index_html)
        self.assertIn('<a href="./meetings/future.ics">Get .ics</a>', index_html)
        self.assertIn("Future Event", index_html)
        self.assertNotIn("Past Event", index_html)
        self.assertIn("./", past_html)
        self.assertIn("Past Event", past_html)
        self.assertNotIn("Future Event", past_html)
        self.assertNotIn("Get meeting schedule .ics", past_html)
        self.assertNotIn("Get .ics", past_html)

    def test_index_click_tracking_and_thunderbird_popover(self) -> None:
        repo_url = "https://github.com/nbody6ppgpu/conference-calendar"
        with patch("calendar_core.GOATCOUNTER_CODE", ""):
            index_html = build_index_html([], date(2026, 3, 30), repo_url)
        with patch("calendar_core.GOATCOUNTER_CODE", "nbody-calendar"):
            tracked_html = build_index_html([], date(2026, 3, 30), repo_url)
            past_html = build_past_events_html([], date(2026, 3, 30))

        self.assertNotIn("gc.zgo.at/count.js", index_html)
        script = '<script data-goatcounter="https://nbody-calendar.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'
        self.assertEqual(tracked_html.count(script), 1)
        self.assertNotIn("gc.zgo.at/count.js", past_html)
        self.assertEqual(tracked_html.count('data-goatcounter-click="'), 2)
        self.assertIn('data-goatcounter-click="subscribe-webcal" data-goatcounter-title="Subscribe to deadline reminders"', tracked_html)
        self.assertIn('data-goatcounter-click="download-static-ics" data-goatcounter-title="Download static calendar ICS"', tracked_html)
        self.assertIn('<button class="help-trigger" type="button" popovertarget="thunderbird-help">instruction for Thunderbird</button>', tracked_html)
        self.assertIn('<div id="thunderbird-help" popover>', tracked_html)
        self.assertIn('<h2>How to set up conference calendar for Thunderbird</h2>', tracked_html)
        self.assertIn('popovertarget="thunderbird-help" popovertargetaction="hide"', tracked_html)
        self.assertIn('<code>webcal://nbody6ppgpu.github.io/conference-calendar/conference_calendar.ics</code>', tracked_html)
        self.assertIn('class="suggest-link" href="https://github.com/nbody6ppgpu/conference-calendar/issues/new?template=add-a-new-meeting.md"', tracked_html)
        HTMLParser(convert_charrefs=True).feed(tracked_html)

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
                        "other_deadlines": [],
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

    def test_ics_merges_same_day_deadlines_and_adds_two_alarms(self) -> None:
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
                        "other_deadlines": [],
                        "comments": "",
                    }
                ]
            }
        )
        conferences = load_conferences(path)
        ics_one = build_ics(conferences)
        ics_two = build_ics(conferences)
        self.assertEqual(ics_one.count("BEGIN:VEVENT"), 2)
        self.assertEqual(ics_one, ics_two)
        self.assertIn(
            f"UID:{stable_uid('ics-test', '2026-04-01', 'abstract:Poster', 'registration:Registration')}",
            ics_one,
        )
        self.assertIn(f"UID:{stable_uid('ics-test', '2026-03-28', 'abstract:Abstract')}", ics_one)
        self.assertIn("SUMMARY:ICS Test - Abstract deadline (Poster) / Registration deadline", ics_one)
        self.assertEqual(ics_one.count("TRIGGER:-P7D"), 2)
        self.assertEqual(ics_one.count("TRIGGER:-P1D"), 2)
        self.assertNotIn("TRIGGER:-P2D", ics_one)

        conference = conferences[0]
        changed_deadline = replace(conference.registration_deadlines[0], date=date(2026, 4, 2))
        changed_cases = [
            replace(conference, title="ICS Test Updated"),
            replace(conference, location="Updated Place"),
            replace(conference, url="https://example.com/updated"),
            replace(conference, registration_deadlines=(changed_deadline,)),
        ]
        for changed in changed_cases:
            with self.subTest(field=changed):
                self.assertNotEqual(_dtstamp_lines(ics_one), _dtstamp_lines(build_ics([changed])))

    def test_meeting_ics_contains_schedule_only(self) -> None:
        path = write_yaml(
            {
                "conferences": [
                    {
                        "id": "meeting-ics-test",
                        "title": "Meeting ICS Test",
                        "url": "https://example.com/meeting",
                        "location": "Test City",
                        "start_date": "2026-07-10",
                        "end_date": "2026-07-12",
                        "registration_deadlines": [{"label": "Registration", "date": "2026-05-01"}],
                        "abstract_deadlines": [{"label": "Abstract", "date": "2026-04-01"}],
                        "registration_display": "",
                        "abstract_display": "",
                        "other_deadlines": [],
                        "comments": "Do not include this note",
                    }
                ]
            }
        )
        conference = load_conferences(path)[0]
        ics = build_meeting_ics(conference)
        self.assertEqual(ics, build_meeting_ics(conference))

        self.assertIn("DTSTART;VALUE=DATE:20260710", ics)
        self.assertIn("DTEND;VALUE=DATE:20260713", ics)
        self.assertIn("SUMMARY:Meeting ICS Test", ics)
        self.assertIn("LOCATION:Test City", ics)
        self.assertIn("DESCRIPTION:https://example.com/meeting", ics)
        self.assertNotIn("VALARM", ics)
        self.assertNotIn("Registration", ics)
        self.assertNotIn("Abstract", ics)
        self.assertNotIn("Do not include this note", ics)

        changed_cases = [
            replace(conference, title="Meeting ICS Test Updated"),
            replace(conference, start_date=date(2026, 7, 11)),
            replace(conference, end_date=date(2026, 7, 13)),
            replace(conference, location="Updated City"),
            replace(conference, url="https://example.com/updated-meeting"),
        ]
        for changed in changed_cases:
            with self.subTest(field=changed):
                self.assertNotEqual(_dtstamp_lines(ics), _dtstamp_lines(build_meeting_ics(changed)))

    def test_placeholder_dates_sort_display_and_keep_deadline_events(self) -> None:
        entries = []
        for conference_id, start, end in (
            ("z-placeholder", "", ""),
            ("future", "2027-06-01", "2027-06-02"),
            ("a-placeholder", "", ""),
            ("past", "2025-06-01", "2025-06-02"),
        ):
            entries.append({
                "id": conference_id,
                "title": conference_id,
                "url": f"https://example.com/{conference_id}",
                "location": "" if not start else "Somewhere",
                "start_date": start,
                "end_date": end,
                "registration_deadlines": [{"label": "Early", "date": "2027-05-01"}] if conference_id == "a-placeholder" else [],
                "abstract_deadlines": [],
                "registration_display": "",
                "abstract_display": "",
                "other_deadlines": [],
                "comments": "",
            })
        conferences = load_conferences(write_yaml({"conferences": entries}))
        self.assertEqual([item.id for item in conferences], ["past", "future", "a-placeholder", "z-placeholder"])
        self.assertIsNone(conferences[-1].start_date)
        today = date(2026, 9, 28)
        markdown = build_markdown(conferences, today)
        self.assertIn("| TBA |  | [a-placeholder]", markdown)
        self.assertLess(markdown.index("future"), markdown.index("a-placeholder"))
        self.assertNotIn("a-placeholder", markdown.split("## Past events", 1)[1])
        html = build_index_html(conferences, today, "https://example.com")
        self.assertIn('<td>TBA</td><td></td><td><a href="https://example.com/a-placeholder">a-placeholder</a>', html)
        self.assertNotIn('meetings/a-placeholder.ics', html)
        self.assertIn('<a href="./meetings/future.ics">Get .ics</a>', html)
        payload = json.loads(build_json(conferences, today))
        self.assertEqual([item["id"] for item in payload["upcoming"]], ["future", "a-placeholder", "z-placeholder"])
        self.assertIsNone(payload["upcoming"][1]["start_date"])
        self.assertIsNone(payload["upcoming"][1]["end_date"])
        self.assertEqual([item["id"] for item in payload["past"]], ["past"])
        ics = build_ics(conferences)
        self.assertIn("SUMMARY:a-placeholder - Registration deadline (Early)", ics)
        self.assertNotIn("SUMMARY:z-placeholder", ics)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 1)
        with tempfile.TemporaryDirectory() as temp_dir:
            meetings_dir = Path(temp_dir) / "meetings"
            meetings_dir.mkdir()
            stale = meetings_dir / "a-placeholder.ics"
            stale.write_text("stale", encoding="utf-8")
            paths = write_meeting_ics_files(conferences, today, temp_dir)
            self.assertEqual([path.name for path in paths], ["future.ics"])
            self.assertFalse(stale.exists())
        with self.assertRaisesRegex(ValueError, "has no meeting dates"):
            build_meeting_ics(conferences[-1])

    def test_placeholder_requires_both_dates_empty(self) -> None:
        for start, end in (("", "2027-05-02"), ("2027-05-01", "")):
            with self.subTest(start=start, end=end):
                path = write_yaml({"conferences": [{
                    "id": "partial", "title": "Partial", "url": "https://example.com",
                    "location": "", "start_date": start, "end_date": end,
                    "registration_deadlines": [], "abstract_deadlines": [],
                    "registration_display": "", "abstract_display": "", "other_deadlines": [], "comments": "",
                }]})
                with self.assertRaisesRegex(ValidationError, "must both be set or both be empty"):
                    load_conferences(path)

    def test_repository_data_builds_and_preserves_known_entries(self) -> None:
        conferences = load_conferences(REPO_ROOT / "data" / "conferences.yml")
        markdown = build_markdown(conferences, today=__import__("datetime").date(2026, 3, 30))
        self.assertIn("MODEST26", markdown)
        self.assertIsInstance(build_json(conferences, date(2026, 3, 30)), str)

    def test_other_deadline_validation_and_sorting(self) -> None:
        entry = {
            "id": "other-test", "title": "Other Test", "url": "https://example.com",
            "location": "", "start_date": "", "end_date": "",
            "registration_deadlines": [], "abstract_deadlines": [],
            "registration_display": "", "abstract_display": "", "comments": "",
            "other_deadlines": [
                {"type": "funding", "label": "Travel grant", "date": ""},
                {"type": "proposal", "label": "Call for sessions", "date": "2027-01-15"},
                {"type": "other", "label": "Workshop fee", "date": "2026-12-01"},
            ],
        }
        self.assertEqual(
            [item.label for item in load_conferences(write_yaml({"conferences": [entry]}))[0].other_deadlines],
            ["Workshop fee", "Call for sessions", "Travel grant"],
        )
        for field, invalid, message in (
            ("type", "unknown", "type must be one of"),
            ("type", "", "type must not be empty"),
            ("label", "", "label must not be empty"),
            ("date", "TBA", "YYYY-MM-DD format"),
        ):
            with self.subTest(field=field, invalid=invalid):
                bad = dict(entry, other_deadlines=[dict(entry["other_deadlines"][0], **{field: invalid})])
                with self.assertRaisesRegex(ValidationError, message):
                    load_conferences(write_yaml({"conferences": [bad]}))
        for field in ("other_deadlines",):
            bad = {key: value for key, value in entry.items() if key != field}
            with self.assertRaisesRegex(ValidationError, "missing required fields: other_deadlines"):
                load_conferences(write_yaml({"conferences": [bad]}))
        for missing in ("type", "label", "date"):
            with self.subTest(missing=missing):
                item = {key: value for key, value in entry["other_deadlines"][0].items() if key != missing}
                with self.assertRaisesRegex(ValidationError, "requires type, label, and date"):
                    load_conferences(write_yaml({"conferences": [dict(entry, other_deadlines=[item])]}))

    def test_other_deadlines_render_and_keep_existing_ics_uids(self) -> None:
        entry = {
            "id": "other-test", "title": "Other Test", "url": "https://example.com",
            "location": "", "start_date": "", "end_date": "",
            "registration_deadlines": [{"label": "Registration", "date": "2027-01-15"}],
            "abstract_deadlines": [{"label": "Abstract", "date": "2027-01-15"}],
            "registration_display": "", "abstract_display": "", "comments": "",
            "other_deadlines": [],
        }
        baseline = load_conferences(write_yaml({"conferences": [entry]}))[0]
        baseline_ics = build_ics([baseline])
        entry["other_deadlines"] = [
            {"type": "funding", "label": "Travel grant", "date": ""},
            {"type": "proposal", "label": "Call for sessions", "date": "2027-01-15"},
            {"type": "other", "label": "Old fee", "date": "2026-01-01"},
        ]
        conference = load_conferences(write_yaml({"conferences": [entry]}))[0]
        today = date(2026, 9, 28)
        html = build_index_html([conference], today, "https://example.com")
        self.assertIn("Travel grant: TBA", html)
        self.assertIn("Call for sessions: Jan. 15 2027", html)
        self.assertNotIn("Old fee", html)
        self.assertLess(html.index("Call for sessions: Jan. 15 2027"), html.index("Travel grant: TBA"))
        self.assertNotIn("Travel grant", build_past_events_html([replace(conference, end_date=date(2026, 1, 2), start_date=date(2026, 1, 1))], today))
        markdown = build_markdown([conference], today)
        self.assertIn("[Other Test](https://example.com)<br>Call for sessions: Jan. 15 2027; Travel grant: TBA", markdown)
        self.assertNotIn("Old fee", markdown)
        payload = json.loads(build_json([conference], today))["upcoming"][0]
        self.assertEqual(payload["other_deadlines"], [
            {"type": "other", "label": "Old fee", "date": "2026-01-01"},
            {"type": "proposal", "label": "Call for sessions", "date": "2027-01-15"},
            {"type": "funding", "label": "Travel grant", "date": None},
        ])
        ics = build_ics([conference])
        self.assertEqual(ics.count("BEGIN:VEVENT"), 3)
        self.assertEqual(ics.count("BEGIN:VALARM"), 6)
        self.assertEqual(ics.count("TRIGGER:-P7D"), 3)
        self.assertEqual(ics.count("TRIGGER:-P1D"), 3)
        old_uid = stable_uid("other-test", "2027-01-15", "abstract:Abstract", "registration:Registration")
        self.assertIn(f"UID:{old_uid}", baseline_ics)
        self.assertIn(f"UID:{old_uid}", ics)
        self.assertIn(f"UID:{stable_uid('other', 'other-test', 'proposal', 'Call for sessions', '2027-01-15')}", ics)
        self.assertIn("SUMMARY:Call for sessions deadline: Other Test", ics)
        self.assertNotIn("Travel grant deadline", ics)
        self.assertEqual(build_ics([conference]), ics)

    def test_build_script_writes_static_site_pages_and_nojekyll_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = write_yaml(
                {
                    "conferences": [
                        {
                            "id": "future-build",
                            "title": "Future Build Event",
                            "url": "https://example.com/future",
                            "location": "Future City",
                            "start_date": "2026-06-01",
                            "end_date": "2026-06-02",
                            "registration_deadlines": [],
                            "abstract_deadlines": [],
                            "registration_display": "",
                            "abstract_display": "",
                            "other_deadlines": [],
                            "comments": "",
                        },
                        {
                            "id": "past-build",
                            "title": "Past Build Event",
                            "url": "https://example.com/past",
                            "location": "Past City",
                            "start_date": "2026-03-01",
                            "end_date": "2026-03-02",
                            "registration_deadlines": [],
                            "abstract_deadlines": [],
                            "registration_display": "",
                            "abstract_display": "",
                            "other_deadlines": [],
                            "comments": "",
                        },
                    ]
                }
            )
            markdown_output = Path(temp_dir) / "calendar.md"
            site_dir = Path(temp_dir) / "site"
            meetings_dir = site_dir / "meetings"
            meetings_dir.mkdir(parents=True)
            (meetings_dir / "stale.ics").write_text("stale", encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "build_calendar.py"),
                    "--data",
                    str(data_path),
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
            self.assertTrue((site_dir / "index.html").exists())
            self.assertTrue((site_dir / "past-events.html").exists())
            self.assertTrue((site_dir / ".nojekyll").exists())
            self.assertTrue((meetings_dir / "future-build.ics").exists())
            self.assertFalse((meetings_dir / "past-build.ics").exists())
            self.assertFalse((meetings_dir / "stale.ics").exists())


if __name__ == "__main__":
    unittest.main()
