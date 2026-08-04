# Conference data reviewer

Read `AGENTS.md` first and follow its reviewer mode instructions.

You are the second-pass reviewer for conference metadata changes. Your job is to fact-check and repair only the conference entries changed in this branch or pull request.

Scope:
- If a pull request base ref is available, inspect `git diff "$REVIEW_BASE_REF"...HEAD -- data/conferences.yml` and identify the changed conference entries.
- If no pull request base ref is available, inspect `git diff -- data/conferences.yml` and identify the changed conference entries.
- Review only those changed entries. Do not clean or reorganize the full calendar.
- A deterministic cleanup workflow owns date-based archive placement. Do not move entries between the past and active sections while reviewing metadata.
- Modify only `data/conferences.yml`.
- Do not edit generated outputs such as `conference_calendar.md`, `site/`, or `site/meetings/`.

Verification rules:
- Do not trust the current YAML values.
- For each changed entry, open the conference `url` and EXPLORE it according to `AGENTS.md`.
- If key facts are not on the landing page, follow only links reachable from that site, such as dates, important dates, registration, abstract submission, program, venue, or FAQ pages.
- Do not use general search engines.
- Verify `title`, `url`, `location`, `start_date`, `end_date`, `registration_deadlines`, `abstract_deadlines`, `registration_display`, and `abstract_display`.
- If multiple registration or abstract deadlines exist, represent them as structured list items with `label` and `date`.
- If a deadline is only stated as text such as `TBA`, `open`, or `?`, keep it in `registration_display` or `abstract_display` instead of inventing a date.
- Do not change `comments` unless the original task explicitly asks for comments.

Repair behavior:
- If a changed entry contains wrong, shifted, stale, or unsupported facts, fix `data/conferences.yml` directly.
- If the current data is correct, leave it unchanged.
- After any YAML edit, run:
  `python3 scripts/build_calendar.py --markdown-output "$RUNNER_TEMP/conference_calendar.md" --site-dir "$RUNNER_TEMP/site"`
- If `RUNNER_TEMP` is not set, use a temporary directory outside the repository.

Final response:
- Summarize which changed entries were reviewed.
- State whether `data/conferences.yml` was modified.
- Mention the build command result if it was run.
