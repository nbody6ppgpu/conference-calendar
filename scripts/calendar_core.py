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


OTHER_DEADLINE_TYPES = frozenset({"funding", "proposal", "other"})
GOATCOUNTER_CODE = "nbody-conference-calendar"
SOURCE_NOTE = (
    "Check our new conference calendar at this link: https://nbody6ppgpu.github.io/conference-calendar/ <-- Bookmark it! "
    "\n"
    "\n"
    "This file is still maintained for backward compatibility, and is automatically generated from `data/conferences.yml` by "
    "`python3 scripts/build_calendar.py`. "
    "\n"
    "\n"
    "Found a new interesting conference? Do not edit this generated markdown, but tell us here: https://github.com/nbody6ppgpu/conference-calendar/issues/new?template=add-a-new-meeting.md "
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
class OtherDeadline:
    type: str
    label: str
    date: date | None


@dataclass(frozen=True)
class Conference:
    id: str
    title: str
    url: str
    location: str
    start_date: date | None
    end_date: date | None
    registration_deadlines: tuple[Deadline, ...]
    abstract_deadlines: tuple[Deadline, ...]
    registration_display: str
    abstract_display: str
    other_deadlines: tuple[OtherDeadline, ...]
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
                "other_deadlines",
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

        start = None if raw["start_date"] == "" else _parse_iso_date(raw["start_date"], f"{conf_id}.start_date")
        end = None if raw["end_date"] == "" else _parse_iso_date(raw["end_date"], f"{conf_id}.end_date")
        if (start is None) != (end is None):
            raise ValidationError(f"{conf_id}.start_date and end_date must both be set or both be empty")
        if start is not None and end < start:
            raise ValidationError(f"{conf_id}.end_date must not be earlier than start_date")

        conference = Conference(
            id=conf_id,
            title=_require_text(raw["title"], f"{conf_id}.title"),
            url=_require_optional_text(raw["url"], f"{conf_id}.url"),
            location=_require_optional_text(raw["location"], f"{conf_id}.location"),
            start_date=start,
            end_date=end,
            registration_deadlines=_parse_deadlines(raw["registration_deadlines"], conf_id, "registration_deadlines"),
            abstract_deadlines=_parse_deadlines(raw["abstract_deadlines"], conf_id, "abstract_deadlines"),
            registration_display=_require_optional_text(
                raw["registration_display"], f"{conf_id}.registration_display"
            ),
            abstract_display=_require_optional_text(raw["abstract_display"], f"{conf_id}.abstract_display"),
            other_deadlines=_parse_other_deadlines(raw["other_deadlines"], conf_id),
            comments=_require_optional_text(raw["comments"], f"{conf_id}.comments"),
        )
        conferences.append(conference)

    return sorted(
        conferences,
        key=lambda item: (
            item.start_date is None,
            item.start_date or date.max,
            item.end_date or date.max,
            item.id if item.start_date is None else item.title.lower(),
            item.id,
        ),
    )


def split_conferences(conferences: Iterable[Conference], today: date) -> tuple[list[Conference], list[Conference]]:
    upcoming = [conference for conference in conferences if conference.end_date is None or conference.end_date >= today]
    past = [conference for conference in conferences if conference.end_date is not None and conference.end_date < today]
    return upcoming, past


def get_today(timezone_name: str, today_override: str | None = None) -> date:
    if today_override:
        return _parse_iso_date(today_override, "today")
    return datetime.now(ZoneInfo(timezone_name)).date()


def _deadline_text(deadline: Deadline) -> str:
    label = f"{deadline.label}: " if deadline.label and deadline.label.lower() not in {"registration", "abstract"} else ""
    return f"{label}{format_single_date(deadline.date)}"


def deadline_display(deadlines: tuple[Deadline, ...], explicit_display: str) -> str:
    if explicit_display:
        return explicit_display
    return "; ".join(_deadline_text(deadline) for deadline in deadlines)


def _html_deadlines(deadlines: tuple[Deadline, ...], explicit_display: str, mark_dates: bool) -> str:
    if explicit_display or not mark_dates:
        return escape(deadline_display(deadlines, explicit_display))
    return "; ".join(
        f'<span data-deadline="{deadline.date.isoformat()}">{escape(_deadline_text(deadline))}</span>'
        for deadline in deadlines
    )


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
    lines.extend(_conference_rows(upcoming, today))
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
    for conference in conferences:
        for deadline_date, items in _group_deadlines_for_ics(conference).items():
            summary = f"{conference.title} - " + " / ".join(item["summary_part"] for item in items)
            description_parts = [f"{item['description_part']}: {deadline_date.isoformat()}" for item in items]
            if conference.comments:
                description_parts.append(f"Notes: {conference.comments}")
            if conference.url:
                description_parts.append(f"Link: {conference.url}")
            uid_parts = [conference.id, deadline_date.isoformat(), *[str(item["uid_part"]) for item in items]]
            dtstamp = stable_dtstamp(
                "deadline",
                conference.id,
                conference.title,
                conference.location,
                conference.url,
                conference.comments,
                deadline_date.isoformat(),
                summary,
                "; ".join(description_parts),
                *[str(item["uid_part"]) for item in items],
            )
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
                        *_deadline_alarms(summary),
                        "END:VEVENT",
                    ]
                )
            )
        for deadline in conference.other_deadlines:
            if deadline.date is None:
                continue
            summary = f"{deadline.label} deadline: {conference.title}"
            description_parts = [f"{deadline.label} deadline: {deadline.date.isoformat()}"]
            if conference.comments:
                description_parts.append(f"Notes: {conference.comments}")
            if conference.url:
                description_parts.append(f"Link: {conference.url}")
            events.append(
                "\n".join(
                    [
                        "BEGIN:VEVENT",
                        f"UID:{stable_uid('other', conference.id, deadline.type, deadline.label, deadline.date.isoformat())}",
                        f"DTSTAMP:{stable_dtstamp('other', conference.id, conference.title, conference.location, conference.url, conference.comments, deadline.type, deadline.label, deadline.date.isoformat())}",
                        f"DTSTART;VALUE=DATE:{deadline.date.strftime('%Y%m%d')}",
                        f"DTEND;VALUE=DATE:{(deadline.date + timedelta(days=1)).strftime('%Y%m%d')}",
                        f"SUMMARY:{_ics_escape(summary)}",
                        f"DESCRIPTION:{_ics_escape('; '.join(description_parts))}",
                        f"URL:{_ics_escape(conference.url)}",
                        *_deadline_alarms(summary),
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


def _deadline_alarms(summary: str) -> list[str]:
    return [
        line
        for offset in (7, 1)
        for line in (
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_escape(summary)}",
            f"TRIGGER:-P{offset}D",
            "END:VALARM",
        )
    ]


def build_meeting_ics(conference: Conference) -> str:
    if conference.start_date is None or conference.end_date is None:
        raise ValueError(f"{conference.id} has no meeting dates")
    dtstamp = stable_dtstamp(
        "meeting",
        conference.id,
        conference.title,
        conference.location,
        conference.url,
        conference.start_date.isoformat(),
        conference.end_date.isoformat(),
    )
    return "\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//conference-calendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{stable_uid('meeting', conference.id)}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{conference.start_date.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(conference.end_date + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_escape(conference.title)}",
            f"LOCATION:{_ics_escape(conference.location)}",
            f"DESCRIPTION:{_ics_escape(conference.url)}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )


def build_index_html(conferences: Iterable[Conference], today: date, repo_url: str) -> str:
    upcoming, past = split_conferences(conferences, today)
    upcoming_rows = _html_rows(upcoming, today=today, include_meeting_ics=True, mark_dates=True)
    webcal_url = _build_webcal_url(repo_url)
    past_count = len(past)
    return _build_site_html(
        title="NBODY Conference Calendar",
        today=today,
        body=f"""
    <section class="hero">
      <h1>NBODY Conference Calendar</h1>
      <p>Interesting conferences for R. Sp. and collaborators. Topics cover stellar/planetary dynamics, star clusters, etc. </p>
      <p>Subscribe to the ICS feed for deadline reminders. The ICS feed follow the same info as calendar below.</p>
      <div class="links">
        <a href="{escape(webcal_url)}" data-goatcounter-click="subscribe-webcal" data-goatcounter-title="Subscribe to deadline reminders">Subscribe to deadline reminders (auto update)</a>
        <a href="./conference_calendar.ics" data-goatcounter-click="download-static-ics" data-goatcounter-title="Download static calendar ICS">Download static .ics (no auto update)</a>
        <a href="{escape(repo_url)}">Repository</a>
      </div>
      <p class="links-note">If the subscription button does not add to your calendar software, you may need to manually add it. For example, <button class="help-trigger" type="button" popovertarget="thunderbird-help">instruction for Thunderbird</button>.</p>
      <div id="thunderbird-help" popover>
        <h2>How to set up conference calendar for Thunderbird</h2>
        <p>Follow the <a href="https://support.mozilla.org/en-US/kb/creating-new-calendars#w_on-the-network-connect-to-your-online-calendars">Thunderbird calendar instructions</a> and leave the account / username / password empty.</p>
        <p>The calendar link with auto update is:</p>
        <code>{escape(webcal_url)}</code>
        <button class="help-close" type="button" popovertarget="thunderbird-help" popovertargetaction="hide">Close</button>
      </div>
      <p class="links-note">Found a new interesting conference? <a class="suggest-link" href="https://github.com/nbody6ppgpu/conference-calendar/issues/new?template=add-a-new-meeting.md">Tell us here</a>.</p>
    </section>
    <section class="panel">
      <h2>Upcoming events</h2>
      {_html_table(upcoming_rows, include_meeting_ics=True)}
    </section>
    <section class="archive-link">
      <a href="./past-events.html">Click here to see past events</a>
      <span>{past_count} archived event{"s" if past_count != 1 else ""}</span>
    </section>""",
        goatcounter_code=GOATCOUNTER_CODE,
        mark_dates=True,
    )


def build_past_events_html(conferences: Iterable[Conference], today: date) -> str:
    _upcoming, past = split_conferences(conferences, today)
    past_rows = _html_rows(past)
    return _build_site_html(
        title="Past Events - NBODY Conference Calendar",
        today=today,
        body=f"""
    <section class="hero compact">
      <h1>Past Events</h1>
      <p>Archived meetings from the NBODY Conference Calendar.</p>
      <div class="links">
        <a href="./">Back to current calendar</a>
      </div>
    </section>
    <section class="panel">
      <h2>Past events</h2>
      {_html_table(past_rows)}
    </section>""",
    )


def _build_site_html(title: str, today: date, body: str, goatcounter_code: str = "", mark_dates: bool = False) -> str:
    goatcounter_script = (
        f'<script data-goatcounter="https://{escape(goatcounter_code, quote=True)}.goatcounter.com/count" '
        'async src="//gc.zgo.at/count.js"></script>'
        if goatcounter_code else ""
    )
    deadline_script = """<script>
    const now = new Date();
    const today = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
    document.querySelectorAll('[data-deadline]').forEach(element => {
      if (element.dataset.deadline < today) element.classList.add('deadline-passed');
    });
  </script>""" if mark_dates else ""
    deadline_style = ".deadline-passed { text-decoration: line-through; color: var(--muted); }" if mark_dates else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
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
    .hero.compact {{
      margin-bottom: 24px;
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
      font-size: 0.88rem;
    }}
    .help-trigger {{
      border: 0;
      padding: 0;
      background: none;
      color: var(--accent);
      font: inherit;
      text-decoration: underline;
      cursor: pointer;
    }}
    #thunderbird-help {{
      width: min(36rem, calc(100vw - 2rem));
      max-height: calc(100vh - 2rem);
      overflow: auto;
      padding: 24px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--panel);
      color: var(--ink);
    }}
    #thunderbird-help::backdrop {{ background: rgba(28, 27, 24, 0.55); }}
    #thunderbird-help code {{ overflow-wrap: anywhere; user-select: all; }}
    .help-close, .suggest-link {{
      display: inline-block;
      border: 0;
      border-radius: 999px;
      padding: 8px 14px;
      background: var(--accent);
      color: white;
      font: inherit;
      text-decoration: none;
      cursor: pointer;
    }}
    .help-close {{ display: block; margin-top: 20px; }}
    .suggest-link {{ margin-left: 4px; }}
    .archive-link {{
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
      background: rgba(255, 250, 242, 0.92);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 22px;
      margin-bottom: 24px;
    }}
    .archive-link a {{
      display: inline-block;
      text-decoration: none;
      color: white;
      background: var(--accent);
      border-radius: 999px;
      padding: 10px 16px;
    }}
    .archive-link span {{
      color: var(--muted);
    }}
    {deadline_style}
    .other-deadlines {{ display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }}
    .other-deadline {{
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 7px;
      color: var(--muted);
      font: 0.75rem/1.4 "Avenir Next Condensed", "Gill Sans", sans-serif;
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
  {goatcounter_script}
</head>
<body>
  <main>
{body}
    <footer>
      <p>Generated for {escape(today.isoformat())} using Europe/Berlin date logic.</p>
    </footer>
  </main>
  {deadline_script}
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


def stable_uid(*parts: str) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()
    return f"{digest}@conference-calendar"


def stable_dtstamp(*parts: str) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()
    seconds = int(digest[:12], 16) % (100 * 366 * 24 * 60 * 60)
    value = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds)
    return value.strftime("%Y%m%dT%H%M%SZ")


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


def _visible_other_deadlines(conference: Conference, today: date) -> tuple[OtherDeadline, ...]:
    return tuple(deadline for deadline in conference.other_deadlines if deadline.date is None or deadline.date >= today)


def _other_deadline_display(deadline: OtherDeadline) -> str:
    return f"{deadline.label}: {format_single_date(deadline.date) if deadline.date else 'TBA'}"


def _conference_rows(conferences: Iterable[Conference], today: date | None = None) -> list[str]:
    rows: list[str] = []
    for conference in conferences:
        rows.append(
            "| "
            + " | ".join(
                [
                    _escape_pipe(format_date_range(conference.start_date, conference.end_date)),
                    _escape_pipe(conference.location),
                    _md_link(conference.title, conference.url)
                    + (
                        "<br>" + "; ".join(
                            _escape_pipe(_other_deadline_display(deadline))
                            for deadline in _visible_other_deadlines(conference, today)
                        )
                        if today is not None and _visible_other_deadlines(conference, today) else ""
                    ),
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


def _html_other_deadline(deadline: OtherDeadline, mark_dates: bool) -> str:
    date_attr = f' data-deadline="{deadline.date.isoformat()}"' if mark_dates and deadline.date else ""
    return f'<span class="other-deadline"{date_attr}>{escape(_other_deadline_display(deadline))}</span>'


def _html_rows(conferences: Iterable[Conference], today: date | None = None, include_meeting_ics: bool = False, mark_dates: bool = False) -> str:
    row_html = []
    for conference in conferences:
        title = (
            f'<a href="{escape(conference.url)}">{escape(conference.title)}</a>'
            if conference.url
            else escape(conference.title)
        )
        tags = (
            '<div class="other-deadlines">'
            + "".join(
                _html_other_deadline(deadline, mark_dates)
                for deadline in _visible_other_deadlines(conference, today)
            )
            + "</div>"
            if today is not None and _visible_other_deadlines(conference, today) else ""
        )
        meeting_ics_cell = (
            f'<td><a href="./meetings/{escape(conference.id)}.ics">Get .ics</a></td>'
            if include_meeting_ics and conference.start_date is not None
            else "<td></td>" if include_meeting_ics else ""
        )
        row_html.append(
            "<tr>"
            f"<td>{escape(format_date_range(conference.start_date, conference.end_date))}</td>"
            f"<td>{escape(conference.location)}</td>"
            f"<td>{title}{tags}</td>"
            f"<td>{_html_deadlines(conference.registration_deadlines, conference.registration_display, mark_dates)}</td>"
            f"<td>{_html_deadlines(conference.abstract_deadlines, conference.abstract_display, mark_dates)}</td>"
            f"<td>{escape(conference.comments)}</td>"
            f"{meeting_ics_cell}"
            "</tr>"
        )
    if not row_html:
        extra_cell = "<td>-</td>" if include_meeting_ics else ""
        row_html.append(f"<tr><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td>{extra_cell}</tr>")
    return "\n          ".join(row_html)


def _html_table(rows: str, include_meeting_ics: bool = False) -> str:
    headers = [
        "Date",
        "Location",
        "Meeting title and link",
        "Registration Deadline",
        "Abstract Deadline",
        "Comments",
    ]
    if include_meeting_ics:
        headers.append("Get meeting schedule .ics")
    header_html = "\n            ".join(f"<th>{header}</th>" for header in headers)
    return f"""<table>
        <thead>
          <tr>
            {header_html}
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>"""


def _conference_payload(conference: Conference) -> dict[str, object]:
    payload = asdict(conference)
    payload["start_date"] = conference.start_date.isoformat() if conference.start_date else None
    payload["end_date"] = conference.end_date.isoformat() if conference.end_date else None
    payload["registration_deadlines"] = [
        {"label": deadline.label, "date": deadline.date.isoformat()} for deadline in conference.registration_deadlines
    ]
    payload["abstract_deadlines"] = [
        {"label": deadline.label, "date": deadline.date.isoformat()} for deadline in conference.abstract_deadlines
    ]
    payload["other_deadlines"] = [
        {"type": deadline.type, "label": deadline.label, "date": deadline.date.isoformat() if deadline.date else None}
        for deadline in conference.other_deadlines
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


def _parse_other_deadlines(value: object, conf_id: str) -> tuple[OtherDeadline, ...]:
    if not isinstance(value, list):
        raise ValidationError(f"{conf_id}.other_deadlines must be a list")
    parsed: list[OtherDeadline] = []
    for idx, raw in enumerate(value, start=1):
        field = f"{conf_id}.other_deadlines[{idx}]"
        if not isinstance(raw, dict):
            raise ValidationError(f"{field} must be a mapping")
        if "type" not in raw or "label" not in raw or "date" not in raw:
            raise ValidationError(f"{field} requires type, label, and date")
        kind = _require_text(raw["type"], f"{field}.type")
        if kind not in OTHER_DEADLINE_TYPES:
            raise ValidationError(f"{field}.type must be one of: funding, proposal, other")
        label = _require_text(raw["label"], f"{field}.label")
        deadline_date = None if raw["date"] == "" else _parse_iso_date(raw["date"], f"{field}.date")
        parsed.append(OtherDeadline(type=kind, label=label, date=deadline_date))
    return tuple(sorted(parsed, key=lambda deadline: (deadline.date is None, deadline.date or date.max, deadline.label.lower(), deadline.type)))


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


def format_date_range(start: date | None, end: date | None) -> str:
    if start is None or end is None:
        return "TBA"
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
