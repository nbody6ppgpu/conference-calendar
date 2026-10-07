#!/usr/bin/env python3
"""Deterministic checks behind the automatic review-and-merge workflow.

Subcommands
-----------
gate         Decide whether a PR opened by the add-conference automation is
             eligible for automatic review (no model involved).
diff-check   Re-run the data-diff checks (used against the merged tree right
             before merging).
compare      Compare a blind reviewer's JSON verdict with the PR entry,
             re-verifying every evidence quote against the live page.
gate-comment Render the markdown comment explaining a gate refusal.

Everything fails closed: any error, ambiguity or mismatch means "not eligible"
/ "do not merge".  This module is always run from the *base* ref, so a pull
request cannot change the code that judges it.
"""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import re
import ssl
import sys
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import yaml

from calendar_core import Conference, ValidationError, load_conferences
from cleanup_calendar import ACTIVE_SECTION, ENTRY_RE, PAST_SECTION, SECTION_RE

APP_LOGIN = "conference-calendar-bot[bot]"
# claude-code-action commits are authored with this identity (see
# claude-add-conference.yml).  GitHub resolves the email to the
# github-actions[bot] *account*, so the check is on the raw git author fields,
# not on the API login.
COMMIT_AUTHOR_NAME = "claude[bot]"
COMMIT_AUTHOR_EMAIL = "41898282+claude[bot]@users.noreply.github.com"
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
DATA_FILE = "data/conferences.yml"
ENTRY_KEYS = frozenset(
    {
        "id", "title", "url", "location", "start_date", "end_date",
        "registration_deadlines", "abstract_deadlines", "other_deadlines",
        "registration_display", "abstract_display", "comments",
    }
)
ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*-\d{4}")
URL_SAFE_RE = re.compile(r"^https?://[A-Za-z0-9._~:/?#@!$&()*+,;=%\-]+$")
MIN_QUOTE_LEN = 15
MIN_DATE_QUOTE_LEN = 10  # a full numeric date such as 5/1/2027 or 2027-01-05

URL_HEADER_RE = re.compile(r"URL link for the meeting\s*:", re.I)
COMMENTS_HEADER_RE = re.compile(r"Comments to show on the calendar table\s*(?:\([^)\n]*\))?\s*:", re.I)


class CheckError(Exception):
    pass


# --------------------------------------------------------------------------
# Issue body parsing
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class IssueFields:
    url: str
    comments: str


def parse_issue_body(body: str) -> IssueFields:
    """Parse the "Add a new meeting" template body; raise CheckError if ambiguous."""
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    url_headers = list(URL_HEADER_RE.finditer(text))
    comment_headers = list(COMMENTS_HEADER_RE.finditer(text))
    if len(url_headers) != 1 or len(comment_headers) != 1:
        raise CheckError("issue body does not contain each template field exactly once")
    url_header, comment_header = url_headers[0], comment_headers[0]
    if url_header.end() > comment_header.start():
        raise CheckError("issue body fields are not in template order")

    url_section = text[url_header.end():comment_header.start()]
    urls = re.findall(r"https?://\S+", url_section)
    if len(urls) != 1:
        raise CheckError(f"expected exactly one URL in the URL field, found {len(urls)}")
    url = urls[0].rstrip(".,;")
    leftover = url_section.replace(urls[0], "", 1).strip()
    if leftover:
        raise CheckError("the URL field contains text besides a single URL")
    if not URL_SAFE_RE.match(url):
        raise CheckError("the URL contains characters that are not allowed")
    parts = urlsplit(url)
    if not parts.hostname or "@" in parts.netloc:
        raise CheckError("the URL has no usable host or contains credentials")
    if not is_public_hostname(parts.hostname):
        raise CheckError("the URL host is an IP address, localhost or not a public domain name")

    comments = text[comment_header.end():].strip()
    return IssueFields(url=url, comments=comments)


def _collapse(value: str) -> str:
    return " ".join(value.split())


def comments_match(entry_comments: str, issue_comments: str) -> bool:
    """Verbatim, tolerating only YAML line folding (whitespace runs)."""
    return entry_comments == issue_comments or _collapse(entry_comments) == _collapse(issue_comments)


# --------------------------------------------------------------------------
# Hosts
# --------------------------------------------------------------------------

MULTI_SUFFIXES = frozenset(
    "co.uk ac.uk org.uk gov.uk com.cn edu.cn ac.cn org.cn gov.cn net.cn com.au edu.au org.au "
    "co.jp ac.jp or.jp co.kr ac.kr com.br co.in ac.in edu.tw com.tw org.tw com.hk edu.hk "
    "co.za ac.za".split()
)
# Generic rule: under a 2-letter ccTLD these second-level labels are part of the public suffix
# (a.ac.nz and b.ac.nz are different sites), even when MULTI_SUFFIXES does not list the pair.
CC_SECOND_LEVEL = frozenset("ac co com edu gov net org or ne go gob nic mil sch res".split())
# Platforms where unrelated projects share a registrable domain: require the
# exact host there.
SHARED_PLATFORMS = frozenset(
    "google.com github.io githubusercontent.com wordpress.com wixsite.com sharepoint.com "
    "blogspot.com notion.site netlify.app pages.dev vercel.app herokuapp.com weebly.com "
    "squarespace.com gitlab.io readthedocs.io".split()
)
# Shared hosts where the tenant is the leading path (not the subdomain): the first N path segments
# (e.g. /view/<site-id>) must match too.
PATH_TENANTED = {"sites.google.com": 2, "raw.githubusercontent.com": 2}


