# Conference Calendar

click https://nbody6ppgpu.github.io/conference-calendar/

In this webpage, you can subscribe to all conferences in your calendar application. You will receive notifications for abstract submission deadlines and registration deadlines. Each event includes a default reminder set for “2 days before.”

# How to contribute / how to add new conference?

1. Create a new issue; put the conference link.
2. Leave the text `[new]` or `[ai]` in the issue title, then AI will start working.
3. If AI does not work then just @kaiwu-astro to call the AI...

## For Repository Maintainers

This repository now maintains the conference calendar using a “structured data + auto-generation” approach.

- The single source of truth is `data/conferences.yml`.
- `conference_calendar.md` and the entire `site/` directory are generated outputs. They are ignored by git and should not be included in pull requests.
- Monthly archive placement is deterministic: the scheduled workflow runs `scripts/cleanup_calendar.py` with one fixed `Europe/Berlin` cleanup date and creates a PR only when the source data needs a change.
- New meetings and monthly metadata enrichment are handled by Claude Code (via `anthropics/claude-code-action@v1`), triggered from tagged issues and from the monthly cleanup workflow. The conference-data reviewer prompt still exists for fact-checking a changed PR, but is invoked by hand rather than automatically.
- The monthly workflow uses the `PERSONAL_ACCESS_TOKEN` repository secret to push its branch and open the draft PR. That token must have Contents: Read and write and Pull requests: Read and write permission on this repository.
- Do not edit generated HTML directly. For page template/static text (for example title or subscribe sentence), edit `scripts/calendar_core.py` in `build_index_html` or `build_past_events_html`, then run `python3 scripts/build_calendar.py`.
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

- The ICS file only includes specific `registration deadline` and `abstract deadline` events; it does not contain conference start/end dates.
- Each ICS event comes with a default reminder set for “2 days before the deadline.”
- If both the registration and abstract deadlines for a conference fall on the same day, only one event will be created in the ICS, combining both types of deadlines.
- Deadlines marked as `TBA`, `open`, or `?` (without a specific date) will not generate ICS events or automatic reminders.

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
python3 scripts/build_calendar.py
python3 scripts/cleanup_calendar.py --today 2026-08-04 --dry-run
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
