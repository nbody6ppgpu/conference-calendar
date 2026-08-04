#!/usr/bin/env python3
"""Deterministically place conference entries in the calendar archive.

The YAML comments are presentation markers only.  The event dates determine
which side of the archive marker an entry belongs on; this keeps the cleanup
independent of an agent's interpretation of the current file layout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from calendar_core import Conference, ValidationError, get_today, load_conferences


ENTRY_RE = re.compile(r"^  - id:\s*(?P<value>.+?)\s*$")
SECTION_RE = re.compile(r"^  # (?P<section>Past events|Conference Calendar)\s*$")
ACTIVE_SECTION = "Conference Calendar"
PAST_SECTION = "Past events"


@dataclass(frozen=True)
class CalendarEntry:
    id: str
    end_date: date
    lines: tuple[str, ...]
    start_line: int
    current_section: str


@dataclass(frozen=True)
class CleanupPlan:
    cleanup_date: date
    overdue_ids: tuple[str, ...]
    expected_ids: tuple[str, ...]
    changed: bool
    rendered_text: str


@dataclass(frozen=True)
class CalendarLayout:
    original_text: str
    prefix: tuple[str, ...]
    active_marker: str
    entries: tuple[CalendarEntry, ...]


def plan_cleanup(data_path: str | Path, cleanup_date: date) -> CleanupPlan:
    path = Path(data_path)
    layout = _read_layout(path)
    conferences = {conference.id: conference for conference in load_conferences(path)}

    if {entry.id for entry in layout.entries} != set(conferences):
        raise ValidationError("YAML entry blocks and parsed conference IDs do not match")

    overdue_ids = tuple(
        entry.id
        for entry in layout.entries
        if entry.current_section == ACTIVE_SECTION and entry.end_date < cleanup_date
    )
    expected_ids = tuple(
        entry.id
        for entry in layout.entries
        if (entry.current_section == PAST_SECTION) != (entry.end_date < cleanup_date)
    )
    rendered_text = _render(layout, cleanup_date)
    return CleanupPlan(
        cleanup_date=cleanup_date,
        overdue_ids=overdue_ids,
        expected_ids=expected_ids,
        changed=rendered_text != layout.original_text,
        rendered_text=rendered_text,
    )


def apply_cleanup(data_path: str | Path, cleanup_date: date) -> CleanupPlan:
    path = Path(data_path)
    plan = plan_cleanup(path, cleanup_date)
    if plan.changed:
        path.write_text(plan.rendered_text, encoding="utf-8")
    return plan


def verify_cleanup(
    data_path: str | Path,
    cleanup_date: date,
    expected_ids: tuple[str, ...] = (),
    baseline_path: str | Path | None = None,
) -> CleanupPlan:
    plan = plan_cleanup(data_path, cleanup_date)
    if plan.expected_ids:
        details = ", ".join(plan.expected_ids)
        raise ValidationError(f"calendar still has entries in the wrong section: {details}")

    actual_ids = {entry.id for entry in _read_layout(Path(data_path)).entries}
    if baseline_path is not None:
        baseline_ids = {conference.id for conference in load_conferences(baseline_path)}
        if actual_ids != baseline_ids:
            missing_ids = sorted(baseline_ids - actual_ids)
            added_ids = sorted(actual_ids - baseline_ids)
            details = []
            if missing_ids:
                details.append(f"missing: {', '.join(missing_ids)}")
            if added_ids:
                details.append(f"added: {', '.join(added_ids)}")
            raise ValidationError("conference ID set changed: " + "; ".join(details))
    missing_ids = [conference_id for conference_id in expected_ids if conference_id not in actual_ids]
    if missing_ids:
        raise ValidationError(f"expected cleanup entries are missing: {', '.join(missing_ids)}")
    return plan


def _read_layout(path: Path) -> CalendarLayout:
    original_text = path.read_text(encoding="utf-8")
    lines = tuple(original_text.splitlines(keepends=True))
    entry_starts = [index for index, line in enumerate(lines) if ENTRY_RE.match(_without_newline(line))]
    if not entry_starts:
        raise ValidationError("data/conferences.yml does not contain conference entries")

    marker_positions: dict[str, list[int]] = {PAST_SECTION: [], ACTIVE_SECTION: []}
    for index, line in enumerate(lines):
        match = SECTION_RE.match(_without_newline(line))
        if match:
            marker_positions[match.group("section")].append(index)

    for section, positions in marker_positions.items():
        if len(positions) != 1:
            raise ValidationError(f"data/conferences.yml must contain exactly one '{section}' marker")

    past_marker_position = marker_positions[PAST_SECTION][0]
    active_marker_position = marker_positions[ACTIVE_SECTION][0]
    if past_marker_position >= entry_starts[0]:
        raise ValidationError("the 'Past events' marker must precede the first conference entry")
    if active_marker_position <= past_marker_position:
        raise ValidationError("the 'Conference Calendar' marker must follow 'Past events'")

    conferences = _load_conference_map(path)
    entries: list[CalendarEntry] = []
    for index, start in enumerate(entry_starts):
        end = entry_starts[index + 1] if index + 1 < len(entry_starts) else len(lines)
        block = tuple(line for line in lines[start:end] if not SECTION_RE.match(_without_newline(line)))
        match = ENTRY_RE.match(_without_newline(lines[start]))
        if match is None:  # pragma: no cover - entry_starts was built with the same expression
            raise ValidationError(f"unable to parse conference entry at line {start + 1}")
        conference_id = _parse_yaml_string(match.group("value"), f"conference id at line {start + 1}")
        if conference_id not in conferences:
            raise ValidationError(f"conference entry '{conference_id}' is not valid YAML data")
        if any(entry.id == conference_id for entry in entries):
            raise ValidationError(f"duplicate conference entry block: {conference_id}")
        current_section = PAST_SECTION if start < active_marker_position else ACTIVE_SECTION
        entries.append(
            CalendarEntry(
                id=conference_id,
                end_date=conferences[conference_id].end_date,
                lines=block,
                start_line=start + 1,
                current_section=current_section,
            )
        )

    prefix = tuple(
        line
        for index, line in enumerate(lines[: entry_starts[0]])
        if index != active_marker_position
    )
    active_marker = lines[active_marker_position]
    if not active_marker.endswith(("\n", "\r")):
        active_marker += "\n"
    return CalendarLayout(
        original_text=original_text,
        prefix=prefix,
        active_marker=active_marker,
        entries=tuple(entries),
    )


def _load_conference_map(path: Path) -> dict[str, Conference]:
    conferences = load_conferences(path)
    return {conference.id: conference for conference in conferences}


def _render(layout: CalendarLayout, cleanup_date: date) -> str:
    past_entries = [entry for entry in layout.entries if entry.end_date < cleanup_date]
    active_entries = [entry for entry in layout.entries if entry.end_date >= cleanup_date]
    lines = list(layout.prefix)
    for entry in past_entries:
        lines.extend(entry.lines)
    lines.append(layout.active_marker)
    for entry in active_entries:
        lines.extend(entry.lines)
    return "".join(lines)


def _parse_yaml_string(value: str, field_name: str) -> str:
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError as exc:
        raise ValidationError(f"{field_name} is not valid YAML") from exc
    if not isinstance(parsed, str) or not parsed:
        raise ValidationError(f"{field_name} must be a non-empty string")
    return parsed


def _without_newline(line: str) -> str:
    return line.rstrip("\r\n")


def _report_payload(plan: CleanupPlan, *, applied: bool, verified: bool = False) -> dict[str, object]:
    return {
        "cleanup_date": plan.cleanup_date.isoformat(),
        "overdue_ids": list(plan.overdue_ids),
        "expected_ids": list(plan.expected_ids),
        "expected_count": len(plan.expected_ids),
        "changed": plan.changed,
        "applied": applied,
        "verified": verified,
    }


def _write_report(report_path: str | Path | None, payload: dict[str, object]) -> None:
    if report_path is None:
        return
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive outdated conference entries deterministically.")
    parser.add_argument("--data", default="data/conferences.yml", help="Path to the source YAML file.")
    parser.add_argument("--timezone", default="Europe/Berlin", help="Timezone used to determine the cleanup date.")
    parser.add_argument("--today", default=None, help="Cleanup date override in YYYY-MM-DD format.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Report the plan without modifying the YAML file.")
    mode.add_argument("--check", action="store_true", help="Fail unless the YAML is in the canonical date-based layout.")
    parser.add_argument(
        "--expected-id",
        action="append",
        default=[],
        help="In --check mode, also require this ID to remain present (repeatable).",
    )
    parser.add_argument(
        "--baseline",
        help="In --check mode, compare the current conference ID set with this source YAML file.",
    )
    parser.add_argument("--report", help="Write the JSON plan/result to this path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        cleanup_date = get_today(args.timezone, args.today)
        if args.check:
            plan = verify_cleanup(Path(args.data), cleanup_date, tuple(args.expected_id), args.baseline)
            payload = _report_payload(plan, applied=False, verified=True)
        else:
            plan = apply_cleanup(Path(args.data), cleanup_date) if not args.dry_run else plan_cleanup(args.data, cleanup_date)
            payload = _report_payload(plan, applied=not args.dry_run)
    except (OSError, ValidationError) as exc:
        print(f"cleanup_calendar.py: error: {exc}", file=sys.stderr)
        return 1

    _write_report(args.report, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
