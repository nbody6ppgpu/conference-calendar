from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import yaml


REMINDER_OFFSETS = (30, 14, 7, 3, 1)
SOURCE_NOTE = (
    "This file is generated from `data/conferences.yml` by "
    "`python3 scripts/build_calendar.py`."
)
TRAVEL_MONEY_ROWS = [
    (
        "German Astro. Society",
        "https://www.astronomische-gesellschaft.de/de/aktivitaeten/foerderung",
        "Always open",
        "Affiliated to a German inst.; apply 6+ weeks before meeting",
        "amount given is usually not big (< 1000 eur)",
    )
]
MONTH_NAMES = {
    1: "Jan.",
    2: "Feb.",
    3: "Mar.",
    4: "Apr.",
    5: "May",
    6: "June",
    7: "July",
    8: "Aug.",
    9: "Sept.",
    10: "Oct.",
    11: "Nov.",
    12: "Dec.",
}


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Deadline:
    label: str
    date: date


@dataclass(frozen=True)
class Conference:
    id: str
    title: str
    url: str
    location: str
    start_date: date
    end_date: date
    registration_deadlines: tuple[Deadline, ...]
    abstract_deadlines: tuple[Deadline, ...]
    registration_display: str
    abstract_display: str
    comments: str


def load_conferences(path: str | Path) -> list[Conference]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw_conferences = payload.get("conferences")
    if not isinstance(raw_conferences, list):
        raise ValidationError("data/conferences.yml must contain a top-level 'conferences' list")

    conferences: list[Conference] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_conferences, start=1):
        if not isinstance(raw, dict):
            raise ValidationError(f"conference #{index} must be a mapping")
        missing = [
            field
            for field in (
                "id",
                "title",
                "url",
                "location",
                "start_date",
                "end_date",
                "registration_deadlines",
                "abstract_deadlines",
                "registration_display",
                "abstract_display",
                "comments",
            )
            if field not in raw
        ]
        if missing:
            raise ValidationError(f"conference #{index} is missing required fields: {', '.join(missing)}")

        conf_id = _require_text(raw["id"], f"conference #{index} id")
        if conf_id in seen_ids:
            raise ValidationError(f"duplicate conference id: {conf_id}")
        seen_ids.add(conf_id)

        start = _parse_iso_date(raw["start_date"], f"{conf_id}.start_date")
        end = _parse_iso_date(raw["end_date"], f"{conf_id}.end_date")
        if end < start:
            raise ValidationError(f"{conf_id}.end_date must not be earlier than start_date")

        conference = Conference(
            id=conf_id,
            title=_require_text(raw["title"], f"{conf_id}.title"),
            url=_require_optional_text(raw["url"], f"{conf_id}.url"),
            location=_require_text(raw["location"], f"{conf_id}.location"),
            start_date=start,
            end_date=end,
            registration_deadlines=_parse_deadlines(raw["registration_deadlines"], conf_id, "registration_deadlines"),
            abstract_deadlines=_parse_deadlines(raw["abstract_deadlines"], conf_id, "abstract_deadlines"),
            registration_display=_require_optional_text(
                raw["registration_display"], f"{conf_id}.registration_display"
            ),
            abstract_display=_require_optional_text(raw["abstract_display"], f"{conf_id}.abstract_display"),
            comments=_require_optional_text(raw["comments"], f"{conf_id}.comments"),
        )
        conferences.append(conference)

    return sorted(conferences, key=lambda item: (item.start_date, item.end_date, item.title.lower(), item.id))


def split_conferences(conferences: Iterable[Conference], today: date) -> tuple[list[Conference], list[Conference]]:
    upcoming = [conference for conference in conferences if conference.end_date >= today]
    past = [conference for conference in conferences if conference.end_date < today]
    return upcoming, past


def get_today(timezone_name: str, today_override: str | None = None) -> date:
    if today_override:
        return _parse_iso_date(today_override, "today")
    return datetime.now(ZoneInfo(timezone_name)).date()


