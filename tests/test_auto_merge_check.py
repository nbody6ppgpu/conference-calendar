from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import auto_merge_check as amc  # noqa: E402
from calendar_core import load_conferences  # noqa: E402

TODAY = date(2026, 10, 7)

TEMPLATE = (
    "**Please do not remove the `[new]` tag in the title, otherwise it will not trigger the AI automation.**\n\n"
    "URL link for the meeting:{url}\n\n\n"
    "Comments to show on the calendar table (e.g., special reason why it is interesting?):{comments}"
)


def body(url: str = "\n\nhttps://example.org/meeting/2027/", comments: str = "\n") -> str:
    return TEMPLATE.format(url=url, comments=comments)


def entry(entry_id: str, *, title: str = "Example Meeting 2027", comments: str = '""', url: str = "https://example.org/meeting/2027/",
          start: str = "2027-03-10", end: str = "2027-03-14", extra: str = "") -> str:
    return f"""  - id: {entry_id}
    title: {title}
    url: {url}
    location: Heidelberg, Germany
    start_date: {start}
    end_date: {end}
    registration_deadlines:
      - label: Registration
        date: 2027-01-15
    abstract_deadlines: []
    registration_display: ""
    abstract_display: ""
    other_deadlines: []
    comments: {comments}
{extra}"""


ACTIVE = entry("active-2027", title="Active Thing", url="https://example.org/active/", start="2027-05-01", end="2027-05-02")
BASE = "conferences:\n  # Past events\n" + entry("old-2024", title="Old Meeting", url="https://example.org/old/", start="2024-01-01", end="2024-01-02") + \
    "  # Conference Calendar\n" + ACTIVE


def write(directory: str, name: str, text: str) -> str:
    path = Path(directory) / name
    path.write_text(text, encoding="utf-8")
    return str(path)


class IssueBodyTests(unittest.TestCase):
    def test_url_on_own_line_and_empty_comments(self):
        fields = amc.parse_issue_body(body())
        self.assertEqual(fields.url, "https://example.org/meeting/2027/")
        self.assertEqual(fields.comments, "")

    def test_url_on_same_line_and_comments(self):
        fields = amc.parse_issue_body(body("  https://tdli.sjtu.edu.cn/event/5006/", "\nsent by Dominika\r\n"))
        self.assertEqual(fields.url, "https://tdli.sjtu.edu.cn/event/5006/")
        self.assertEqual(fields.comments, "sent by Dominika")

    def test_comments_may_contain_urls_and_newlines(self):
        fields = amc.parse_issue_body(body(comments="\n\nsee: \nhttps://other.example/page.htm\n"))
        self.assertEqual(fields.url, "https://example.org/meeting/2027/")
        self.assertIn("https://other.example/page.htm", fields.comments)

    def test_ambiguous_bodies_rejected(self):
        bad = [
            body("\nhttps://a.example/x https://b.example/y\n"),  # two URLs
            body("\nsee https://a.example/x\n"),  # extra text
            body("\n\n"),  # no URL
            "no template at all",
            body("\nftp://a.example/x\n"),
            body("\nhttps://user:pw@a.example/x\n"),
            body("\nhttps://a.example/x`id`\n"),
            body() + "\nURL link for the meeting: https://b.example/\n",  # duplicated field
        ]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(amc.CheckError):
                amc.parse_issue_body(text)

    def test_comments_match_tolerates_only_whitespace_folding(self):
        self.assertTrue(amc.comments_match("a b", "a\nb"))
        self.assertTrue(amc.comments_match("", ""))
        self.assertFalse(amc.comments_match("a b", "a c"))
        self.assertFalse(amc.comments_match("", "something"))