def is_public_hostname(host: str | None) -> bool:
    """Reject IP literals (any notation), localhost and single-label names."""
    host = (host or "").lower().rstrip(".")
    if not host or "." not in host or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not host.rsplit(".", 1)[1].isdigit()  # 127.1, 2130706433 and similar


def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def registrable_domain(host: str) -> str:
    labels = host.split(".")
    if len(labels) >= 3 and (
        ".".join(labels[-2:]) in MULTI_SUFFIXES
        or (len(labels[-1]) == 2 and labels[-1].isalpha() and labels[-2] in CC_SECOND_LEVEL)
    ):
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def same_site(host_a: str, host_b: str) -> bool:
    if not host_a or not host_b:
        return False
    reg = registrable_domain(host_a)
    if reg != registrable_domain(host_b):
        return False
    return host_a == host_b if reg in SHARED_PLATFORMS else True


def tenant_prefix(url: str) -> tuple[str, ...]:
    """Leading path segments that identify the tenant on path-tenanted hosts (else empty)."""
    n = PATH_TENANTED.get(host_of(url), 0)
    return tuple(seg.casefold() for seg in urlsplit(url).path.split("/") if seg)[:n] if n else ()


def same_site_url(url_a: str, url_b: str) -> bool:
    """same_site on the hosts, plus equal tenant path prefix on path-tenanted hosts."""
    return same_site(host_of(url_a), host_of(url_b)) and tenant_prefix(url_a) == tenant_prefix(url_b)


# --------------------------------------------------------------------------
# Diff checks on conferences.yml
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Block:
    id: str
    text: str
    section: str


