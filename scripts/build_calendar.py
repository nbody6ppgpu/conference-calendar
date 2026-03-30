from __future__ import annotations

import argparse
from pathlib import Path

from calendar_core import build_ics, build_index_html, build_json, build_markdown, get_today, load_conferences


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build markdown, JSON, HTML, and ICS conference calendar outputs.")
    parser.add_argument("--data", default="data/conferences.yml", help="Path to the source YAML file.")
    parser.add_argument("--markdown-output", default="conference_calendar.md", help="Generated markdown output path.")
    parser.add_argument("--site-dir", default="site", help="Directory for generated site assets.")
    parser.add_argument("--repo-url", default="https://github.com/nbody6ppgpu/conference-calendar", help="Repository URL shown on the generated site.")
    parser.add_argument("--timezone", default="Europe/Berlin", help="Timezone used to determine 'today'.")
    parser.add_argument("--today", default=None, help="Override today's date in YYYY-MM-DD format.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conferences = load_conferences(args.data)
    today = get_today(args.timezone, args.today)

    markdown_path = Path(args.markdown_output)
    site_dir = Path(args.site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)

    markdown_path.write_text(build_markdown(conferences, today), encoding="utf-8")
    (site_dir / "conference_calendar.ics").write_text(build_ics(conferences), encoding="utf-8")
    (site_dir / "conference_calendar.json").write_text(build_json(conferences, today), encoding="utf-8")
    (site_dir / "index.html").write_text(
        build_index_html(conferences, today, args.repo_url),
        encoding="utf-8",
    )
    # Disable GitHub Pages' implicit Jekyll pipeline for this prebuilt static site.
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":
    main()
