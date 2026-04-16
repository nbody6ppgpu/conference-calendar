# AGENTS Instructions

0. Here the term EXPLORE(url) means: 
   - Open the webpage and extract: **title, link, location, start/end dates, registration deadlines, abstract deadlines, comments**. If you did not find any of the required information, such as registration deadline, you open (retrieve) other links on the given webpage, such as tabs or links shows "dates" "important date" "registration" "abstract submission" and so on to try fetching the data from second/third/fourth-level pages which are accessible on the given webpage. However, do **not** use general search engine tool/MCP such as Google, to prevent getting inauthentic information. 

1. **When you are given a URL link:**
   - EXPLORE the give url
   - Update only **`data/conferences.yml`**. Do **not** hand-edit `conference_calendar.md`.
   - If there are multiple registration/abstract deadlines, split them into structured array items with **`label` + `date`**.
   - If a deadline only has text like **`TBA`**, **`open`**, or **`?`**, keep it in **`registration_display`** / **`abstract_display`** instead of inventing a date.
   - You do not fill in the `comments` field unless instructed by user.
   - After editing YAML, run **`python3 scripts/build_calendar.py`** to regenerate the Markdown/JSON/ICS/HTML outputs.

2. **When asked to clean the table or clean the calendar:**
   - Update only **`data/conferences.yml`**. Do **not** hand-edit `conference_calendar.md`.
   - Step a: in `data/conferences.yml`, for every event inside "Conference Calendar" but NOT under "Past events", evaluate if it is outdated. Outdated means `end_date < today`. Move every outdated events from "Conference Calendar" into "Past events". 
   - Step b: for every event inside "Conference Calendar" but NOT under "Past events", check  `start_date`, `end_date`, `registration_deadlines`, `abstract_deadlines` , if any of them is empty or contain no date, you EXPLORE the corresponding conference url and try updating the entry. You do not fill in the `comments` field unless instructed by user.
   - Step c: evalute whether you have moved any outdated conferences in Step 1 or updated any missing fields in Step 2.
   - Step d (optional): if user explicitly ask you not to run build script, you stop here and do not execute this step. Else, evaluate if anything has changed in `data/conferences.yml`; if yes you run **`python3 scripts/build_calendar.py`**.

