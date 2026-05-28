from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Iterable

from calendar_core import Conference, build_meeting_ics, get_today, load_conferences, split_conferences


def write_meeting_ics_files(conferences: Iterable[Conference], today: date, site_dir: str | Path) -> list[Path]:
    upcoming, _past = split_conferences(conferences, today)
    meetings_dir = Path(site_dir) / "meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)

    expected_paths = {meetings_dir / f"{conference.id}.ics" for conference in upcoming}
    for conference in upcoming:
        (meetings_dir / f"{conference.id}.ics").write_text(build_meeting_ics(conference), encoding="utf-8")

    for stale_path in meetings_dir.glob("*.ics"):
        if stale_path not in expected_paths:
            stale_path.unlink()

    return sorted(expected_paths)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build per-meeting ICS files for upcoming conferences.")
    parser.add_argument("--data", default="data/conferences.yml", help="Path to the source YAML file.")
    parser.add_argument("--site-dir", default="site", help="Directory for generated site assets.")
    parser.add_argument("--timezone", default="Europe/Berlin", help="Timezone used to determine 'today'.")
    parser.add_argument("--today", default=None, help="Override today's date in YYYY-MM-DD format.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conferences = load_conferences(args.data)
    today = get_today(args.timezone, args.today)
    write_meeting_ics_files(conferences, today, args.site_dir)


if __name__ == "__main__":
    main()