def split_layout(text: str) -> tuple[str, list[Block]]:
    """Return (non-entry text without markers, entry blocks with their section)."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if ENTRY_RE.match(line.rstrip("\r\n"))]
    if not starts:
        raise CheckError("no conference entries found")
    markers: dict[str, list[int]] = {PAST_SECTION: [], ACTIVE_SECTION: []}
    for i, line in enumerate(lines):
        m = SECTION_RE.match(line.rstrip("\r\n"))
        if m:
            markers[m.group("section")].append(i)
    if len(markers[PAST_SECTION]) != 1 or len(markers[ACTIVE_SECTION]) != 1:
        raise CheckError("file must contain exactly one of each section marker")
    past_pos, active_pos = markers[PAST_SECTION][0], markers[ACTIVE_SECTION][0]
    if not (past_pos < starts[0] and active_pos > past_pos):
        raise CheckError("section markers are out of order")

    blocks: list[Block] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        block_lines = [l for l in lines[start:end] if not SECTION_RE.match(l.rstrip("\r\n"))]
        m = ENTRY_RE.match(lines[start].rstrip("\r\n"))
        try:
            entry_id = yaml.safe_load(m.group("value"))
        except yaml.YAMLError as exc:
            raise CheckError(f"unparseable entry id at line {start + 1}") from exc
        if not isinstance(entry_id, str) or not entry_id:
            raise CheckError(f"entry id at line {start + 1} is not a string")
        blocks.append(Block(entry_id, "".join(block_lines), PAST_SECTION if start < active_pos else ACTIVE_SECTION))
    prefix = "".join(l for i, l in enumerate(lines[: starts[0]]) if i not in (past_pos, active_pos))
    return prefix, blocks


def check_diff(
    base_path: str | Path,
    head_path: str | Path,
    issue_url: str,
    issue_comments: str,
    today: date,
) -> tuple[list[str], Conference | None]:
    """Return (error list, the added Conference or None)."""
    errors: list[str] = []
    try:
        base_prefix, base_blocks = split_layout(Path(base_path).read_text(encoding="utf-8"))
        head_prefix, head_blocks = split_layout(Path(head_path).read_text(encoding="utf-8"))
        head_confs = {c.id: c for c in load_conferences(head_path)}
        load_conferences(base_path)
    except (CheckError, ValidationError, OSError, yaml.YAMLError) as exc:
        return [f"data file could not be analysed: {exc}"], None

    base_ids = [b.id for b in base_blocks]
    head_ids = [b.id for b in head_blocks]
    added = [i for i in head_ids if i not in base_ids]
    removed = [i for i in base_ids if i not in head_ids]
    if removed:
        errors.append(f"existing entries removed: {', '.join(removed)}")
    if len(added) != 1:
        errors.append(f"expected exactly one added entry, found {len(added)}")
        return errors, None
    new_id = added[0]
    if head_ids.count(new_id) != 1:
        errors.append("the new entry id occurs more than once")
    if [i for i in head_ids if i != new_id] != base_ids:
        errors.append("existing entries were reordered")
    if head_prefix != base_prefix:
        errors.append("text outside the entries (file header) changed")
    base_by_id = {b.id: b for b in base_blocks}
    for block in head_blocks:
        if block.id == new_id:
            continue
        old = base_by_id.get(block.id)
        if old is not None and (old.text != block.text or old.section != block.section):
            errors.append(f"existing entry modified or moved: {block.id}")
    new_block = next(b for b in head_blocks if b.id == new_id)
    if new_block.section != ACTIVE_SECTION:
        errors.append("the new entry is not below the '# Conference Calendar' marker")

    try:
        raw = yaml.safe_load(new_block.text)
        keys = set(raw[0]) if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], dict) else None
    except yaml.YAMLError:
        keys = None
    if keys != ENTRY_KEYS:
        errors.append("the new entry does not have exactly the expected set of keys")

    if not ID_RE.fullmatch(new_id):
        errors.append(f"id {new_id!r} is not a lowercase hyphenated slug ending in a 4-digit year")
    conf = head_confs.get(new_id)
    if conf is None:
        errors.append("the new entry could not be loaded")
        return errors, None
    if not comments_match(conf.comments, issue_comments):
        errors.append("entry comments differ from the issue's comments field")
    if not conf.url or not host_of(conf.url) or host_of(conf.url) != host_of(issue_url):
        errors.append("entry url host differs from the issue URL host")
    elif tenant_prefix(conf.url) != tenant_prefix(issue_url):
        errors.append("entry url is a different site on the same shared host as the issue URL")
    if conf.start_date is not None and conf.end_date is not None and conf.start_date > conf.end_date:
        errors.append("start_date is after end_date")
    if conf.end_date is not None and conf.end_date < today:
        errors.append(f"entry is already past (end_date {conf.end_date} < {today})")
    errors.extend(_duplicate_errors(conf, [c for cid, c in head_confs.items() if cid != new_id]))
    return errors, conf


def _norm_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = host_of(url)
    return f"{host}{parts.path.rstrip('/')}" + (f"?{parts.query}" if parts.query else "")


def _norm_title(title: str) -> str:
    return " ".join(sorted(re.findall(r"\w+", unicodedata.normalize("NFKC", title).casefold())))


def _duplicate_errors(new: Conference, existing: list[Conference]) -> list[str]:
    """Reject a new entry that repeats an existing one (past entries and placeholders included).

    The same series with a different year is a new edition and is fine, but the
    same URL, or the same title and year, never is.
    """
    errors = []
    new_year, new_stem = new.id[-4:], new.id[:-5]
    for old in existing:
        if new.url and _norm_url(new.url) == _norm_url(old.url):
            errors.append(f"duplicate of {old.id}: same url")
        elif _norm_title(new.title) == _norm_title(old.title) and new_year == old.id[-4:]:
            errors.append(f"duplicate of {old.id}: same title and year")
        elif new_stem == old.id[:-5] and new_year == old.id[-4:]:
            errors.append(f"duplicate of {old.id}: same id stem and year")
    return errors


# --------------------------------------------------------------------------
# Gate
# --------------------------------------------------------------------------

def run_gate(pr: dict, issue: dict, commits: list[tuple[str, str]], changed_files: list[str],
             base_path: str, head_path: str, trusted_logins: set[str], today: date) -> dict:
    reasons: list[str] = []
    result = {"eligible": False, "reasons": reasons, "issue_number": "", "meeting_url": "",
              "head_sha": "", "entry_id": "", "issue_comments": ""}
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    ref = head.get("ref") or ""
    result["head_sha"] = head.get("sha") or ""

    m = re.fullmatch(r"claude/issue-(\d+)-\d+", ref)
    if not m:
        reasons.append("head branch is not claude/issue-<N>-<run id>")
    if (head.get("repo") or {}).get("full_name") != (base.get("repo") or {}).get("full_name") or not base.get("repo"):
        reasons.append("head repository differs from the base repository")
    user = pr.get("user") or {}
    if user.get("login") != APP_LOGIN or user.get("type") != "Bot":
        reasons.append(f"PR author is not {APP_LOGIN}")
    if not commits:
        reasons.append("the PR has no commits")
    bad = [f"{n} <{e}>" for n, e in commits if (n, e) != (COMMIT_AUTHOR_NAME, COMMIT_AUTHOR_EMAIL)]
    if bad:
        reasons.append(f"commits not authored by {COMMIT_AUTHOR_NAME}: {'; '.join(sorted(set(bad)))}")

    branch_n = m.group(1) if m else None
    body_matches = re.findall(r"(?m)^Fixes #(\d+)\s*$", pr.get("body") or "")
    if len(body_matches) != 1:
        reasons.append("PR body must contain exactly one 'Fixes #N' line")
    body_n = body_matches[0] if len(body_matches) == 1 else None
    if branch_n and body_n and branch_n != body_n:
        reasons.append(f"issue number mismatch: branch says #{branch_n}, PR body says #{body_n}")
    n = branch_n if branch_n and branch_n == body_n else None
    if n:
        result["issue_number"] = n
        if str(issue.get("number")) != n:
            reasons.append("fetched issue number does not match")
        if "pull_request" in issue:
            reasons.append("the referenced number is a pull request, not an issue")
        assoc = issue.get("author_association")
        login = (issue.get("user") or {}).get("login") or ""
        if assoc not in TRUSTED_ASSOCIATIONS and login.lower() not in trusted_logins:
            reasons.append(
                f"issue author {login or '?'} has association {assoc}; "
                f"only {', '.join(sorted(TRUSTED_ASSOCIATIONS))} or an explicitly trusted login is accepted"
            )

    if changed_files != [DATA_FILE]:
        reasons.append(f"changed files are not exactly [{DATA_FILE}]: {changed_files}")

    fields = None
    if n:
        try:
            fields = parse_issue_body(issue.get("body") or "")
            result["meeting_url"] = fields.url
            result["issue_comments"] = fields.comments
        except CheckError as exc:
            reasons.append(f"issue body: {exc}")
    if fields is not None and changed_files == [DATA_FILE]:
        errors, conf = check_diff(base_path, head_path, fields.url, fields.comments, today)
        reasons.extend(errors)
        if conf is not None:
            result["entry_id"] = conf.id
    result["eligible"] = not reasons and bool(result["entry_id"]) and bool(result["meeting_url"])
    return result


# --------------------------------------------------------------------------
# Evidence verification
# --------------------------------------------------------------------------

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = dict.fromkeys(map(ord, "‘’‚‛′"), "'")
_QUOTES.update(dict.fromkeys(map(ord, "“”„‟″"), '"'))


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", html.unescape(value)).translate(_DASHES).translate(_QUOTES)
    return " ".join(value.split()).casefold()


def html_to_text(raw_html: str) -> str:
    return normalize_text(re.sub(r"<[^>]*>", " ", raw_html))


def quote_in_page(quote: str, raw_html: str) -> bool:
    q = normalize_text(quote)
    # A bare "30/04/2027:" is a legitimate, specific quote; anything else short is too weak.
    if len(q) < MIN_QUOTE_LEN and not (len(q) >= MIN_DATE_QUOTE_LEN and has_numeric_date(q)):
        return False
    # Whitespace-insensitive: inline tags such as <b> may or may not add a space.
    squash = lambda value: re.sub(r"\s+", "", value)
    q = squash(q)
    return q in squash(html_to_text(raw_html)) or q in squash(normalize_text(raw_html))


Fetcher = Callable[[str], tuple[str, str]]  # url -> (final_url, text)


def http_fetch(url: str, timeout: int = 30, max_bytes: int = 8_000_000) -> tuple[str, str]:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise CheckError("only http(s) URLs can be fetched")
    if not is_public_hostname(parts.hostname):
        raise CheckError("refusing to fetch an IP address, localhost or non-public host")
    ctx = None
    if (parts.hostname or "") == "astronomy.pmo.cas.cn":  # known self-signed certificate (AGENTS.md)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; conference-calendar-auto-review)",
                      "Accept": "text/html,application/json,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = resp.read(max_bytes + 1)
            charset = resp.headers.get_content_charset() or "utf-8"
            final_url = resp.geturl()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise CheckError(f"could not fetch {url}: {exc}") from exc
    if len(data) > max_bytes:
        raise CheckError(f"{url} is larger than {max_bytes} bytes")
    try:
        return final_url, data.decode(charset, errors="replace")
    except LookupError:  # unknown charset name in the response headers
        return final_url, data.decode("utf-8", errors="replace")


@dataclass
class EvidenceResult:
    ok: bool
    quotes: list[str]
    problems: list[str]
    orders: list[str | None] = field(default_factory=list)  # slash-date convention of each quote's page


class EvidenceVerifier:
    def __init__(self, allowed_urls: list[str], fetch: Fetcher = http_fetch):
        self.allowed_urls = [u for u in allowed_urls if is_public_hostname(urlsplit(u).hostname)]
        self.fetch = fetch
        self.cache: dict[str, str | CheckError] = {}
        self.verified_quotes: list[str] = []

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        return (parts.scheme in ("http", "https") and is_public_hostname(parts.hostname)
                and any(same_site_url(url, a) for a in self.allowed_urls))

    def _page(self, url: str) -> str:
        if url not in self.cache:
            try:
                final_url, text = self.fetch(url)
                if not self._allowed(final_url):
                    raise CheckError(f"{url} redirected off the meeting's site")
                self.cache[url] = text
            except CheckError as exc:
                self.cache[url] = exc
        cached = self.cache[url]
        if isinstance(cached, CheckError):
            raise cached
        return cached

    def prefetch(self, verdict: dict) -> None:
        """Fetch every page the verdict cites, so page-wide checks see all of them."""
        for item in verdict.values():
            for ev in (item.get("evidence") if isinstance(item, dict) else None) or []:
                if isinstance(ev, dict) and isinstance(ev.get("url"), str) and self._allowed(ev["url"]):
                    try:
                        self._page(ev["url"])
                    except CheckError:
                        pass

    def page_tokens(self) -> frozenset[str]:
        """Word tokens of the visible text of every official page fetched so far."""
        out: set[str] = set()
        for page in self.cache.values():
            if isinstance(page, str):
                out |= tokens(html_to_text(page))
        return frozenset(out)

    def slash_order(self, url: str) -> str | None:
        """Slash-date convention of a fetched page ("dmy", "mdy" or None when it does not say)."""
        page = self.cache.get(url)
        return slash_convention(page) if isinstance(page, str) else None

    def verify(self, evidence: object) -> EvidenceResult:
        problems: list[str] = []
        quotes: list[str] = []
        orders: list[str | None] = []
        if not isinstance(evidence, list) or not evidence:
            return EvidenceResult(False, [], ["no evidence given"], [])
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str) or not isinstance(item.get("quote"), str):
                problems.append("malformed evidence item")
                continue
            url, quote = item["url"], item["quote"]
            if not self._allowed(url):
                problems.append(f"evidence host not allowed: {host_of(url) or url}")
                continue
            try:
                page = self._page(url)
            except CheckError as exc:
                problems.append(str(exc))
                continue
            if quote_in_page(quote, page):
                quotes.append(quote)
                orders.append(self.slash_order(url))
                self.verified_quotes.append(quote)
            else:
                problems.append(f"quote not found at {url}: {quote[:60]!r}")
        return EvidenceResult(not problems, quotes, problems, orders)


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------

STOPWORDS = frozenset(
    "a an and at by de del der des die du el for from in la le les of on or the to und with y".split()
)
MONTHS = {
    1: ("january", "jan"), 2: ("february", "feb"), 3: ("march", "mar"), 4: ("april", "apr"),
    5: ("may",), 6: ("june", "jun"), 7: ("july", "jul"), 8: ("august", "aug"),
    9: ("september", "sept", "sep"), 10: ("october", "oct"), 11: ("november", "nov"), 12: ("december", "dec"),
}
SHARE_THRESHOLD = 0.6


def tokens(value: str) -> frozenset[str]:
    return frozenset(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def content_tokens(value: str) -> frozenset[str]:
    return frozenset(t for t in tokens(value) if t not in STOPWORDS)


def _year_or_ordinal(token: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)\d{2}|\d+(?:st|nd|rd|th)", token))


def title_match(a: str, b: str) -> bool:
    """Equal after dropping stopwords and year/ordinal tokens (years must not conflict), or Jaccard >= 0.8."""
    ta, tb = content_tokens(a), content_tokens(b)
    if not ta or not tb:
        return not ta and not tb
    years_a = {t for t in ta if re.fullmatch(r"(?:19|20)\d{2}", t)}
    years_b = {t for t in tb if re.fullmatch(r"(?:19|20)\d{2}", t)}
    if years_a and years_b and years_a != years_b:
        return False
    ca = {t for t in ta if not _year_or_ordinal(t)}
    cb = {t for t in tb if not _year_or_ordinal(t)}
    if ca == cb:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.8


def location_match(pr: str, reviewer: str) -> bool:
    """The PR location must cover everything the reviewer found (superset of tokens)."""
    tp, tr = content_tokens(pr), content_tokens(reviewer)
    if not tr:
        return not tp
    return tr <= tp


def digit_runs(value: str) -> set[str]:
    return {str(int(run)) for run in re.findall(r"\d+", value)}


def _share_in_quotes(value: str, quotes: list[str], *, words_only: bool = False) -> float:
    wanted = content_tokens(value)
    if words_only:
        wanted = frozenset(t for t in wanted if not any(c.isdigit() for c in t))
    if not wanted:
        return 1.0
    have = content_tokens(" ".join(normalize_text(q) for q in quotes))
    return len(wanted & have) / len(wanted)


def _iso(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if value == "":
        return ""
    try:
        return date.fromisoformat(value).isoformat() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else None
    except ValueError:
        return None


def _slash_readings(m: re.Match, slash_order: str | None) -> list[tuple[str, str, str]]:
    """Readings (y, m, d) of a/b/YYYY. Ambiguous (both <= 12, different) only with a known page convention."""
    a, b = int(m[1]), int(m[2])
    if a == b or a > 12 or slash_order == "dmy":
        return [(m[3], m[2], m[1])]
    if b > 12 or slash_order == "mdy":
        return [(m[3], m[1], m[2])]
    return []


_NUMERIC_DATES = (
    (re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)"), lambda m, so: [(m[1], m[2], m[3])]),
    (re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)"), lambda m, so: [(m[3], m[2], m[1])]),
    (re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)"), _slash_readings),
    # Same-month day range "D1-D2/M/YYYY" or "D1-D2.M.YYYY": supports exactly its two endpoints. Only the
    # day-first reading applies (the range sits on the first component, so M/D cannot be meant), and a
    # slash range is refused on a page whose slash dates are month-first; middle days are not supported.
    # Lookbehind on digits and "-" keeps it out of ISO dates and longer digit runs.
    (
        re.compile(r"(?<![\d-])(\d{1,2}) ?- ?(\d{1,2})([/.])(\d{1,2})\3(\d{4})(?!\d)"),
        lambda m, so: [] if (m[3] == "/" and so == "mdy") else [(m[5], m[4], m[1]), (m[5], m[4], m[2])],
    ),
)
_SLASH_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(?:19|20)\d{2}(?!\d)")


def has_numeric_date(text: str) -> bool:
    return any(pattern.search(text) for pattern, _ in _NUMERIC_DATES)


def slash_convention(page: str) -> str | None:
    """"dmy" / "mdy" when the page's own a/b/YYYY dates prove the order, else None (ambiguous)."""
    first_big = second_big = False
    for m in _SLASH_DATE_RE.finditer(html_to_text(page) + " " + normalize_text(page)):
        a, b = int(m[1]), int(m[2])
        if a > 31 or b > 31 or (a > 12 and b > 12):
            continue
        first_big |= a > 12
        second_big |= b > 12
    if first_big and not second_big:
        return "dmy"
    if second_big and not first_big:
        return "mdy"
    return None


