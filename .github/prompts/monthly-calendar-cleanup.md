# Monthly calendar cleanup — archive step

This document describes the first commit of the monthly cleanup PR: the
deterministic archive step. It is included in the PR body for human
reference; it is not fed to a model, because this step makes no model calls.

The Actions workflow computes one fixed cleanup date in `Europe/Berlin` and
passes it to the deterministic command below:

```bash
python3 scripts/cleanup_calendar.py --today "$CLEANUP_DATE"
```

The command moves every entry whose `end_date` is before the fixed cleanup
date into the past section and preserves the YAML entry text. It changes only
`data/conferences.yml`, and a `--check` run afterwards fails the job if that
result is edited by hand.

Do not run a second-pass metadata review as part of this step; metadata
enrichment is a separate commit in this same PR, produced by an agent
following `.github/prompts/metadata-enrichment.md`.
