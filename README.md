# Conference Calendar

This repository now maintains the conference calendar using a “structured data + auto-generation” approach.

- The single source of truth is `data/conferences.yml`.

- `conference_calendar.md`, `site/index.html`, `site/conference_calendar.ics`, and `site/conference_calendar.json` are all generated outputs.

- A GitHub Issue is created daily to remind users of conferences with deadlines remaining in `30 / 14 / 7 / 3 / 1` days.

## What Reminders Can I Receive?

Currently, this repository offers two reminder methods:

1. **ICS Calendar Notifications**:  
   After subscribing to `site/conference_calendar.ics` in your calendar application, you will receive notifications for specific deadlines. Each event includes a default reminder set for “2 days before.”

2. **GitHub Issue Notifications**:  
   The repository automatically maintains a daily issue titled in the fixed format `Deadline reminders for YYYY-MM-DD`, listing the conference deadlines due that day.

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

### Method 2: Receive GitHub Issue Notifications

To receive daily GitHub deadline issues:

1. Go to the repository’s main page.
2. Click the “Watch” button in the upper-right corner.
3. Select “Custom.”
4. Check the “Issues” box.
5. Verify in your GitHub `Settings -> Notifications` that Web or Email notifications are enabled.

This way, you’ll receive a GitHub notification whenever the workflow updates or creates a new reminder issue.

**Additional Notes:**

- Reminder issues are tagged with the fixed label `deadline-reminder`.
- If the workflow runs multiple times on the same day, it will update the existing issue rather than creating duplicates.
- If the repository remains inactive for an extended period, GitHub may pause scheduled workflows. To resume, simply re-enable Actions or manually run the workflow once.

## For Repository Maintainers

### 1. Enable GitHub Actions

This repository relies on three workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/deploy-pages.yml`
- `.github/workflows/deadline-reminders.yml`

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

After first enabling the repository, it’s advisable to manually run two workflows to confirm everything is functioning correctly:

1. `Deploy Pages`
2. `Deadline Reminders`

This will allow you to immediately verify:

- Whether the Pages site is accessible.
- Whether `conference_calendar.ics` can be downloaded.
- Whether reminder issues are being successfully created.

## How to Update Conference Data

Only edit:

- `data/conferences.yml`

Do not manually edit:

- `conference_calendar.md`

After making changes, run the following commands locally:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/build_calendar.py
python3 -m unittest discover -s tests -v
```

Then commit these files:

- `data/conferences.yml`
- `conference_calendar.md`
- `site/index.html`
- `site/conference_calendar.ics`
- `site/conference_calendar.json`

## Deadline Reminder Rules

- Only applies to deadlines with specific dates.
- Checks are performed at fixed intervals: `30 / 14 / 7 / 3 / 1` days before the deadline.
- Dates are calculated based on the `Europe/Berlin` time zone.
- Only one issue is maintained per day.

## Directory Structure

- `data/conferences.yml`: The single source of truth.
- `scripts/build_calendar.py`: Generates Markdown, HTML, ICS, and JSON files.
- `scripts/build_reminders.py`: Creates the payload for the daily reminder issue.
- `tests/`: Contains validation, generation, ICS, and reminder regression tests.
- `site/`: The output published by GitHub Pages.