_ORD = r"(?:st|nd|rd|th)?"
_NUM = r"(?<!\d)\d{1,2}" + _ORD


def _month_name_patterns(d: int, names: tuple[str, ...]) -> list[str]:
    """Day and month name adjacent ("15 March", "15th of March", "March 15", "11-15 October", "October 11-15")."""
    mon = r"(?<![a-z])(?:%s)\.?(?![a-z])" % "|".join(names)
    day = r"(?<!\d)%d%s(?!\d)" % (d, _ORD)
    rng = r"\s*-\s*"
    return [
        rf"{day}(?:{rng}{_NUM}(?!\d))?\s*(?:of\s+)?{mon}",
        rf"{_NUM}(?!\d){rng}{day}\s*(?:of\s+)?{mon}",
        rf"{mon}\s*{day}(?:{rng}{_NUM}(?!\d))?",
        rf"{mon}\s*{_NUM}(?!\d){rng}{day}",
    ]


def _chinese_patterns(mo: int, d: int) -> list[str]:
    day = r"(?<!\d)%d(?!\d)" % d
    other = r"\d{1,2}(?!\d)"
    rng = r"\s*-\s*"
    return [rf"(?<!\d){mo}\s*月\s*{day}(?:{rng}{other})?", rf"(?<!\d){mo}\s*月\s*{other}{rng}{day}"]


