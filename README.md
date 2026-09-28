# Conference Calendar

click https://nbody6ppgpu.github.io/conference-calendar/

On this webpage, you can subscribe to conference deadlines in your calendar application. The ICS feed covers dated registration, abstract submission, and other labeled deadlines. Each deadline event includes two alarms, 7 days and 1 day before the deadline.

# How to contribute / how to add new conference?

1. Create a new issue; put the conference link.
2. Leave the text `[new]` or `[ai]` in the issue title, then AI will start working.
3. If AI does not work then just @kaiwu-astro to call the AI...

## For Repository Maintainers

This repository now maintains the conference calendar using a “structured data + auto-generation” approach.

- The single source of truth is `data/conferences.yml`.
- `conference_calendar.md` and the entire `site/` directory are generated outputs tracked in git; do not hand-edit or include regenerated copies in data-change pull requests.
- Monthly archive placement is deterministic: the scheduled workflow runs `scripts/cleanup_calendar.py` with one fixed `Europe/Berlin` cleanup date and creates a PR only when the source data needs a change.
- New meetings and monthly metadata enrichment are handled by Claude Code (via `anthropics/claude-code-action@v1`), triggered from tagged issues and from the monthly cleanup workflow. The conference-data reviewer prompt still exists for fact-checking a changed PR, but is invoked by hand rather than automatically.
- The monthly workflow, the new-issue notifier, and the add-conference workflow all authenticate as a dedicated GitHub App (`conference-calendar-bot`) rather than a maintainer's personal token, so that comments and PRs they post are visible to GitHub's own notification system (an account is never notified of its own activity). The `CALENDAR_BOT_APP_ID` and `CALENDAR_BOT_APP_PRIVATE_KEY` repository secrets hold its credentials; the App needs Contents: Read, Issues: Read and write, and Pull requests: Read and write permission on this repository.
- Do not edit generated HTML directly. For page template/static text (for example title or subscribe sentence), edit `scripts/calendar_core.py` in `build_index_html` or `build_past_events_html`, then build into a scratch directory (see below).
- GitHub Pages builds the site from `data/conferences.yml` during deployment.

## What Reminders Can I Receive?

Currently, this repository offers one reminder method:

1. **ICS Calendar Notifications**:  
   As mentioned above.

## If You Just Want to “Receive Reminders”

### Method 1: Subscribe to ICS

1. Open the GitHub Pages site.
2. Copy the link to `conference_calendar.ics`.
3. In your calendar client, choose “Subscribe to calendar via URL” or a similar option.
4. Set a default reminder for events within your calendar client.

**Notes:**

- The ICS feed includes dated registration, abstract, and `other_deadlines` events; it does not contain conference start/end dates.
- Each dated deadline event includes two alarms: 7 days and 1 day before the deadline (`TRIGGER:-P7D` and `TRIGGER:-P1D`).
- Registration and abstract deadlines for the same conference on the same day share one ICS event; each dated `other_deadlines` item gets its own event, even on that date.
- Undated deadlines (including `other_deadlines` items with `date: ""`) do not generate ICS events or automatic reminders. Other deadline items use `type` (`funding`, `proposal`, or `other`), `label`, and `date`; early-bird/early/reduced-rate registration cutoffs use `type: other` and `label: Early-bird registration`, while `registration_deadlines` holds regular/final cutoffs.

## Maintaince notes

### 1. Enable GitHub Actions

This repository relies on two workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/deploy-pages.yml`

You need to:

1. Enable Actions on the repository’s “Actions” page.
2. Ensure the default branch is `main`.
3. Keep the workflow files on the `main` branch executable.

### 2. Enable GitHub Pages

The repository uses the official Pages workflow to publish the contents of the `site/` directory.

It’s recommended to check:

1. `Settings -> Pages`.
2. Set the source to “GitHub Actions.”

Once configured, the `Deploy Pages` workflow will automatically publish the generated static pages.

### 3. Manually Trigger an Initial Deployment

After first enabling the repository, it’s advisable to manually run the following workflow to confirm everything is functioning correctly:

1. `Deploy Pages`

This will allow you to immediately verify:

- Whether the Pages site is accessible.
- Whether `conference_calendar.ics` can be downloaded.

## How to Update Conference Data

Only edit:

- `data/conferences.yml`

Do not commit generated outputs:

- `conference_calendar.md`
- `site/`

After making changes, run the following commands locally to preview and verify:

```bash
python3 -m pip install -r requirements.txt
out="$(mktemp -d)"
python3 scripts/build_calendar.py --markdown-output "$out/conference_calendar.md" --site-dir "$out/site"
python3 scripts/cleanup_calendar.py --today YYYY-MM-DD --dry-run
python3 -m unittest discover -s tests -v
```

Then commit only source changes, normally:

- `data/conferences.yml`

## Directory Structure

- `data/conferences.yml`: The single source of truth.
- `scripts/build_calendar.py`: Generates Markdown, main/archive HTML pages, ICS, and JSON files.
- `scripts/cleanup_calendar.py`: Computes and applies date-based archive placement with a fixed cleanup date.
- `tests/`: Contains validation, generation, ICS, and reminder-related regression tests.
- `site/`: Generated local preview output and the artifact published by GitHub Pages.
