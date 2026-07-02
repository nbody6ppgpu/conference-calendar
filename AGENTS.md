# AGENTS Instructions

0. Here the term EXPLORE(url) means: 
   - Open the webpage and extract: **title, link, location, start/end dates, registration deadlines, abstract deadlines, comments**. If you did not find any of the required information, such as registration deadline, you open (retrieve) other links on the given webpage, such as tabs or links shows "dates" "important date" "registration" "abstract submission" and so on to try fetching the data from second/third/fourth-level pages which are accessible on the given webpage. However, do **not** use general search engine tool/MCP such as Google, to prevent getting inauthentic information. 

1. **When you are given a URL link:**
   - EXPLORE the give url
   - Update only **`data/conferences.yml`**. Do **not** hand-edit or commit generated outputs such as `conference_calendar.md`, `site/`, or generated per-meeting ICS files under `site/meetings/`.
   - `site/index.html` and `site/past-events.html` are generated. Do not edit them directly; edit `scripts/calendar_core.py` (`build_index_html` / `build_past_events_html`) for page template/static text, then run `python3 scripts/build_calendar.py`.
   - If there are multiple registration/abstract deadlines, split them into structured array items with **`label` + `date`**.
   - If a deadline only has text like **`TBA`**, **`open`**, or **`?`**, keep it in **`registration_display`** / **`abstract_display`** instead of inventing a date.
   - You do not fill in the `comments` field unless instructed by user.
   - After editing YAML, run **`python3 scripts/build_calendar.py`** for local verification unless the user explicitly asks not to. Do not include generated Markdown/JSON/ICS/HTML outputs in the PR; Pages deployment regenerates them automatically.

2. **When asked to clean the table or clean the calendar:**
   - Update only **`data/conferences.yml`**. Do **not** hand-edit or commit generated outputs such as `conference_calendar.md`, `site/`, or generated per-meeting ICS files under `site/meetings/`.
   - Step a: in `data/conferences.yml`, for every event inside "Conference Calendar" but NOT under "Past events", evaluate if it is outdated. Outdated means `end_date < today`. Move every outdated events from "Conference Calendar" into "Past events". 
   - Step b: for every event inside "Conference Calendar" but NOT under "Past events", check  `start_date`, `end_date`, `registration_deadlines`, `abstract_deadlines` , if any of them is empty or contain no date, you EXPLORE the corresponding conference url and try updating the entry. You do not fill in the `comments` field unless instructed by user.
   - Step c: evalute whether you have moved any outdated conferences in Step 1 or updated any missing fields in Step 2.
   - Step d (optional): if user explicitly ask you not to run build script, you stop here and do not execute this step. Else, evaluate if anything has changed in `data/conferences.yml`; if yes you run **`python3 scripts/build_calendar.py`** for local verification. This rebuilds local preview outputs and deletes stale per-meeting schedule ICS files automatically, but those generated files should not be committed.

3. **When asked to review changed conference data (reviewer mode):**
   - Reviewer mode is a factual verification and repair pass for conference entries changed in the current PR or automation run. It is not a full-table cleanup.
   - Identify the changed conference entries from the current PR diff or current working-tree diff for **`data/conferences.yml`**. Review only those entries unless a directly related moved/renamed entry is needed to understand the diff.
   - For each changed entry, EXPLORE the conference URL again using the rule above. Do not rely on the current YAML value as authoritative.
   - Verify **`title`**, **`url`**, **`location`**, **`start_date`**, **`end_date`**, **`registration_deadlines`**, **`abstract_deadlines`**, **`registration_display`**, and **`abstract_display`**.
   - If dates are ambiguous, missing, `TBA`, `open`, or `?`, do not invent dates. Use **`registration_display`** / **`abstract_display`** for text-only deadline states.
   - If you find incorrect, shifted, stale, or unsupported values, directly repair only **`data/conferences.yml`**.
   - Do not change **`comments`** unless the original user issue or task explicitly requested it.
   - For GitHub Actions verification builds, use temporary outputs to keep generated files out of the PR:
     **`python3 scripts/build_calendar.py --markdown-output "$RUNNER_TEMP/conference_calendar.md" --site-dir "$RUNNER_TEMP/site"`**.