class DiffCheckTests(unittest.TestCase):
    def check(self, head_text: str, *, url="https://example.org/meeting/2027/", comments="", base_text=BASE, today=TODAY):
        with tempfile.TemporaryDirectory() as d:
            return amc.check_diff(write(d, "base.yml", base_text), write(d, "head.yml", head_text), url, comments, today)

    def test_one_added_entry_passes(self):
        head = BASE + entry("example-meeting-2027")
        errors, conf = self.check(head)
        self.assertEqual(errors, [])
        self.assertEqual(conf.id, "example-meeting-2027")

    def test_added_in_middle_of_active_section_passes(self):
        head = BASE.replace(ACTIVE,
                            entry("example-meeting-2027") + ACTIVE)
        self.assertEqual(self.check(head)[0], [])

    def test_existing_entry_modified(self):
        head = BASE.replace("Heidelberg, Germany", "Elsewhere", 1) + entry("example-meeting-2027")
        errors, _ = self.check(head)
        self.assertTrue(any("modified" in e for e in errors), errors)

    def test_existing_entry_removed(self):
        head = BASE.replace(ACTIVE, "") + entry("example-meeting-2027")
        errors, _ = self.check(head)
        self.assertTrue(any("removed" in e for e in errors), errors)

    def test_two_added(self):
        errors, conf = self.check(BASE + entry("example-meeting-2027") + entry("another-2027"))
        self.assertTrue(any("exactly one" in e for e in errors), errors)
        self.assertIsNone(conf)

    def test_wrong_section(self):
        head = BASE.replace("  # Conference Calendar\n", entry("example-meeting-2027") + "  # Conference Calendar\n")
        errors, _ = self.check(head)
        self.assertTrue(any("marker" in e for e in errors), errors)

    def test_reordered(self):
        a, b = ACTIVE, entry("zzz-2027", title="Zzz", url="https://example.org/zzz/")
        base = BASE.replace(a, a + b)
        head = BASE.replace(a, b + a) + entry("example-meeting-2027")
        errors, _ = self.check(head, base_text=base)
        self.assertTrue(any("reordered" in e for e in errors), errors)

    def test_comments_must_match_issue(self):
        head = BASE + entry("example-meeting-2027", comments="invented comment")
        self.assertTrue(any("comments" in e for e in self.check(head)[0]))
        self.assertEqual(self.check(head, comments="invented comment")[0], [])

    def test_url_host_must_match_issue_but_www_tolerated(self):
        head = BASE + entry("example-meeting-2027", url="https://www.example.org/x")
        self.assertEqual(self.check(head)[0], [])
        head = BASE + entry("example-meeting-2027", url="https://evil.example.net/x")
        self.assertTrue(any("host" in e for e in self.check(head)[0]))

    def test_bad_ids(self):
        for bad in ("Example-2027", "example-meeting", "example_meeting-2027"):
            with self.subTest(bad=bad):
                errors, _ = self.check(BASE + entry(bad))
                self.assertTrue(any("slug" in e for e in errors), errors)

    def test_duplicate_id_rejected(self):
        errors, _ = self.check(BASE + entry("active-2027"))
        self.assertTrue(errors)

    def test_past_entry_rejected(self):
        head = BASE + entry("example-meeting-2027", start="2026-01-01", end="2026-01-02")
        self.assertTrue(any("past" in e for e in self.check(head)[0]))

    def test_placeholder_is_not_past(self):
        head = BASE + entry("example-meeting-2027", start='""', end='""')
        self.assertEqual(self.check(head)[0], [])

    def test_duplicate_url_title_or_stem_rejected(self):
        dup_url = BASE + entry("example-meeting-2027", url="https://www.example.org/active")
        self.assertTrue(any("same url" in e for e in self.check(dup_url)[0]))
        dup_title = BASE + entry("example-meeting-2027", title="active thing!")
        self.assertTrue(any("title" in e for e in self.check(dup_title.replace("2027-05-01", "2027-05-01"))[0]))
        # An old placeholder/past entry with the same url counts too.
        dup_past = BASE + entry("example-meeting-2027", url="https://example.org/old")
        self.assertTrue(any("same url" in e for e in self.check(dup_past)[0]))

    def test_new_edition_of_a_series_is_allowed(self):
        base = BASE.replace("old-2024", "example-meeting-2026").replace("Old Meeting", "Example Meeting 2026")
        errors, _ = self.check(base.replace("start_date: 2024-01-01", "start_date: 2026-01-01")
                               .replace("end_date: 2024-01-02", "end_date: 2026-01-02")
                               + entry("example-meeting-2027"), base_text=base)
        self.assertEqual([e for e in errors if "duplicate" in e], [])

    def test_extra_key_rejected(self):
        head = BASE + entry("example-meeting-2027", extra="    surprise: 1\n")
        self.assertTrue(any("keys" in e for e in self.check(head)[0]))


def pr_json(**over):
    pr = {"number": 80, "body": "Fixes #79\n\nAdds...", "user": {"login": amc.APP_LOGIN, "type": "Bot"},
          "head": {"ref": "claude/issue-79-123456", "sha": "abc", "repo": {"full_name": "o/r"}},
          "base": {"repo": {"full_name": "o/r"}}}
    pr.update(over)
    return pr


