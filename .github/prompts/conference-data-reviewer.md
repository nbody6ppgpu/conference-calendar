# Conference data reviewer

Read `AGENTS.md` first and follow its reviewer mode instructions.

You are the second-pass reviewer for conference metadata changes. Your job is
to fact-check and repair only the conference entries changed in this branch
or pull request.

Scope:
- Determine the changed entries from the diff. Use
  `git diff "origin/$GITHUB_BASE_REF"...HEAD -- data/conferences.yml` when
  `GITHUB_BASE_REF` is set (pull-request runs); otherwise
  `git diff -- data/conferences.yml` against the working tree.
- Review only those changed entries. Do not clean or reorganize the full
  calendar.
- A deterministic cleanup workflow owns date-based archive placement. Do not
  move entries between the past and active sections while reviewing
  metadata.
- Modify only `data/conferences.yml`.
- Do not edit generated outputs such as `conference_calendar.md`, `site/`,
  or `site/meetings/`.

Verification rules:
- Do not trust the current YAML values.
- For each changed entry, EXPLORE its `url` as defined in `AGENTS.md`.
- Verify `title`, `url`, `location`, `start_date`, `end_date`,
  `registration_deadlines`, `abstract_deadlines`, `registration_display`,
  and `abstract_display`.
- Never invent a date — see the shared rule in `AGENTS.md`.

Repair behavior:
- If a changed entry contains wrong, shifted, stale, or unsupported facts,
  fix `data/conferences.yml` directly.
- If the current data is correct, leave it unchanged.
- After any YAML edit, verify the build using the shared command in
  `AGENTS.md` (a scratch output directory, never the bare
  `build_calendar.py` invocation).

Final response:
- Summarize which changed entries were reviewed.
- State whether `data/conferences.yml` was modified.
- Mention the build verification result if it was run.