def deadline_display(deadlines: tuple[Deadline, ...], explicit_display: str) -> str:
    if explicit_display:
        return explicit_display
    parts = []
    for deadline in deadlines:
        label = f"{deadline.label}: " if deadline.label and deadline.label.lower() not in {"registration", "abstract"} else ""
        parts.append(f"{label}{format_single_date(deadline.date)}")
    return "; ".join(parts)


def build_markdown(conferences: Iterable[Conference], today: date) -> str:
    upcoming, past = split_conferences(conferences, today)
    lines = [
        "# Conference Calendar",
        "",
        SOURCE_NOTE,
        "",
        "| Possible Travel Money | Time | Restriction | Note |",
        "|-|-|-|-|",
    ]
    for title, url, when, restriction, note in TRAVEL_MONEY_ROWS:
        lines.append(
            f"| {_md_link(title, url)} | {_escape_pipe(when)} | {_escape_pipe(restriction)} | {_escape_pipe(note)} |"
        )
    lines.extend(
        [
            "",
            "| Date | Location | Meeting title and link | Registration Deadline | Abstract Deadline | Comments |",
            "|-|-|-|-|-|-|",
        ]
    )
    lines.extend(_conference_rows(upcoming))
    lines.extend(["", "## Past events", "", "| Date | Location | Meeting title and link | Registration Deadline | Abstract Deadline | Comments |", "|-|-|-|-|-|-|"])
    lines.extend(_conference_rows(past))
    lines.extend(["", "*Note: after edit please click* `Preview` *on the top left to see whether the table shows properly.*", ""])
    return "\n".join(lines)


def build_json(conferences: Iterable[Conference], today: date) -> str:
    upcoming, past = split_conferences(conferences, today)
    payload = {
        "generated_on": today.isoformat(),
        "upcoming": [_conference_payload(conference) for conference in upcoming],
        "past": [_conference_payload(conference) for conference in past],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def build_ics(conferences: Iterable[Conference]) -> str:
    events: list[str] = []
    dtstamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for conference in conferences:
        for deadline_date, items in _group_deadlines_for_ics(conference).items():
            summary = f"{conference.title} - " + " / ".join(item["summary_part"] for item in items)
            description_parts = [f"{item['description_part']}: {deadline_date.isoformat()}" for item in items]
            if conference.comments:
                description_parts.append(f"Notes: {conference.comments}")
            if conference.url:
                description_parts.append(f"Link: {conference.url}")
            uid_parts = [conference.id, deadline_date.isoformat(), *[str(item["uid_part"]) for item in items]]
            events.append(
                "\n".join(
                    [
                        "BEGIN:VEVENT",
                        f"UID:{stable_uid(*uid_parts)}",
                        f"DTSTAMP:{dtstamp}",
                        f"DTSTART;VALUE=DATE:{deadline_date.strftime('%Y%m%d')}",
                        f"DTEND;VALUE=DATE:{(deadline_date + timedelta(days=1)).strftime('%Y%m%d')}",
                        f"SUMMARY:{_ics_escape(summary)}",
                        f"DESCRIPTION:{_ics_escape('; '.join(description_parts))}",
                        f"URL:{_ics_escape(conference.url)}",
                        "BEGIN:VALARM",
                        "ACTION:DISPLAY",
                        f"DESCRIPTION:{_ics_escape(summary)}",
                        "TRIGGER:-P2D",
                        "END:VALARM",
                        "END:VEVENT",
                    ]
                )
            )
    return "\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//conference-calendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            *events,
            "END:VCALENDAR",
            "",
        ]
    )