ISSUE = {"number": 79, "author_association": "OWNER", "user": {"login": "kai"}, "body": body()}
GOOD_COMMIT = [(amc.COMMIT_AUTHOR_NAME, amc.COMMIT_AUTHOR_EMAIL)]


class GateTests(unittest.TestCase):
    def gate(self, pr=None, issue=None, commits=None, files=None, trusted=frozenset(), head=None):
        with tempfile.TemporaryDirectory() as d:
            return amc.run_gate(
                pr or pr_json(), issue or ISSUE, GOOD_COMMIT if commits is None else commits,
                files or [amc.DATA_FILE], write(d, "b.yml", BASE),
                write(d, "h.yml", head or BASE + entry("example-meeting-2027")), set(trusted), TODAY)

    def test_happy_path(self):
        result = self.gate()
        self.assertEqual(result["reasons"], [])
        self.assertTrue(result["eligible"])
        self.assertEqual(result["issue_number"], "79")
        self.assertEqual(result["entry_id"], "example-meeting-2027")

    def test_issue_author_association(self):
        for assoc in ("OWNER", "MEMBER", "COLLABORATOR"):
            self.assertTrue(self.gate(issue=dict(ISSUE, author_association=assoc))["eligible"], assoc)
        for assoc in ("CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "NONE", None):
            issue = dict(ISSUE, author_association=assoc)
            self.assertFalse(self.gate(issue=issue)["eligible"], assoc)
        # The optional login allowlist only adds to the trusted set.
        issue = dict(ISSUE, author_association="NONE", user={"login": "kai"})
        self.assertTrue(self.gate(issue=issue, trusted={"kai"})["eligible"])
        self.assertFalse(self.gate(issue=dict(issue, user={"login": "mallory"}), trusted={"kai"})["eligible"])

    def test_wrong_author_commit_or_files(self):
        self.assertFalse(self.gate(pr=pr_json(user={"login": "someone", "type": "User"}))["eligible"])
        self.assertFalse(self.gate(commits=GOOD_COMMIT + [("human", "h@example.org")])["eligible"])
        self.assertFalse(self.gate(commits=[])["eligible"])
        self.assertFalse(self.gate(files=[amc.DATA_FILE, ".github/workflows/x.yml"])["eligible"])

    def test_number_mismatch_and_fork(self):
        self.assertFalse(self.gate(pr=pr_json(body="Fixes #80"))["eligible"])
        fork = pr_json(head={"ref": "claude/issue-79-1", "sha": "a", "repo": {"full_name": "x/r"}})
        self.assertFalse(self.gate(pr=fork)["eligible"])
        self.assertFalse(self.gate(pr=pr_json(head={"ref": "feature", "sha": "a", "repo": {"full_name": "o/r"}}))["eligible"])

    def test_issue_that_is_a_pull_request(self):
        self.assertFalse(self.gate(issue=dict(ISSUE, pull_request={}))["eligible"])


class ComparisonTests(unittest.TestCase):
    PAGE = """<html><body><h1>Example &amp; Meeting 2027</h1>
    <p>Heidelberg,   Germany</p><p>10&ndash;14 March 2027</p><p>Registration deadline: 15 January 2027</p>
    </body><script>var cfg = {"abstractDeadline": "2027-01-15 extra"};</script></html>"""

    def make(self, **over):
        ev = lambda q: [{"url": "https://example.org/meeting/2027/", "quote": q}]
        verdict = {
            "title": {"value": "Example Meeting 2027", "evidence": ev("Example & Meeting 2027")},
            "location": {"value": "Heidelberg, Germany", "evidence": ev("Heidelberg, Germany")},
            "start_date": {"value": "2027-03-10", "evidence": ev("10-14 March 2027")},
            "end_date": {"value": "2027-03-14", "evidence": ev("10-14 March 2027")},
            "registration_deadlines": {"value": [{"label": "Registration", "date": "2027-01-15"}],
                                       "evidence": ev("Registration deadline: 15 January 2027")},
            "abstract_deadlines": {"value": [], "evidence": []},
            "other_deadlines": {"value": [], "evidence": []},
            "registration_display": {"value": "", "evidence": []},
            "abstract_display": {"value": "", "evidence": []},
        }
        verdict.update(over)
        return verdict

    def conf(self, **changes):
        with tempfile.TemporaryDirectory() as d:
            text = "conferences:\n  # Past events\n  # Conference Calendar\n" + entry("example-meeting-2027")
            for old, new in changes.items():
                text = text.replace(old, new)
            return load_conferences(write(d, "c.yml", text))[0]

    def run_compare(self, verdict, conf=None):
        verifier = amc.EvidenceVerifier(["https://example.org/meeting/2027/"], fetch=lambda u: (u, self.PAGE))
        return amc.compare_verdict(conf or self.conf(), verdict, verifier)

    def failed(self, rows):
        return [r.field for r in rows if not r.ok]

    def test_exact_match_passes(self):
        rows = self.run_compare(self.make())
        self.assertEqual(self.failed(rows), [], amc.render_table(rows))

    def test_date_mismatch_fails(self):
        rows = self.run_compare(self.make(), self.conf(**{"2027-03-14": "2027-03-13"}))
        self.assertEqual(self.failed(rows), ["end_date"])

    def test_missing_deadline_fails(self):
        rows = self.run_compare(self.make(abstract_deadlines={"value": [{"label": "A", "date": "2027-01-15"}],
                                                              "evidence": [{"url": "https://example.org/meeting/2027/",
                                                                            "quote": '"abstractDeadline": "2027-01-15'}]}))
        self.assertEqual(self.failed(rows), ["abstract_deadlines"])

    def test_raw_html_evidence_counts(self):
        verdict = self.make(abstract_deadlines={"value": [{"label": "A", "date": "2027-01-15"}], "evidence": [
            {"url": "https://example.org/meeting/2027/", "quote": '"abstractDeadline": "2027-01-15 extra"'}]})
        conf = self.conf(**{"abstract_deadlines: []": "abstract_deadlines:\n      - label: A\n        date: 2027-01-15"})
        self.assertEqual(self.failed(self.run_compare(verdict, conf)), [])

    URL = "https://example.org/meeting/2027/"

    def display_verdict(self, value, quote):
        return self.make(registration_display={"value": value, "evidence": [{"url": self.URL, "quote": quote}]})

    def test_invented_year_in_display_fails(self):
        conf = self.conf(**{'registration_display: ""': 'registration_display: Registration deadline 15 January 2028'})
        rows = self.run_compare(self.display_verdict("Registration deadline 15 January 2027",
                                                     "Registration deadline: 15 January 2027"), conf)
        self.assertEqual(self.failed(rows), ["registration_display"])

    def test_display_backed_by_own_evidence_passes(self):
        conf = self.conf(**{'registration_display: ""': 'registration_display: Registration deadline 15 January 2027'})
        rows = self.run_compare(self.display_verdict("Registration deadline 15 January 2027",
                                                     "Registration deadline: 15 January 2027"), conf)
        self.assertEqual(self.failed(rows), [], amc.render_table(rows))

    def test_display_requires_reviewer_text_and_own_digits(self):
        conf = self.conf(**{'registration_display: ""': 'registration_display: Registration deadline 15 January 2027'})
        self.assertEqual(self.failed(self.run_compare(self.make(), conf)), ["registration_display"])
        # Digits present only in another field's evidence do not count.
        rows = self.run_compare(self.display_verdict("Registration deadline 15 January 2027", "Heidelberg, Germany"), conf)
        self.assertEqual(self.failed(rows), ["registration_display"])

    def test_empty_pr_display_but_reviewer_text_fails(self):
        rows = self.run_compare(self.display_verdict("Mid November (TBC)", "Registration deadline: 15 January 2027"))
        self.assertEqual(self.failed(rows), ["registration_display"])

    def test_date_support_rules(self):
        q = amc.quote_supports_date
        self.assertTrue(q("10-14 March 2027", "2027-03-10"))
        self.assertTrue(q("Deadline: 15 Nov 2026", "2026-11-15"))
        self.assertTrue(q("deadline 2026-11-15", "2026-11-15"))
        self.assertTrue(q("deadline 15.11.2026", "2026-11-15"))
        self.assertTrue(q("deadline 15/11/2026", "2026-11-15"))
        self.assertTrue(q("deadline 11/15/2026", "2026-11-15"))
        self.assertTrue(q("March 15 (final deadline)", "2026-03-15"))
        self.assertFalse(q("deadline 15 November 2025", "2026-11-15"))  # conflicting year
        self.assertFalse(q("deadline 15 December 2026", "2026-11-15"))  # wrong month
        self.assertFalse(q("deadline 16 November 2026", "2026-11-15"))  # wrong day
        self.assertFalse(q("deadline 16/11/2026", "2026-11-15"))

    def test_numeric_day_range_supports_endpoints_only(self):
        q = amc.quote_supports_date
        quote = "11-15/10/2027: IAU symposium 414 in Puerto Natales"
        self.assertTrue(q(quote, "2027-10-11"))
        self.assertTrue(q(quote, "2027-10-15"))
        self.assertFalse(q(quote, "2027-10-12"))  # inside the range, not an endpoint
        self.assertFalse(q(quote, "2027-11-11"))
        self.assertFalse(q(quote, "2026-10-11"))
        self.assertFalse(q("11-15/10/2027", "2027-10-10"))
        for variant in ("11\u201315/10/2027", "11 - 15/10/2027", "11-15.10.2027", "11\u201315.10.2027"):
            with self.subTest(variant=variant):
                self.assertTrue(q(variant, "2027-10-11"))
                self.assertTrue(q(variant, "2027-10-15"))
                self.assertFalse(q(variant, "2027-10-12"))
                self.assertTrue(amc.has_numeric_date(amc.normalize_text(variant)))
        # Day-first only: no M/D reading for a range.
        self.assertFalse(q("11-15/10/2027", "2027-11-10"))
        # Not inside ISO dates or longer digit runs; a bare day with a numeric month elsewhere is no support.
        self.assertFalse(q("2027-10-11", "2027-10-12"))
        self.assertTrue(q("2027-10-11", "2027-10-11"))
        self.assertFalse(amc.has_numeric_date("on 11-15 november"))
        self.assertFalse(q("2026-11-15/10/2027", "2026-11-11"))
        self.assertFalse(q("311-15/10/2027", "2027-10-11"))
        self.assertFalse(q("on the 11 (10/2027)", "2027-10-11"))

    def title_case(self, pr_title):
        conf = self.conf(**{"title: Example Meeting 2027": f"title: {pr_title}"})
        return self.failed(self.run_compare(self.make(), conf))  # reviewer title: "Example Meeting 2027"

    def test_reviewer_may_omit_title_words_found_on_the_page(self):
        self.assertEqual(self.title_case("Example Heidelberg Meeting 2027"), [])  # "heidelberg" is on the page

    def test_title_words_missing_from_every_page_fail(self):
        self.assertEqual(self.title_case("Example Meeting Deluxe 2027"), ["title"])
        self.assertEqual(self.title_case("Example Meeting III 2027"), ["title"])

    def test_title_off_target_quote_passes_when_all_words_on_pages(self):
        # Same words, reordered; the quote verifies but cites the wrong line.
        off = lambda value: self.make(title={"value": value, "evidence": [{"url": self.URL, "quote": "Heidelberg,   Germany"}]})
        conf = self.conf(**{"title: Example Meeting 2027": "title: Meeting Example 2027"})
        rows = self.run_compare(off("Example Meeting 2027"), conf)
        self.assertEqual(self.failed(rows), [], amc.render_table(rows))
        self.assertEqual(self.failed(self.run_compare(off("Example Meeting 2027"))), [])

    def test_title_off_target_quote_fails_when_a_word_is_absent(self):
        conf = self.conf(**{"title: Example Meeting 2027": "title: Example Meeting Deluxe 2027"})
        verdict = self.make(title={"value": "Deluxe Example Meeting 2027", "evidence": [
            {"url": self.URL, "quote": "Heidelberg,   Germany"}]})
        self.assertEqual(self.failed(self.run_compare(verdict, conf)), ["title"])
        # An unverifiable quote still fails even if every word is on the page.
        bad = self.make(title={"value": "Example Meeting 2027", "evidence": [
            {"url": self.URL, "quote": "this text is not on the page"}]})
        self.assertEqual(self.failed(self.run_compare(bad)), ["title"])

    def test_unverified_or_foreign_evidence_fails(self):
        bad_quote = self.make(title={"value": "Example Meeting 2027", "evidence": [
            {"url": "https://example.org/meeting/2027/", "quote": "this text is not on the page"}]})
        self.assertEqual(self.failed(self.run_compare(bad_quote)), ["title"])
        foreign = self.make(title={"value": "Example Meeting 2027", "evidence": [
            {"url": "https://evil.example.net/", "quote": "Example & Meeting 2027"}]})
        self.assertEqual(self.failed(self.run_compare(foreign)), ["title"])
        none = self.make(title={"value": "Example Meeting 2027", "evidence": []})
        self.assertEqual(self.failed(self.run_compare(none)), ["title"])

    def test_short_quote_rejected(self):
        verdict = self.make(start_date={"value": "2027-03-10", "evidence": [
            {"url": "https://example.org/meeting/2027/", "quote": "10 March 2027"}]})
        self.assertEqual(self.failed(self.run_compare(verdict)), ["start_date"])

    def test_day_month_year_must_appear_in_quote(self):
        verdict = self.make(start_date={"value": "2027-03-10", "evidence": [
            {"url": "https://example.org/meeting/2027/", "quote": "Heidelberg, Germany"}]})
        self.assertEqual(self.failed(self.run_compare(verdict)), ["start_date"])

    def test_missing_field_and_malformed(self):
        verdict = self.make()
        del verdict["location"]
        self.assertEqual(self.failed(self.run_compare(verdict)), ["location"])
        self.assertEqual(self.failed(self.run_compare([])), ["verdict"])

    def test_other_deadline_type_matters(self):
        verdict = self.make(other_deadlines={"value": [{"type": "funding", "label": "Grants", "date": ""}],
                                             "evidence": [{"url": "https://example.org/meeting/2027/",
                                                           "quote": "Registration deadline"}]})
        self.assertEqual(self.failed(self.run_compare(verdict)), ["other_deadlines"])

    def test_title_token_rule(self):
        m = amc.text_fields_match
        self.assertTrue(m("IAU GA 2027", "iau  ga 2027!"))
        self.assertFalse(m("Cosmic Collisions 2026 Workshop", "Cosmic Collisions 2026"))
        self.assertFalse(m("Stars", "Stars on the Run III"))
        self.assertTrue(m("The Stars of the Run III", "Stars Run III"))
        self.assertTrue(m("2nd Cosmic Collisions", "Cosmic Collisions"))
        self.assertFalse(m("Cosmic Collisions 2026", "Stellar Streams 2026"))
        self.assertFalse(m("Meeting 2026", "Meeting 2027"))
        self.assertTrue(m("Meeting", "Meeting 2027"))
        self.assertFalse(m("", "Heidelberg"))
        self.assertTrue(m("", ""))

    def test_location_rule(self):
        m = amc.location_match
        self.assertTrue(m("Heidelberg, Germany", "Heidelberg"))
        self.assertFalse(m("Heidelberg", "Heidelberg, Germany"))
        self.assertFalse(m("Heidelberg", ""))
        self.assertTrue(m("", ""))


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class EvidenceTests(unittest.TestCase):
    def test_google_sites_markup_with_short_dated_quotes(self):
        # Trimmed real markup from a Google Sites "important dates" page: the date and its colon sit
        # in one span, the label in another, and the same text also lives in a JS string with \t escapes.
        page = (FIXTURES / "google_sites_important_dates.html").read_text(encoding="utf-8")
        for quote in ("30/04/2027:", "15/11/2027:", "05/01/2027:", "30/04/2027: Deadline for registration and fee submission"):
            with self.subTest(quote=quote):
                self.assertTrue(amc.quote_in_page(quote, page))
        self.assertFalse(amc.quote_in_page("2027", page))  # short and not a full date
        self.assertFalse(amc.quote_in_page("30/05/2027:", page))
        self.assertTrue(amc.quote_supports_date("30/04/2027:", "2027-04-30"))
        self.assertFalse(amc.quote_supports_date("30/04/2027:", "2027-04-29"))

    def test_normalization(self):
        page = "<p>Early&nbsp;bird\n  deadline&mdash;<b>1 Feb</b></p><!-- c -->"
        self.assertTrue(amc.quote_in_page("EARLY BIRD deadline-1 feb", page))
        self.assertFalse(amc.quote_in_page("late bird deadline", page))

    def test_redirect_off_site_rejected(self):
        verifier = amc.EvidenceVerifier(["https://example.org/"], fetch=lambda u: ("https://evil.example.net/", "quote here ok"))
        res = verifier.verify([{"url": "https://example.org/a", "quote": "quote here ok"}])
        self.assertFalse(res.ok)

    def test_domain_rules(self):
        self.assertTrue(amc.same_site("indico.cern.ch", "cern.ch"))
        self.assertTrue(amc.same_site("a.ac.uk", "b.a.ac.uk"))
        self.assertFalse(amc.same_site("a.ac.uk", "b.ac.uk"))
        self.assertFalse(amc.same_site("sites.google.com", "evil.google.com"))
        self.assertTrue(amc.same_site("sites.google.com", "sites.google.com"))
        self.assertFalse(amc.same_site("example.org", "example.org.evil.net"))


if __name__ == "__main__":
    unittest.main()
