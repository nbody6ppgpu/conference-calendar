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
  source supports.
- For an active placeholder (`start_date: ""`, `end_date: ""`), start at its
  `url` and follow a direct link to that year's official meeting site or
  official registration system, even if it uses a different domain. Use only
  the official series entry and the linked official site, not search engines
  or third-party aggregators. Confirm the meeting year matches the year in
  the entry's `id` before editing it. Once confirmed, you may update `url` to
  the meeting site and fill `location`, both `start_date` and `end_date` (only
  when both are known), `registration_deadlines`, and `abstract_deadlines`
  with verified facts. Keep `title` when it already has the correct year;
  never change `id` or `comments`.
- If a fact still isn't available after EXPLORE, leave the field as it is.
  Do not write `TBA` or any placeholder yourself — an unannounced date will
  simply be checked again next month.
- Do not touch `comments`.
- Modify only `data/conferences.yml`. Do not run the build script; the
  workflow verifies the build itself in a later step.
- Commit your change yourself if you modified the file, with a clear commit
  message (e.g. `Enrich monthly calendar metadata`). If you made no changes,
  do not create an empty commit.

Final message: list which entries you enriched and which fields you filled,
or say explicitly that nothing needed enrichment.
