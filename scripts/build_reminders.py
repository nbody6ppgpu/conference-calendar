from __future__ import annotations

import argparse
import json
from pathlib import Path

from calendar_core import build_reminder_payload, get_today, load_conferences


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a daily GitHub issue payload for conference deadline reminders.")
    parser.add_argument("--data", default="data/conferences.yml", help="Path to the source YAML file.")
    parser.add_argument("--timezone", default="Europe/Berlin", help="Timezone used to determine 'today'.")
    parser.add_argument("--today", default=None, help="Override today's date in YYYY-MM-DD format.")
    parser.add_argument("--json-output", default=None, help="Optional JSON file path. Defaults to stdout.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conferences = load_conferences(args.data)
    today = get_today(args.timezone, args.today)
    payload = build_reminder_payload(conferences, today, args.timezone)
    output = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.json_output:
        Path(args.json_output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
