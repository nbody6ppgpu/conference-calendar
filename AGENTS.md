# AGENTS Instructions

1. **When given a URL link:**
   - Open the webpage and extract: **Date, Location, Meeting title and link, Registration Deadline, Abstract Deadline, Comments (other important info)**.
   - Add a new row to the conference calendar markdown table using that information.
   - Insert the new row in chronological order so the table remains sorted by **Date**.

2. **When asked to clean the table/calendar:**
   - Treat an event as outdated if its conference **Date is earlier than today**.
   - Move outdated events from the main table to the table under **`#Past events`**.
