# Monthly calendar cleanup

This is cleanup mode, not reviewer mode. Read `AGENTS.md` first and follow its
calendar-cleanup instructions.

The Actions workflow computes one fixed cleanup date in `Europe/Berlin` and
passes it to the deterministic command below. Use that same date throughout
the task; do not recalculate today's date in a later step:

```bash
python3 scripts/cleanup_calendar.py --today "$CLEANUP_DATE"
```

The command moves every entry whose `end_date` is before the fixed cleanup
date into the past section and preserves the YAML entry text. Modify only
`data/conferences.yml`. Do not run a second-pass metadata review as part of
this task; the separate `conference-data-reviewer.md` prompt is invoked only
after a real data PR exists.
