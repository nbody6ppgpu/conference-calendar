# AGENTS Instructions

1. **When given a URL link:**
   - Open the webpage and extract: **title, link, location, start/end dates, registration deadlines, abstract deadlines, comments**.
   - Update only **`data/conferences.yml`**. Do **not** hand-edit `conference_calendar.md`.
   - If there are multiple registration/abstract deadlines, split them into structured array items with **`label` + `date`**.
   - If a deadline only has text like **`TBA`**, **`open`**, or **`?`**, keep it in **`registration_display`** / **`abstract_display`** instead of inventing a date.
   - After editing YAML, run **`python3 scripts/build_calendar.py`** to regenerate the Markdown/JSON/ICS/HTML outputs.

2. **When asked to clean the table/calendar:**
   - Treat an event as outdated if **`end_date < today`**.
   - Do **not** manually move Markdown rows.
   - Update YAML only if the underlying conference data changed, then run **`python3 scripts/build_calendar.py`**. The script automatically places outdated events under **`# Past events`**.
