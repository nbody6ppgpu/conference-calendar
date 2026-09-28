# Monthly calendar cleanup — metadata enrichment

Read `AGENTS.md` first and follow "Mode 2 — Monthly cleanup", the metadata
enrichment part specifically. The archive-placement part of this mode has
already run as this PR's first commit; do not redo it and do not move any
entry between `# Past events` and `# Conference Calendar`.

The cleanup date for this run is given to you in this prompt — use it
exactly, do not recompute or guess today's date, and do not read it from an
environment variable (it will not be set in your tool environment).

Task:
- For every entry after the `# Conference Calendar` marker in
  `data/conferences.yml` whose `start_date`, `end_date`,
  `registration_deadlines`, or `abstract_deadlines` is empty or holds no real
  date, EXPLORE its `url` (as defined in `AGENTS.md`) and fill in what the
  source supports, including announced `other_deadlines` (`type`: `funding`,
  `proposal`, or `other`; descriptive `label`; verified `date` or `""` only
  when the official site explicitly announces the item without a date).
  Treat early-bird, early, and reduced-rate registration cutoffs as
  `other_deadlines` (`type: other`, `label: Early-bird registration`), not as
  regular/final `registration_deadlines`; see `AGENTS.md`.
- Also revisit every active meeting whose `start_date` is at least 90 days
  after the supplied cleanup date, plus every placeholder with no meeting
  dates, to find new `other_deadlines` and fill dates for existing undated
  items. Keep existing items unless the official site clearly contradicts them.
- For an active placeholder (`start_date: ""`, `end_date: ""`), start at its
  `url` and follow a direct link to that year's official meeting site or
  official registration system, even if it uses a different domain. Use only
  the official series entry and the linked official site, not search engines
  or third-party aggregators. Confirm the meeting year matches the year in
  the entry's `id` before editing it. Once confirmed, you may update `url` to
  the meeting site and fill `location`, both `start_date` and `end_date` (only
  when both are known), `registration_deadlines`, `abstract_deadlines`, and
  `other_deadlines` with verified facts. Keep `title` when it already has the
  correct year; never change `id` or `comments`.
- If WebFetch fails or returns an empty/JS-rendered shell, fetch that same
  official URL with Bash `curl -sL` and inspect its raw HTML, embedded JSON,
  and the site's own same-origin JS bundles for dates. On the official Chinese
  Astronomical Society site `astronomy.pmo.cas.cn` alone, use `curl -k` for its
  known self-signed certificate; never use `-k` on other sites. Follow only
  official conference/series links (including directly linked official meeting
  sites for placeholders), never search engines or aggregators. If the fallback
  also fails, record the entry, URL, and error in the final report.
- If a fact still isn't available after EXPLORE, leave the field as it is.
  Only an officially announced `other_deadlines` item may have `date: ""`;
  never guess a date or write `TBA` as one. Recheck undated items next month.
- When you fill `registration_display` / `abstract_display`, keep the site's
  wording and never add a year, month, or day it does not state for that item.
- Do not touch `comments`.
- Modify only `data/conferences.yml`. Do not run the build script; the
  workflow verifies the build itself in a later step.
- Commit your change yourself if you modified the file, with a clear commit
  message (e.g. `Enrich monthly calendar metadata`). If you made no changes,
  do not create an empty commit.

Final message: list each enriched entry and the fields filled (or explicitly
state that nothing changed). Add separate sections listing **every active
entry checked but unreadable** (entry ID, URL, and WebFetch/curl error) and
**every entry checked with no new facts** (entry ID). Write `None` under a
section if it is empty, so the reviewer can distinguish a checked source from
an overlooked one. The workflow copies this message into the PR body.