def build_index_html(conferences: Iterable[Conference], today: date, repo_url: str) -> str:
    upcoming, past = split_conferences(conferences, today)
    upcoming_rows = _html_rows(upcoming)
    past_rows = _html_rows(past)
    webcal_url = _build_webcal_url(repo_url)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Conference Calendar</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --panel: #fffaf2;
      --ink: #1c1b18;
      --accent: #9f3a22;
      --line: #d6c7b3;
      --muted: #675f54;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(159, 58, 34, 0.14), transparent 32%),
        linear-gradient(180deg, #f9f4ea 0%, var(--bg) 100%);
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 48px 20px 72px;
    }}
    h1, h2 {{
      font-family: "Avenir Next Condensed", "Gill Sans", sans-serif;
      letter-spacing: 0.03em;
      margin: 0 0 12px;
    }}
    p, li {{
      color: var(--muted);
      line-height: 1.5;
    }}
    .hero {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 28px;
      box-shadow: 0 18px 40px rgba(28, 27, 24, 0.08);
      margin-bottom: 28px;
    }}
    .links {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 16px;
    }}
    .links a {{
      text-decoration: none;
      color: white;
      background: var(--accent);
      border-radius: 999px;
      padding: 10px 16px;
    }}
    .links-note {{
      margin-top: 14px;
    }}
    .panel {{
      background: rgba(255, 250, 242, 0.92);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 22px;
      margin-bottom: 24px;
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 900px;
    }}
    th, td {{
      text-align: left;
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      font-family: "Avenir Next Condensed", "Gill Sans", sans-serif;
      font-size: 0.95rem;
      color: var(--accent);
    }}
    a {{ color: var(--accent); }}
    footer {{ margin-top: 24px; }}
    @media (max-width: 720px) {{
      main {{ padding: 28px 14px 48px; }}
      .hero, .panel {{ padding: 18px; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <p>Generated from structured YAML and rebuilt automatically.</p>
      <h1>Conference Calendar</h1>
      <p>Subscribe to the ICS feed for deadline reminders only, or browse the latest upcoming and past events below. Reminder issues are computed from concrete deadline dates only.</p>
      <div class="links">
        <a href="{escape(webcal_url)}">Subscribe this calendar (with auto update)</a>
        <a href="./conference_calendar.ics">Download static .ics (no auto update)</a>
        <a href="{escape(repo_url)}">Repository</a>
      </div>
      <p class="links-note">If the subscription buttom does not add to your calendar software, you may need to manually add it, for example for thunderbird (<a href="https://support.mozilla.org/en-US/kb/creating-new-calendars#w_on-the-network-connect-to-your-online-calendars">https://support.mozilla.org/en-US/kb/creating-new-calendars#w_on-the-network-connect-to-your-online-calendars</a>), and leave the account / username / password empty. Calendar link with update is: <a href="{escape(webcal_url)}">{escape(webcal_url)}</a></p>
    </section>
    <section class="panel">
      <h2>Upcoming events</h2>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Location</th>
            <th>Meeting title and link</th>
            <th>Registration Deadline</th>
            <th>Abstract Deadline</th>
            <th>Comments</th>
          </tr>
        </thead>
        <tbody>
          {upcoming_rows}
        </tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Past events</h2>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Location</th>
            <th>Meeting title and link</th>
            <th>Registration Deadline</th>
            <th>Abstract Deadline</th>
            <th>Comments</th>
          </tr>
        </thead>
        <tbody>
          {past_rows}
        </tbody>
      </table>
    </section>
    <footer>
      <p>Generated for {escape(today.isoformat())} using Europe/Berlin date logic.</p>
    </footer>
  </main>
</body>
</html>
"""


def _build_webcal_url(repo_url: str) -> str:
    normalized = repo_url.rstrip("/")
    if normalized.startswith("https://github.com/"):
        path = normalized.removeprefix("https://github.com/")
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            return f"webcal://{owner}.github.io/{repo}/conference_calendar.ics"
    parsed = urlparse(normalized)
    path = parsed.path.rstrip("/")
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"webcal://{parsed.netloc}{path}/conference_calendar.ics"
    return "webcal://conference_calendar.ics"


def build_reminder_payload(conferences: Iterable[Conference], today: date, timezone_name: str) -> dict[str, object]:
    reminders = find_reminders(conferences, today)
    title = f"Deadline reminders for {today.isoformat()}"
    return {
        "date": today.isoformat(),
        "title": title,
        "label": "deadline-reminder",
        "has_reminders": bool(reminders),
        "body": render_reminder_issue(reminders, today, timezone_name),
    }


def find_reminders(conferences: Iterable[Conference], today: date) -> list[dict[str, object]]:
    reminders: list[dict[str, object]] = []
    for conference in conferences:
        for deadline_type, deadlines in (
            ("Registration", conference.registration_deadlines),
            ("Abstract", conference.abstract_deadlines),
        ):
            for deadline in deadlines:
                delta_days = (deadline.date - today).days
                if delta_days in REMINDER_OFFSETS:
                    reminders.append(
                        {
                            "conference_id": conference.id,
                            "conference_title": conference.title,
                            "conference_url": conference.url,
                            "deadline_type": deadline_type,
                            "deadline_label": deadline.label,
                            "deadline_date": deadline.date.isoformat(),
                            "days_until": delta_days,
                            "comments": conference.comments,
                        }
                    )
    reminders.sort(
        key=lambda item: (
            item["days_until"],
            item["deadline_date"],
            str(item["conference_title"]).lower(),
            str(item["deadline_type"]).lower(),
        )
    )
    return reminders


def render_reminder_issue(reminders: list[dict[str, object]], today: date, timezone_name: str) -> str:
    lines = [
        f"# Deadline reminders for {today.isoformat()}",
        "",
        f"Computed using `{timezone_name}` dates.",
        "",
    ]
    if not reminders:
        lines.append("No concrete registration or abstract deadlines hit the 30/14/7/3/1-day reminder windows today.")
        lines.append("")
        return "\n".join(lines)

    current_conference = None
    for reminder in reminders:
        conference_title = str(reminder["conference_title"])
        if conference_title != current_conference:
            if current_conference is not None:
                lines.append("")
            url = str(reminder["conference_url"])
            heading = f"## [{conference_title}]({url})" if url else f"## {conference_title}"
            lines.append(heading)
            current_conference = conference_title
        label = str(reminder["deadline_label"])
        label_suffix = f" ({label})" if label and label.lower() not in {"registration", "abstract"} else ""
        lines.append(
            f"- {reminder['deadline_type']} deadline{label_suffix}: {reminder['deadline_date']} "
            f"({reminder['days_until']} days left)"
        )
        comments = str(reminder["comments"])
        if comments:
            lines.append(f"- Notes: {comments}")
    lines.append("")
    return "\n".join(lines)


def stable_uid(*parts: str) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()
    return f"{digest}@conference-calendar"


def _group_deadlines_for_ics(conference: Conference) -> dict[date, list[dict[str, str]]]:
    grouped: dict[date, list[dict[str, str]]] = {}
    for kind, deadlines in (("registration", conference.registration_deadlines), ("abstract", conference.abstract_deadlines)):
        kind_title = kind.title()
        for deadline in deadlines:
            label = deadline.label if deadline.label else kind_title
            label_suffix = f" ({label})" if label.lower() not in {"registration", "abstract"} else ""
            grouped.setdefault(deadline.date, []).append(
                {
                    "uid_part": f"{kind}:{label}",
                    "summary_part": f"{kind_title} deadline{label_suffix}",
                    "description_part": f"{kind_title} deadline{label_suffix}",
                }
            )
    for items in grouped.values():
        items.sort(key=lambda item: str(item["uid_part"]).lower())
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _conference_rows(conferences: Iterable[Conference]) -> list[str]:
    rows: list[str] = []
    for conference in conferences:
        rows.append(
            "| "
            + " | ".join(
                [
                    _escape_pipe(format_date_range(conference.start_date, conference.end_date)),
                    _escape_pipe(conference.location),
                    _md_link(conference.title, conference.url),
                    _escape_pipe(deadline_display(conference.registration_deadlines, conference.registration_display)),
                    _escape_pipe(deadline_display(conference.abstract_deadlines, conference.abstract_display)),
                    _escape_pipe(conference.comments),
                ]
            )
            + " |"
        )
    if not rows:
        rows.append("| - | - | - | - | - | - |")
    return rows


def _html_rows(conferences: Iterable[Conference]) -> str:
    row_html = []
    for conference in conferences:
        title = (
            f'<a href="{escape(conference.url)}">{escape(conference.title)}</a>'
            if conference.url
            else escape(conference.title)
        )
        row_html.append(
            "<tr>"
            f"<td>{escape(format_date_range(conference.start_date, conference.end_date))}</td>"
            f"<td>{escape(conference.location)}</td>"
            f"<td>{title}</td>"
            f"<td>{escape(deadline_display(conference.registration_deadlines, conference.registration_display))}</td>"
            f"<td>{escape(deadline_display(conference.abstract_deadlines, conference.abstract_display))}</td>"
            f"<td>{escape(conference.comments)}</td>"
            "</tr>"
        )
    if not row_html:
        row_html.append("<tr><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>")
    return "\n          ".join(row_html)


def _conference_payload(conference: Conference) -> dict[str, object]:
    payload = asdict(conference)
    payload["start_date"] = conference.start_date.isoformat()
    payload["end_date"] = conference.end_date.isoformat()
    payload["registration_deadlines"] = [
        {"label": deadline.label, "date": deadline.date.isoformat()} for deadline in conference.registration_deadlines
    ]
    payload["abstract_deadlines"] = [
        {"label": deadline.label, "date": deadline.date.isoformat()} for deadline in conference.abstract_deadlines
    ]
    payload["registration_display"] = deadline_display(conference.registration_deadlines, conference.registration_display)
    payload["abstract_display"] = deadline_display(conference.abstract_deadlines, conference.abstract_display)
    return payload


def _parse_deadlines(value: object, conf_id: str, field_name: str) -> tuple[Deadline, ...]:
    if not isinstance(value, list):
        raise ValidationError(f"{conf_id}.{field_name} must be a list")
    parsed: list[Deadline] = []
    for idx, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            raise ValidationError(f"{conf_id}.{field_name}[{idx}] must be a mapping")
        label = _require_optional_text(raw.get("label", ""), f"{conf_id}.{field_name}[{idx}].label")
        if "date" not in raw:
            raise ValidationError(f"{conf_id}.{field_name}[{idx}] is missing required field: date")
        parsed.append(Deadline(label=label, date=_parse_iso_date(raw["date"], f"{conf_id}.{field_name}[{idx}].date")))
    return tuple(sorted(parsed, key=lambda deadline: (deadline.date, deadline.label.lower())))


def _parse_iso_date(value: object, field_name: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be in YYYY-MM-DD format") from exc


def _require_text(value: object, field_name: str) -> str:
    text = _require_optional_text(value, field_name)
    if not text:
        raise ValidationError(f"{field_name} must not be empty")
    return text


def _require_optional_text(value: object, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    return value.strip()


def format_single_date(value: date) -> str:
    return f"{MONTH_NAMES[value.month]} {value.day} {value.year}"


def format_date_range(start: date, end: date) -> str:
    if start == end:
        return format_single_date(start)
    if start.year == end.year and start.month == end.month:
        return f"{MONTH_NAMES[start.month]} {start.day}-{end.day} {start.year}"
    if start.year == end.year:
        return f"{MONTH_NAMES[start.month]} {start.day} - {MONTH_NAMES[end.month]} {end.day} {start.year}"
    return f"{MONTH_NAMES[start.month]} {start.day} {start.year} - {MONTH_NAMES[end.month]} {end.day} {end.year}"


def _md_link(text: str, url: str) -> str:
    safe_text = _escape_pipe(text)
    if url:
        return f"[{safe_text}]({url})"
    return safe_text


def _escape_pipe(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", "<br>")


def _ics_escape(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")
