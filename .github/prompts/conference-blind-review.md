# Conference blind review

Read `AGENTS.md` first: the data rules and the `EXPLORE(url)` procedure apply
exactly as written there.

You are an independent fact extractor. You are given exactly one thing, the
URL of a conference's official page (stated in the task prompt). You have not
been shown, and must not look for, any calendar entry, issue, pull request or
other data about this meeting: do not read `data/conferences.yml` or run `git`
commands to find it. Your output is compared by a deterministic script against
an entry written by someone else, so extract only what the official site says.

Procedure:

1. EXPLORE the given URL as defined in `AGENTS.md` (landing page, then the
   same site's important-dates, registration, abstract, funding, sessions,
   program and venue pages; `curl -sL` if WebFetch returns a JS shell). Use
   only the conference's own site. No web search.
2. Extract the following fields. For each one give `value` and `evidence`.
   - `title`: the meeting's name.
   - `location`: city and country (or venue) as the site states it.
   - `start_date`, `end_date`: `YYYY-MM-DD`, or `""` if not stated.
   - `registration_deadlines`: regular/final registration cutoffs only, as
     `{label, date}`. Early-bird or reduced-rate cutoffs belong in
     `other_deadlines`.
   - `abstract_deadlines`: abstract-submission cutoffs, `{label, date}`.
   - `other_deadlines`: every other announced deadline as `{type, label,
     date}` with `type` one of `funding`, `proposal`, `other`; early-bird
     registration is `type: other`, `label: Early-bird registration`. Use
     `date: ""` only if the site explicitly says the item exists but gives no
     date.
   - `registration_display`, `abstract_display`: the site's own wording
     (for example "Mid or end of November (TBC)") when a deadline is stated
     only as text or has no concrete date; `""` otherwise. Never add, change
     or guess a year, month or day that the site does not state.
3. A date field, or a list, that the site does not state is `""` or `[]`.
   Never guess, never infer a year the page does not show, never use a
   third-party source.
4. `evidence` is a list of `{url, quote}`. Every non-empty `value` needs at
   least one item. `url` is the exact page you read (same site as the given
   URL). `quote` is a short verbatim snippet (at least 8 characters, ideally
   one line) copied from that page's visible text, or from its raw HTML or
   embedded JSON if that is where you found the fact. It must contain the
   day and month of every date it supports. Do not paraphrase, translate,
   reformat dates or join separate passages into one quote. A script
   re-fetches each URL and searches for your quote; any quote it cannot find
   makes the whole review fail. Empty values use `evidence: []`.

Output: end your run by returning the result through the structured-output
mechanism (the JSON schema supplied with the task). Do not write files, do
not edit anything, and do not add commentary outside the structured result.