def quote_supports_date(quote: str, iso: str, slash_order: str | None = None) -> bool:
    """The quote must carry the full date: day, month (adjacent to the day) and the year.

    slash_order is the page's slash-date convention ("dmy"/"mdy"); None means unknown, in which
    case an ambiguous a/b/YYYY (both parts <= 12, different) supports nothing.
    """
    y, mo, d = (int(x) for x in iso.split("-"))
    q = normalize_text(quote)
    for pattern, expand in _NUMERIC_DATES:
        for m in pattern.finditer(q):
            if any(int(a) == y and int(b) == mo and int(c) == d for a, b, c in expand(m, slash_order)):
                return True
    if y not in {int(x) for x in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", q)}:
        return False
    patterns = _month_name_patterns(d, MONTHS[mo]) + _chinese_patterns(mo, d)
    return any(re.search(p, q) for p in patterns)


def _dates_supported(dates: set[str], quotes: list[str], orders: list[str | None] | None = None) -> bool:
    orders = orders if orders is not None and len(orders) == len(quotes) else [None] * len(quotes)
    return all(not d or any(quote_supports_date(q, d, o) for q, o in zip(quotes, orders)) for d in dates)


_GENERIC_LABEL_WORDS = frozenset("deadline deadlines date dates the".split())


def _stem(token: str) -> str:
    return re.sub(r"(?:ions|ion|s)$", "", token) if len(token) > 4 else token


_EARLY_BIRD_LABEL = "early-bird registration"
_EARLY_BIRD_WORDS = frozenset("early earlybird early-bird reduced discount discounted".split())


def label_supported(label: str, quotes: list[str], type_: str = "") -> bool:
    """At least half of the label's content words (suffix-normalised) occur in the field's verified quotes.

    The normalised label "Early-bird registration" (type other) is mandated by
    AGENTS.md and is not copied from the site, so it instead needs one of the
    early/reduced-rate words in the quotes.
    """
    if type_ == "other" and label.strip().casefold() == _EARLY_BIRD_LABEL:
        text = " ".join(normalize_text(q) for q in quotes)
        words = set(re.findall(r"[a-z]+(?:-[a-z]+)*", text.casefold()))
        words |= {w for word in list(words) for w in word.split("-")}
        return bool(words & _EARLY_BIRD_WORDS)
    wanted = {_stem(t) for t in content_tokens(label) if t not in _GENERIC_LABEL_WORDS}
    if not wanted:
        return True
    have = {_stem(t) for t in content_tokens(" ".join(normalize_text(q) for q in quotes))}
    return len(wanted & have) / len(wanted) >= 0.5


@dataclass
class Row:
    field: str
    pr: str
    reviewer: str
    ok: bool
    note: str = ""


def _fmt(values: object) -> str:
    if isinstance(values, (set, frozenset, list, tuple)):
        return ", ".join(sorted(str(v) for v in values)) or "(none)"
    return str(values) if values not in ("", None) else "(empty)"


def compare_verdict(conf: Conference, verdict: object, verifier: EvidenceVerifier) -> list[Row]:
    rows: list[Row] = []
    if not isinstance(verdict, dict):
        return [Row("verdict", "", "", False, "reviewer output is not a JSON object")]
    verifier.prefetch(verdict)

    def field_of(name: str) -> tuple[object, object] | None:
        item = verdict.get(name)
        if not isinstance(item, dict) or "value" not in item:
            rows.append(Row(name, "", "", False, "missing from reviewer output"))
            return None
        return item["value"], item.get("evidence")

    def finish(name: str, pr_val: object, rev_val: object, equal: bool, relied: bool, evidence: object,
               date_set: set[str] | None = None, text_for_share: str | None = None,
               page_fallback: frozenset[str] | None = None, labels: list[tuple[str, str]] | None = None,
               extra_tokens: frozenset[str] | None = None) -> None:
        pr_s, rev_s = _fmt(pr_val), _fmt(rev_val)
        if not equal:
            rows.append(Row(name, pr_s, rev_s, False, "values differ"))
            return
        if not relied:
            rows.append(Row(name, pr_s, rev_s, True, "both empty"))
            return
        res = verifier.verify(evidence)
        if not res.ok:
            rows.append(Row(name, pr_s, rev_s, False, "evidence not verified: " + "; ".join(res.problems)))
        elif date_set is not None and not _dates_supported(date_set, res.quotes, res.orders):
            rows.append(Row(name, pr_s, rev_s, False, "no verified quote carries each date's day, month and year"))
        elif (bad_label := next((l for l, t in labels or [] if not label_supported(l, res.quotes, t)), None)) is not None:
            rows.append(Row(name, pr_s, rev_s, False, f"label not supported by evidence: {bad_label!r}"))
        elif extra_tokens and not extra_tokens <= (
                tokens(" ".join(normalize_text(q) for q in res.quotes)) | verifier.page_tokens()):
            rows.append(Row(name, pr_s, rev_s, False,
                            "PR words without evidence: " + ", ".join(sorted(extra_tokens - verifier.page_tokens()))))
        elif text_for_share is not None and _share_in_quotes(text_for_share, res.quotes) < SHARE_THRESHOLD:
            if page_fallback is not None and page_fallback <= verifier.page_tokens():
                # The quotes verify but cite the wrong line; every word is on a fetched official page.
                rows.append(Row(name, pr_s, rev_s, True, f"{len(res.quotes)} quote(s) verified; all words on official pages"))
            else:
                rows.append(Row(name, pr_s, rev_s, False, "verified quotes cover too little of the value"))
        else:
            rows.append(Row(name, pr_s, rev_s, True, f"{len(res.quotes)} quote(s) verified"))

    for name, pr_val, matcher in (("title", conf.title, title_match), ("location", conf.location, location_match)):
        got = field_of(name)
        if got is None:
            continue
        rev_val, evidence = got
        if not isinstance(rev_val, str):
            rows.append(Row(name, pr_val, str(rev_val), False, "value is not a string"))
            continue
        equal = matcher(pr_val, rev_val)
        page_wide = False
        if not equal and name == "title":
            # The reviewer may legitimately omit a prefix (e.g. "IAU Symposium 414: "), provided the
            # reviewer's words are all in the PR title and every PR title word is on a fetched official page.
            tr, tp = tokens(rev_val), tokens(pr_val)
            if tr and tr <= tp:
                verifier.verify(evidence)  # make sure the cited pages are fetched
                equal = page_wide = tp <= verifier.page_tokens()
        # Page-wide token coverage is stronger than the per-quote share, so it replaces it.
        finish(name, pr_val, rev_val, equal, bool(tokens(pr_val) or tokens(rev_val)), evidence,
               text_for_share=None if page_wide else rev_val,
               page_fallback=(tokens(pr_val) | tokens(rev_val)) if name == "title" else None,
               extra_tokens=(content_tokens(pr_val) - content_tokens(rev_val)) if name == "location" else None)

    for name, pr_val in (("start_date", conf.start_date), ("end_date", conf.end_date)):
        got = field_of(name)
        if got is None:
            continue
        rev_val, evidence = got
        pr_iso = pr_val.isoformat() if pr_val else ""
        rev_iso = _iso(rev_val)
        if rev_iso is None:
            rows.append(Row(name, pr_iso, str(rev_val), False, "reviewer date is not YYYY-MM-DD"))
            continue
        finish(name, pr_iso, rev_iso, pr_iso == rev_iso, bool(pr_iso or rev_iso), evidence, {pr_iso, rev_iso} - {""})

    for name, pr_list in (("registration_deadlines", conf.registration_deadlines),
                          ("abstract_deadlines", conf.abstract_deadlines)):
        got = field_of(name)
        if got is None:
            continue
        rev_val, evidence = got
        try:
            rev_dates = {_iso(d["date"]) for d in rev_val}
            valid = isinstance(rev_val, list) and None not in rev_dates and "" not in rev_dates
        except (TypeError, KeyError):
            valid = False
        if not valid:
            rows.append(Row(name, "", str(rev_val)[:100], False, "malformed reviewer deadlines"))
            continue
        pr_dates = {d.date.isoformat() for d in pr_list}
        finish(name, pr_dates, rev_dates, pr_dates == rev_dates, bool(pr_dates or rev_dates), evidence, pr_dates | rev_dates,
               labels=[(d.label, "") for d in pr_list])

    got = field_of("other_deadlines")
    if got is not None:
        rev_val, evidence = got
        try:
            rev_set = Counter((d["type"], _iso(d["date"])) for d in rev_val)
            valid = isinstance(rev_val, list) and all(d[1] is not None for d in rev_set)
        except (TypeError, KeyError):
            valid = False
        if not valid:
            rows.append(Row("other_deadlines", "", str(rev_val)[:100], False, "malformed reviewer deadlines"))
        else:
            pr_set = Counter((d.type, d.date.isoformat() if d.date else "") for d in conf.other_deadlines)
            fmt = lambda s: [f"{t}:{d or 'undated'}" for t, d in s.elements()]
            finish("other_deadlines", fmt(pr_set), fmt(rev_set), pr_set == rev_set, bool(pr_set or rev_set), evidence,
                   {d for _, d in (pr_set + rev_set)}, labels=[(d.label, d.type) for d in conf.other_deadlines])

    for name, pr_text in (("registration_display", conf.registration_display), ("abstract_display", conf.abstract_display)):
        got = field_of(name)
        if got is None:
            continue
        rev_val, evidence = got
        if not isinstance(rev_val, str):
            rows.append(Row(name, pr_text, str(rev_val), False, "value is not a string"))
            continue
        if not pr_text.strip():
            rows.append(Row(name, "", rev_val, not rev_val.strip(),
                            "both empty" if not rev_val.strip() else "reviewer found display text the PR lacks"))
            continue
        if not rev_val.strip() or not title_match(pr_text, rev_val):
            rows.append(Row(name, pr_text, rev_val, False, "reviewer's display text is missing or differs"))
            continue
        res = verifier.verify(evidence)
        if not res.ok:
            rows.append(Row(name, pr_text, rev_val, False, "evidence not verified: " + "; ".join(res.problems)))
            continue
        missing = digit_runs(pr_text) - digit_runs(" ".join(res.quotes))
        share = _share_in_quotes(pr_text, res.quotes, words_only=True)
        if missing:
            rows.append(Row(name, pr_text, rev_val, False,
                            f"digits not in this field's verified quotes: {', '.join(sorted(missing))}"))
        elif share < SHARE_THRESHOLD:
            rows.append(Row(name, pr_text, rev_val, False, "verified quotes cover too few of the text's words"))
        else:
            rows.append(Row(name, pr_text, rev_val, True, "digits and words backed by this field's verified quotes"))
    return rows


def render_table(rows: list[Row]) -> str:
    def cell(value: str) -> str:
        value = " ".join(str(value).replace("`", "'").replace("|", "/").split())
        return f"`{value[:160]}`" if value else ""
    out = ["| Field | PR value | Reviewer value | Result |", "| --- | --- | --- | --- |"]
    for r in rows:
        mark = "pass" if r.ok else "FAIL"
        note = f" ({r.note})" if r.note else ""
        out.append(f"| {r.field} | {cell(r.pr)} | {cell(r.reviewer)} | {mark}{note.replace('|', '/')} |")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _today(value: str | None) -> date:
    return date.fromisoformat(value) if value else datetime.now(timezone.utc).date()


def _load_json(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_gate(args: argparse.Namespace) -> int:
    commits = []
    for line in Path(args.commits).read_text(encoding="utf-8").splitlines():
        if line:
            name, _, email = line.partition("\x1f")
            commits.append((name, email))
    changed = [l for l in Path(args.changed_files).read_text(encoding="utf-8").splitlines() if l]
    trusted = {t.strip().lower() for t in (args.trusted_logins or "").split(",") if t.strip()}
    try:
        result = run_gate(_load_json(args.pr), _load_json(args.issue), commits, changed,
                          args.base_data, args.head_data, trusted, _today(args.today))
    except Exception as exc:  # fail closed on anything unexpected
        result = {"eligible": False, "reasons": [f"gate crashed: {exc!r}"], "issue_number": "",
                  "meeting_url": "", "head_sha": "", "entry_id": "", "issue_comments": ""}
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["eligible"] else 1


def cmd_diff_check(args: argparse.Namespace) -> int:
    gate = _load_json(args.gate_json)
    errors, conf = check_diff(args.base_data, args.head_data, gate["meeting_url"], gate["issue_comments"], _today(args.today))
    if conf is not None and conf.id != gate["entry_id"]:
        errors.append("the added entry differs from the one that was reviewed")
    for e in errors:
        print(f"diff-check: {e}", file=sys.stderr)
    return 1 if errors else 0


def cmd_compare(args: argparse.Namespace) -> int:
    rows: list[Row]
    try:
        gate = _load_json(args.gate_json)
        conf = next((c for c in load_conferences(args.head_data) if c.id == gate["entry_id"]), None)
        if conf is None:
            raise CheckError("reviewed entry not found in the PR data")
        verdict = _load_json(args.verdict)
        verifier = EvidenceVerifier([conf.url, gate["meeting_url"]])
        rows = compare_verdict(conf, verdict, verifier)
    except (CheckError, ValidationError, OSError, ValueError) as exc:
        rows = [Row("review", "", "", False, f"comparison could not run: {exc}")]
    except Exception as exc:  # fail closed, but still leave a result table behind
        rows = [Row("review", "", "", False, f"comparison crashed: {type(exc).__name__}")]
    table = render_table(rows)
    Path(args.table_output).write_text(table, encoding="utf-8")
    print(table)
    return 0 if rows and all(r.ok for r in rows) else 1


def cmd_gate_comment(args: argparse.Namespace) -> int:
    gate = _load_json(args.gate_json)
    lines = ["Automatic review and merge was **not** performed for this PR. A human reviewer is still requested.", "",
             "Reasons:"]
    lines += [f"- `{' '.join(str(r).replace('`', chr(39)).split())[:300]}`" for r in gate.get("reasons", [])] or ["- (none recorded)"]
    print("\n".join(lines))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    g.add_argument("--pr", required=True)
    g.add_argument("--issue", required=True)
    g.add_argument("--commits", required=True)
    g.add_argument("--changed-files", required=True)
    g.add_argument("--base-data", required=True)
    g.add_argument("--head-data", required=True)
    g.add_argument("--trusted-logins", default="")
    g.add_argument("--today")
    g.add_argument("--output", required=True)
    g.set_defaults(func=cmd_gate)
    d = sub.add_parser("diff-check")
    d.add_argument("--gate-json", required=True)
    d.add_argument("--base-data", required=True)
    d.add_argument("--head-data", required=True)
    d.add_argument("--today")
    d.set_defaults(func=cmd_diff_check)
    c = sub.add_parser("compare")
    c.add_argument("--gate-json", required=True)
    c.add_argument("--head-data", required=True)
    c.add_argument("--verdict", required=True)
    c.add_argument("--table-output", required=True)
    c.set_defaults(func=cmd_compare)
    gc = sub.add_parser("gate-comment")
    gc.add_argument("--gate-json", required=True)
    gc.set_defaults(func=cmd_gate_comment)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
