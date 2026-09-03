#!/usr/bin/env python3
"""Discover supported official notices and update data/auto-jobs.json.

Supported types are recruitment, admission, answer key, result, and recruitment
corrigendum/addendum. The monitor uses only information on configured source pages,
feeds, linked HTML pages, or PDFs. Unknown fields are labelled as such instead of
being guessed. A temporary source failure is reported but does not remove alerts.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

try:
    from pypdf import PdfReader
except ImportError:  # PDF enrichment is optional for local, dependency-free runs.
    PdfReader = None

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "automation" / "sources.json"
DEFAULT_DISCOVERY_FEEDS = ROOT / "automation" / "discovery-feeds.json"
DEFAULT_OFFICIAL_ORGS = ROOT / "automation" / "official-organizations.json"
DEFAULT_OFFLINE_FORMS = ROOT / "automation" / "offline-forms.json"
DEFAULT_OFFLINE_REDIRECTS = ROOT / "data" / "offline-redirects.json"
DEFAULT_OUTPUT = ROOT / "data" / "auto-jobs.json"
DEFAULT_STATE = ROOT / "data" / "seen-notices.json"
# The external portals used to source the offline application form for offline-apply
# vacancies. Their URLs are kept out of the visible site (links are masked behind a
# client-side redirect on redirect.html); they are only used here to build that mask.
OFFLINE_FORM_HOSTS = {"onlineforms.in", "speedjob.in"}
REDIRECT_PAGE = "redirect.html"
# Recruitment automation is data-only. These paths define the visual website and
# are snapshotted/restored around every CLI run so the monitor cannot alter layout.
# The homepage layout is FROZEN for AI agents and humans alike — content-only
# updates; see AGENTS.md and tests/test_layout_order.py before editing index.html.
PROTECTED_LAYOUT_PATHS = ("index.html", "assets")
DISCOVERY_HOSTS = {"haryanajobs.in", "linkingsky.com", "punjabjobalert.com", "rozgarnews.com"}
# Job blogs / aggregators, social platforms and shorteners: an "Official Website"
# row pointing at one of these is never an official website and is never
# auto-registered as a monitor source.
NON_OFFICIAL_WEBSITE_HOSTS = {
    "freejobalert.com", "sarkariresult.com", "sarkariresult.info", "mysarkarinaukri.com",
    "dailyjobalert.in", "punjabjobalert.com", "haryanajobs.in", "linkingsky.com",
    "rozgarnews.com", "testbook.com", "adda247.com", "pw.live", "jagranjosh.com",
    "careerpower.in", "oliveboard.in", "gradeup.co", "byjus.com", "indgovtjobs.in",
    "sarkarijobfind.com", "rojgarresult.com", "sarkarialert.com",
    "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
    "t.me", "telegram.me", "whatsapp.com", "chat.whatsapp.com", "linkedin.com",
    "bit.ly", "tinyurl.com", "goo.gl",
}
# Domain endings a genuine Indian recruiting board / PSU / institute uses.
OFFICIAL_WEBSITE_DOMAIN_SUFFIXES = (
    ".gov.in", ".nic.in", ".gov", ".mil.in", ".ac.in", ".edu.in", ".res.in",
    ".org.in", ".net.in", ".co.in", ".edu", ".org", ".in",
)

DISCOVERY_BRAND_TERMS = ("haryanajobs", "haryana jobs", "punjabjobalert", "punjab job alert", "punjabjobalert.com", "rozgarnews", "rozgar news")
# Aggregator branding that must never surface in a published alert title or
# source name (the offline-form portals host the forms but are never credited).
OFFLINE_BRAND_TERMS = (
    "onlineforms.in",
    "onlineforms",
    "online forms",
    "www.speedjob.in",
    "speedjob.in",
    "speedjob",
    "speed job",
)

# Offline-apply vacancy handling (offline application forms hosted on the
# portals in OFFLINE_FORM_HOSTS).
# The external URL is masked on the website behind redirect.html so the portal's
# branding/URL is not shown to visitors; only its data file records the mapping.
OFFLINE_APPLY_MARKERS = (
    "offline application",
    "offline form",
    "apply offline",
    "offline mode",
    "application form pdf",
    "download application form",
    "applications through post",
    "send your application",
    "by post",
)
OFFLINE_APPLY_STEPS = [
    "Download the offline application form using the link below.",
    "Read the official notification for eligibility, fee, documents and the address to send the form.",
    "Fill the form, attach the required self-attested documents and a recent photograph.",
    "Send the completed application to the notified address before the last date.",
]
# Fuzzy title-match words that are too generic to identify a specific vacancy.
OFFLINE_STOPWORDS = {
    "recruitment", "recruitments", "apply", "application", "applications",
    "online", "offline", "form", "forms", "vacancy", "vacancies", "notification",
    "notifications", "invites", "invited", "post", "posts", "etc", "others",
    "and", "for", "with", "the", "in", "of", "to", "a", "an", "2026", "2025",
    "job", "jobs", "govt", "sarkari", "pdf", "download",
}
# Minimum token-overlap fraction required before an offline form is auto-attached.
OFFLINE_MATCH_MIN = 0.5
# Link labels / PDF filenames used on an offline-form portal vacancy page to find the
# direct offline application form and the official notification document.
OFFLINE_FORM_LABEL_MARKERS = (
    "application form",
    "application_form",
    "application format",
    "application_format",
    "download application",
    "proforma",
    "application form pdf",
)
OFFLINE_FORM_FILE_MARKERS = (
    "application-form",
    "application_form",
    "applicationform",
    "application-format",
    "application_format",
    "proforma",
)
OFFLINE_NOTIFICATION_LABEL_MARKERS = (
    "official notification",
    "notification",
    "advertisement",
    "advt",
    "official notice",
    "official detail",
    "official details",
    "detailed notification",
    "short notice",
)
OFFLINE_NOTIFICATION_FILE_MARKERS = (
    "notification",
    "advertisement",
    "advt",
    "official-notice",
)
# Page-text signals that a portal vacancy is genuinely offline-apply. The
# portal's own intro sentence ("...can apply through offline mode.") is the
# strongest signal; the fallback markers are article-specific rows that never
# appear in the portal's site-wide navigation.
APPLY_MODE_PHRASE_RE = re.compile(
    r"apply\s+through\s+(?:the\s+)?(online|offline)\s+mode", re.IGNORECASE
)
# Alternatives that continue an "apply through X mode" sentence
# (e.g. "...can apply through online mode or offline mode.").
APPLY_MODE_ALT_RE = re.compile(
    r"\b(?:or|and)\s+(online|offline)\s+mode", re.IGNORECASE
)
OFFLINE_ARTICLE_MARKERS = (
    "offline application form",
    "download offline form",
    "applications through post",
    "applications by post",
)
# Explicit online-apply wording used by portals that do not phrase the mode as
# "apply through online mode" (checked before the weaker offline dispatch hints
# below, because those hints also appear in a negated form on online pages).
ONLINE_ARTICLE_MARKERS = (
    "need not to be sent their filled application",
    "not required to send the filled application",
    "click here to apply online",
    "apply online link given below",
)
# Weaker offline hints: an article that tells the candidate to post a filled
# form to a recruiting address is offline-apply even without the mode sentence.
OFFLINE_DISPATCH_MARKERS = (
    "apply in prescribed application format",
    "apply in the prescribed application format",
    "send their filled application form",
    "sent their filled application form",
    "send the filled application form",
    "download link to download application form",
)
# Listing-page chrome (nav/footer links) that must never be published as an
# offline vacancy. Applied to scraped listing entries and to already-published
# offline alerts; curated registry entries (automation/offline-forms.json) are
# trusted and deliberately exempt.
OFFLINE_LISTING_JUNK_TITLES = {
    "skip to content",
    "close menu",
    "other link",
    "other links",
    "important link",
    "important links",
    "mdu date sheet",
    "date sheet",
    "work recruitment",
    "work recruitments",
    "www.onlineforms.in",
    "online form",
    "online forms",
    "online form online form",
    "latest online form",
    "latest online forms",
    "offline form",
    "offline forms",
    "latest offline form",
    "latest offline forms",
    "admit card",
    "admit cards",
    "answer key",
    "answer keys",
    "admission",
    "admissions",
    "result",
    "results",
    "home",
    "disclaimer",
    "privacy policy",
    "terms and conditions",
    "about us",
    "contact us",
    "advertise with us",
    "advertise with us!",
    "join channel",
    "join now",
    "download",
    "downloads",
    "download offline form",
    "view more",
    "read more",
    "work recruitments",
    "important links",
    "quick links",
    "syllabus",
    "previous papers",
    "login",
    "register",
    "latest job",
    "latest jobs",
    "govt jobs",
    "government jobs",
    "sarkari result",
    "telegram",
    "whatsapp",
    "join telegram",
    "join telegram channel",
    "join whatsapp",
    "join whatsapp group",
    "next post",
    "previous post",
    "leave a comment",
    "post comment",
}

USER_AGENT = (
    "Mozilla/5.0 (compatible; EmploymentExpressJobMonitor/1.0; "
    "+https://employmentexpress.github.io/homepage/)"
)
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_TEXT_LENGTH = 160_000

RECRUITMENT_TERMS = (
    "recruitment",
    "vacancy",
    "vacancies",
    "advertisement no",
    "advertisement for",
    "applications invited",
    "application invited",
    "apply online",
    "online application",
    "engagement of",
    "appointment of",
    "walk-in interview",
    "walk in interview",
    "posts of",
    "notification for",
    "career opportunity",
)
ADMISSION_TERMS = (
    "admission",
    "admissions",
    "admission notice",
    "admission notification",
    "admission form",
    "admissions open",
    "admission to class",
    "online admission",
    "selection test",
    "jnvst",
    "lateral entry admission",
    "lateral entry",
    "entrance test",
    "entrance exam",
    "counselling",
    "counseling",
    "seat allotment",
    "prospectus",
)
ANSWER_KEY_TERMS = (
    "answer key",
    "answer keys",
    "response key",
    "response keys",
    "provisional key",
    "final key",
    "master answer key",
    "tentative answer key",
    "objection tracker",
    "question paper and key",
)
RESULT_TERMS = (
    "final result",
    "written test result",
    "cbt result",
    "exam result",
    "result of",
    "result for",
    "result declared",
    "result declaration",
    "declaration of result",
    "score card",
    "scorecard",
    "cut-off",
    "cutoff",
    "merit list",
    "selection list",
    "selected candidates",
    "shortlisted candidates",
    "shortlist",
    "short listing",
    "recommendation list",
    "marks list",
    "marks scored",
    "qualified candidates",
    "provisional result",
    "result",
    "results",
    # Selection / score lists are results, never new vacancies — they must land
    # in the Results column, not the recruitment (job) column.
    "shortlisted candidate",
    "short-listed candidate",
    "short listing",
    "short-listing",
    "eligible candidate",
    "eligibility list",
    "provisionally selected",
    "provisionally shortlisted",
    "provisionally eligible",
    "list of shortlisted",
    "list of eligible",
    "list of selected",
    "candidates shortlisted",
    "candidates selected",
    "candidates called for",
    "score card list",
    "marks sheet",
    "mark sheet",
    "document verification",
    "typing test result",
    "interview result",
    "final selection",
    "panel list",
    "wait list",
    "waiting list",
)
# An exam / written-test schedule announcement is admit-card territory (it tells
# candidates when/where they appear), not a new vacancy. Kept to multi-word
# scheduling phrases so recruitment ads that merely mention a selection process
# are not misrouted; bare "exam date" is an exact cue.
ADMIT_CARD_TERMS = (
    "admit card",
    "admit cards",
    "call letter",
    "call letters",
    "hall ticket",
    "hall tickets",
    "e-call letter",
    "city intimation",
    "city intimation slip",
    "exam city slip",
    "exam city",
    "city slip",
    "roll number slip",
    "roll no slip",
    "exam date and city",
    "city status",
    "exam date",
    "exam schedule",
    "examination schedule",
    "written test date",
    "written test schedule",
    "written examination date",
    "written exam date",
    "written exam schedule",
    "cbt exam date",
    "cbt schedule",
    "exam date announced",
    "examination date announced",
    "test date announced",
    "announces exam date",
    "test scheduled",
    "date of examination",
    "date of written test",
    "exam time table",
    "exam timetable",
)
UPDATE_TERMS = ("corrigendum", "addendum")

_EXAM_SCHEDULE_RE = re.compile(
    r"(?i)(?:(?:written\s+test|written\s+examination?|online\s+test|online\s+written\s+test|"
    r"cbt|computer\s+based\s+test|exam(?:ination)?)\b[^.;|]{0,40}?"
    r"(?:date|schedule|timetable|time\s+table|reschedul\w*|postpon\w*|date\s+sheet|held\s+on|"
    r"scheduled\s+on|tentative\s+date|announc\w+))"
    r"|(?:(?:date|schedule|reschedul\w*|postpon\w*)\b[^.;|]{0,30}?"
    r"(?:written\s+test|written\s+examination?|online\s+test|cbt|exam(?:ination)?)\b)"
)


def _announces_exam_schedule(lowered: str) -> bool:
    """True when a notice announces/schedules a written test or exam date."""
    if not _EXAM_SCHEDULE_RE.search(lowered):
        return False
    # A vacancy ad merely stating "selection will be by written examination" is
    # not an exam-date announcement unless it carries a scheduling cue.
    if "recruitment" in lowered or "vacanc" in lowered:
        if not re.search(r"\b(date|schedule|reschedul|postpon|timetable|time table|held|scheduled)\b", lowered):
            return False
    return True
# Phrases used by official corrigenda/addenda when the application deadline is
# pushed back. Detection is deliberately specific so unrelated corrigenda (age,
# vacancy, syllabus changes) are not mistaken for a last-date extension.
EXTENSION_TERMS = (
    "last date extended",
    "last date has been extended",
    "last date is extended",
    "last date stands extended",
    "last date further extended",
    "extension of last date",
    "extension of the last date",
    "extension in last date",
    "extension in the last date",
    "extended up to",
    "extended till",
    "extended until",
    "extend the last date",
    "closing date extended",
    "extension of date",
    "extension of the date",
    "date of application extended",
    "date for application extended",
)
RECRUITMENT_CONTEXT_TERMS = RECRUITMENT_TERMS + (
    "advertisement",
    "advt",
    "notification",
    "application",
    "post",
    "cra ",
    "cen ",
)
EXCLUDED_TERMS = (
    "tender",
    "auction",
    "seniority list",
    "transfer order",
    "promotion order",
    "syllabus",
    "quotation",
    "eoi",
    "expression of interest",
)
DEFAULT_NOTICE_TYPES = {
    "recruitment",
    "admission",
    "answer-key",
    "result",
    "admit-card",
    "corrigendum",
}
GENERIC_TITLES = {
    "recruitment",
    "recruitments",
    "advertisement",
    "advertisements",
    "careers",
    "career",
    "apply online",
    "apply online now",
    "apply online (recruitment portal)",
    "recruitment portal",
    "how to apply",
    "how to apply online",
    "click here",
    "read more",
    "view more",
    "notification",
    "notifications",
}
# Advertisement-number captures that are table headings, not real advt ids.
INVALID_ADVT_NUMBERS = {
    "DATE",
    "TITLE",
    "NO",
    "NUMBER",
    "ADVT",
    "ADVT.",
    "NOTIFICATION",
    "SEE",
    "POST",
    "POSTS",
    "NAME",
    "S",
    "SR",
    "SNO",
    "SN",
}
# Labels that introduce an application deadline on official pages and listing titles.
LAST_DATE_LABELS = (
    r"last\s+date(?:\s+for\s+(?:submission|application|receipt|registration))?"
    r"|closing\s+date"
    r"|closure\s+date"
    r"|applications?\s+close"
    r"|on\s+or\s+before"
    r"|upto"
    r"|up\s+to"
)
PLACEHOLDER_DETAILS = {
    "",
    "see notification",
    "see official notification",
    "see official notice",
    "newly published",
    "as notified",
    "active / live",
}
MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
DATE_TOKEN = (
    r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|"
    r"Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*,?\s*\d{4})"
)


@dataclass(frozen=True)
class Download:
    url: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class Candidate:
    title: str
    url: str
    summary: str = ""
    published_at: str = ""
    # Date printed next to the notice on its source page (dd-mm-YYYY), when the
    # page publishes one. Used for the notice's displayed publication date.
    notice_date: str = ""


class NoticeHTMLParser(HTMLParser):
    """Small, forgiving HTML extractor for links, metadata, and visible text."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        # Anchor labels exactly as written on the page (before generic labels
        # such as "Click here for ..." are rewritten from surrounding context).
        self.raw_links: list[tuple[str, str]] = []
        # Table rows, so notice tables that keep the description in one cell and
        # the download links in another can be read as a single notice.
        self.rows: list[dict[str, Any]] = []
        self.page_title = ""
        self.description = ""
        self.visible_parts: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []
        self._anchor_context: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._hidden_depth = 0
        self._row: dict[str, Any] | None = None
        self._cell_parts: list[str] | None = None
        self._cell_plain_parts: list[str] = []
        self._cell_links = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1
        if tag == "base" and values.get("href"):
            self.base_url = urllib.parse.urljoin(self.base_url, values["href"])
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (values.get("name") or values.get("property") or "").lower()
            if key in {"description", "og:description"} and not self.description:
                self.description = clean_text(values.get("content", ""))
        elif tag == "a" and values.get("href"):
            self._anchor_href = urllib.parse.urljoin(self.base_url, values["href"])
            self._anchor_parts = [values.get("title", ""), values.get("aria-label", "")]
            self._anchor_context = self.visible_parts[-4:]
        elif tag == "img" and self._anchor_href:
            self._anchor_parts.extend([values.get("alt", ""), values.get("title", "")])
        elif tag == "tr":
            self._row = {"cells": [], "links": []}
        elif tag in {"td", "th"}:
            if self._row is None:
                self._row = {"cells": [], "links": []}
            self._cell_parts = []
            self._cell_plain_parts = []
            self._cell_links = 0

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._hidden_depth:
            self._hidden_depth -= 1
        elif tag == "title":
            self._in_title = False
            self.page_title = clean_text(" ".join(self._title_parts))
        elif tag == "a" and self._anchor_href:
            raw_title = clean_text(" ".join(self._anchor_parts))
            title = raw_title
            if re.fullmatch(r"(?i)(?:click here(?:\s+(?:to|for).*)?|download|view|open)(?:\s+now)?", raw_title):
                contextual_title = clean_text(" ".join(self._anchor_context[-3:]))
                if contextual_title:
                    title = contextual_title
            self.links.append((self._anchor_href, title))
            self.raw_links.append((self._anchor_href, raw_title))
            if self._row is not None:
                self._row["links"].append((self._anchor_href, title))
                self._cell_links += 1
            self._anchor_href = None
            self._anchor_parts = []
            self._anchor_context = []
        elif tag in {"td", "th"}:
            if self._row is not None and self._cell_parts is not None:
                self._row["cells"].append({
                    "text": clean_text(" ".join(self._cell_parts)),
                    # Text outside anchors only: a download column is mostly link
                    # labels, so this stays (near) empty for it and the real
                    # subject cell wins when picking the notice title.
                    "plainText": clean_text(" ".join(self._cell_plain_parts)),
                    "links": self._cell_links,
                })
            self._cell_parts = None
            self._cell_plain_parts = []
            self._cell_links = 0
        elif tag == "tr":
            if self._row is not None and self._row["cells"]:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if not self._hidden_depth:
            text = clean_text(data)
            if text:
                self.visible_parts.append(text)
                if self._anchor_href:
                    self._anchor_parts.append(text)
                if self._cell_parts is not None:
                    self._cell_parts.append(text)
                    if not self._anchor_href:
                        self._cell_plain_parts.append(text)

    @property
    def text(self) -> str:
        return clean_text(" ".join(self.visible_parts))[:MAX_TEXT_LENGTH]


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# A bare website address must never be used as a recruiting authority/department
# or left as the headline ("sbi.gov.in announced result" / "iitbhu.ac.in vacancy").
# A token counts as a domain only when it ends in a recognised Indian suffix
# (".gov.in", ".ac.in" ...), a non-Indian gTLD (".com" ...) or a ".in" host that is
# preceded by at least one label, so ordinary words ("Portal)") and year tails
# ("2026)") can never match.
_DOMAIN_NAME = (
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
)
WEBSITE_DOMAIN_RE = re.compile(
    r"(?i)(?:https?://)?(?:www\.)?"
    r"(?:" + _DOMAIN_NAME + r"\.(?:gov\.in|nic\.in|ac\.in|res\.in|edu\.in|org\.in|net\.in|co\.in|mil\.in|gov|ac|edu|org|net|com)(?![a-z])"
    r"|" + _DOMAIN_NAME + r"\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)?in(?![a-z]))"
    r"(?:[/?#][^\s]*)?"
)


def is_website_domain(value: Any) -> bool:
    """True when the whole value is just a website address (a URL or domain)."""
    text = clean_text(value).strip(" .,:;–-|()[]{}\"'").lower()
    if not text:
        return False
    if WEBSITE_DOMAIN_RE.fullmatch(text):
        return True
    match = re.fullmatch(r"(?:https?://)?(?:www\.)?\S+", text)
    if not match or "." not in text:
        return False
    host = re.sub(r"^https?://", "", text).split("/", 1)[0]
    return bool(re.search(r"\.[a-z]{2,}(?:\.[a-z]{2})?$", host))


def strip_website_domains(value: Any) -> str:
    """Remove website URLs/domains from a title or department name."""
    text = WEBSITE_DOMAIN_RE.sub(" ", clean_text(value))
    # Collapse whitespace and trim separators, but keep brackets intact (removing
    # them would corrupt titles such as "(Advt No. 03/2026)").
    text = re.sub(r"\s+", " ", text).strip(" .,:;–-|'\"")
    return text


# Official recruiting hosts whose feed name is just the domain. Map the host to
# the real authority name so a department is never published as a website link.
HOST_ORGANIZATION_NAMES = {
    "sbi.bank.in": "State Bank of India (SBI)",
    "uco.bank.in": "UCO Bank",
    # Every *.ibps.in portal (www.ibps.in, ibpsonline.ibps.in, ibpsreg.ibps.in)
    # belongs to the same board; the registry link for it used to be a bare
    # domain, which is what let a row label become a published department.
    "ibps.in": "Institute of Banking Personnel Selection (IBPS)",
    "iob.bank.in": "Indian Overseas Bank (IOB)",
    "iitbhu.ac.in": "Indian Institute of Technology (BHU), Varanasi",
    "hau.ac.in": "Chaudhary Charan Singh Haryana Agricultural University (HAU), Hisar",
    "bceceboard.bihar.gov.in": "Bihar Combined Entrance Competitive Examination Board (BCECEB)",
}


def organization_from_host(url_or_host: str) -> str:
    """Resolve a bare official host to its authority name, or '' when unknown."""
    host = host_name(url_or_host) or clean_text(url_or_host).lower()
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if host in HOST_ORGANIZATION_NAMES:
        return HOST_ORGANIZATION_NAMES[host]
    for known, name in HOST_ORGANIZATION_NAMES.items():
        if host.endswith("." + known) or host == known:
            return name
    return ""


def department_from_url(url: str) -> str:
    """Authority name for a source whose department is a bare domain, else ''."""
    resolved = organization_from_host(url)
    return resolved if is_specific_department(resolved) else ""


def clean_title(value: str) -> str:
    title = strip_website_domains(clean_text(value))
    # Strip "NEW" badges ("NEW Advertisement", "!! NEW !!") but never the word
    # inside a place name such as "New Delhi" or "New Town".
    title = re.sub(
        r"(?i)(?:!!\s*)?\bnew\b(?:\s*!!)?(?=\s+(?:advertisement|advt\.?|notification|recruitment|vacancy|update|result|job|opening)\b)",
        " ",
        title,
    )
    title = re.sub(r"(?i)!!\s*new\s*!!", " ", title)
    title = re.sub(
        r"(?i)^\s*(?:click here(?:\s+(?:to|for))?|download)\s*[-:–—]*\s*",
        "",
        title,
    )
    title = re.sub(r"\s+", " ", title).strip(" -|:–—")
    return title[:240]


# A recruiting authority is required for every published vacancy. These labels
# describe a feed or a link collection, not the department that owns a vacancy.
GENERIC_RECRUITING_DEPARTMENTS = {
    "official offline recruitment notices",
    "official recruitment notice",
    "official recruitment notices",
    "official recruitment website",
    "official website",
    "recruitment notice",
    "recruitment notices",
    "additional job notification source",
}

# Role words used only as a fallback when an offline listing gives a combined
# "Department + Posts" row but does not expose the department in a separate
# machine-readable field. The text before the first role is the authority name.
OFFLINE_ROLE_START_RE = re.compile(
    r"(?i)\b(?:\d+\s*[–—-]\s*)?(?:assistant\s+professor|accounts?\s+assistant|"
    r"branch\s+manager|civilian\s+motor\s+driver|computer\s+operator|data\s+entry\s+operator|"
    r"female\s+supervisor|head\s+clerk|junior\s+engineer|lab\s+assistant|library\s+attendant|"
    r"lift\s+operator|lower\s+division\s+clerk|multi[ -]?tasking\s+staff|senior\s+field\s+officer|"
    r"social\s+worker|stenographer|teaching\s+and\s+non[ -]?teaching|technical\s+and\s+non[ -]?technical|"
    r"agniveervayu|apprentice|clerk|cook|deo|dfo|driver|fireman|instructor|ldc|mts|peon|"
    r"safaiwala|soldier|steno|teacher|technician|tradesman|tgt|pgt|prt|udc)\b"
)


# Portal furniture that appears in a listing cell where a name should be:
# the "View"/"Click here"/"Download" link label, sometimes glued to the row's
# date ("View 22 Oct 2025"). No recruiting authority is ever named this way.
LINK_LABEL_WORDS = (
    r"(?:view|read|click(?:\s+here)?|download|apply|visit|register|log\s?in|more|here|check)"
)
LINK_LABEL_NOISE_RE = re.compile(rf"(?i)^\s*{LINK_LABEL_WORDS}\b(?:\s*[-:–—]\s*)?")
# A listing row's date in the shapes official portals print: 22/10/2025,
# 22 Oct 2025, Oct 22, 2025.
DATE_TOKEN = (
    r"\b\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{2,4}\b"                  # 22/10/2025
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?\s+\d{4}\b"         # 22 Oct 2025
    r"|\b[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b"        # Oct 22, 2025
)
LISTING_DATE_RE = re.compile(rf"(?i)(?:{DATE_TOKEN})")
LEADING_DATE_RE = re.compile(rf"(?i)^(?:on\s+|dated\s+)?(?:{DATE_TOKEN})\s*")


def strip_link_label_noise(value: str) -> str:
    """Drop a link label glued to its row date from a listing cell text.

    ``"View 22 Oct 2025 RECRUITMENT OF LOCAL BANK OFFICER (LBO) 2025-26"`` is a
    listing row: ``View`` is the Documents-column link and ``22 Oct 2025`` is the
    row date glued in front of the notice name. Both must come off before the
    text is used as a title. The verb is only treated as portal furniture when
    a date follows it, so a real notice name that happens to open with a word
    like "View of Public Notice..." is left alone. Titles keep more of the
    board's own wording than departments do, since only a label glued to its
    row date counts as furniture here.
    """
    text = clean_text(value)
    changed = True
    while changed and text:
        changed = False
        match = re.match(rf"(?i)^\s*(?:{LINK_LABEL_WORDS})\b[\s:–—,-]*", text)
        if match and LEADING_DATE_RE.match(text[match.end():]):
            text = clean_text(text[match.end():])
            changed = True
        match = LEADING_DATE_RE.match(text)
        if match:
            text = clean_text(text[match.end():]).strip(" -:–—|,.")
            changed = True
    return text


def is_link_label_noise(value: str) -> bool:
    """True when the text is only a link label and/or a date, never a name."""
    text = clean_text(value).strip(" .,:;|-–—")
    if not text:
        return True
    without_dates = clean_text(LISTING_DATE_RE.sub(" ", text))
    if not without_dates or without_dates.lower().strip(" .,:;|-–—") in {
        "view", "click here", "click", "download", "read more", "more", "here",
    }:
        return True
    return bool(LINK_LABEL_NOISE_RE.match(text))


def is_specific_department(value: str) -> bool:
    department = clean_text(value)
    if is_website_domain(department):
        # A website address (e.g. "sbi.gov.in") is never a recruiting authority.
        return False
    if is_link_label_noise(department):
        # "View 22 Oct 2025" is a listing row label, not an authority name.
        return False
    return bool(
        len(department) >= 3
        and department.lower().strip(" .:-–—") not in GENERIC_RECRUITING_DEPARTMENTS
    )


def sanitize_department(value: Any) -> str:
    """Return a usable authority name, stripping any website address.

    When only a domain was present the result is empty so callers fall back to
    title inference / host resolution instead of publishing a link as department.
    """
    department = strip_website_domains(value)
    return department if is_specific_department(department) else ""


def is_junk_job_title(value: str) -> bool:
    title = clean_title(value).lower().strip(" .:-–—")
    if (
        not title
        or title in GENERIC_TITLES
        or title in OFFLINE_LISTING_JUNK_TITLES
        or re.fullmatch(r"(?:other|important|quick|useful)\s+links?", title)
    ):
        return True
    # Already-prefixed titles such as "Board — Apply Online (Recruitment Portal)".
    parts = re.split(r"\s+[—–-]\s+", title, maxsplit=1)
    if len(parts) == 2:
        subject = parts[1].strip(" .:-–—")
        if subject in GENERIC_TITLES or subject in OFFLINE_LISTING_JUNK_TITLES:
            return True
    return False


def infer_recruiting_department(title: str) -> str:
    """Best-effort authority name for a combined offline-listing headline.

    Official source metadata or the article's ``Department / Organization`` row
    always wins. This fallback is intentionally conservative: if it cannot find
    a meaningful authority, the vacancy is not published under a generic feed
    name.
    """
    subject = clean_title(title)
    if is_junk_job_title(subject):
        return ""
    recruitment = re.search(r"(?i)\s+recruitment\b", subject)
    if recruitment:
        candidate = subject[: recruitment.start()]
    else:
        role = OFFLINE_ROLE_START_RE.search(subject)
        candidate = subject[: role.start()] if role else ""
    candidate = re.sub(r"(?i)\s+(?:apply|offline|online)\s*$", "", candidate)
    candidate = clean_text(candidate).strip(" ,;|:-–—")
    if len(candidate) < 3 or candidate.lower() in {
        "application", "application form", "job", "jobs", "recruitment"
    }:
        return ""
    return candidate[:180]


def _department_aliases(department: str) -> list[str]:
    authority = clean_text(department)
    aliases = [authority]
    aliases.extend(re.findall(r"\(([A-Z][A-Z0-9&./ -]{1,20})\)", authority))
    without_parenthetical = clean_text(re.sub(r"\s*\([^)]*\)", "", authority))
    if len(without_parenthetical) >= 4:
        aliases.append(without_parenthetical)
    # A readable leading name is useful for removing an already-present short
    # form before the full official department name is prefixed.
    leading = re.split(r"\s+(?:[-–—]|,\s*(?:Amritsar|Bathinda|Chandigarh|Delhi|Ludhiana|Patiala))\b", without_parenthetical, maxsplit=1)[0]
    if len(leading) >= 4:
        aliases.append(leading)
    return list(dict.fromkeys(alias for alias in aliases if len(alias) >= 3))


def title_mentions_department(title: str, department: str) -> bool:
    """A title satisfies the rule only when it carries the full authority name."""
    lowered = clean_text(title).lower()
    authority = clean_text(department).lower()
    return bool(
        authority
        and re.search(rf"(?<![a-z0-9]){re.escape(authority)}(?![a-z0-9])", lowered)
    )


def official_job_title(title: str, department: str) -> str:
    """Return a specific vacancy title that visibly names its authority."""
    subject = strip_link_label_noise(clean_title(title))
    authority = clean_text(department)
    if is_junk_job_title(subject) or not is_specific_department(authority):
        return ""

    # Action-only labels are links, not vacancy names. Keep the actual post and
    # rewrite it as a recruitment subject before adding the authority.
    generic_application = re.fullmatch(
        r"(?i)applications?(?:\s+forms?)?\s+(?:are\s+invited\s+)?for\s+(?:the\s+)?(?:posts?\s+of\s+)?(.+)",
        subject,
    )
    if generic_application:
        post_name = clean_text(generic_application.group(1)).strip(" .:-–—")
        subject = f"{post_name} Recruitment"

    if title_mentions_department(subject, authority):
        return subject[:240]
    # If the headline starts with only an acronym/short name, remove that short
    # form before prefixing the complete official authority (avoids
    # "... (PSSSB) — PSSSB Clerk ..." while retaining the full name).
    for alias in sorted(_department_aliases(authority)[1:], key=len, reverse=True):
        shortened = re.sub(
            rf"(?i)^\s*{re.escape(alias)}\s*[,|:–—-]*\s*", "", subject, count=1
        )
        if shortened != subject and clean_text(shortened):
            subject = clean_text(shortened)
            break
    return f"{authority} — {subject}"[:240]


def canonical_url(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned or cleaned.lower().endswith("undefined") or "/undefined" in cleaned.lower():
        return ""
    try:
        parsed = urllib.parse.urlsplit(cleaned)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.path.lower().endswith("/undefined") or parsed.path.lower() == "/undefined":
        return ""
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if not k.lower().startswith("utm_")]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, urllib.parse.urlencode(query), "")
    )


def host_name(url: str) -> str:
    return urllib.parse.urlsplit(canonical_url(url) or url).netloc.lower().removeprefix("www.")


def is_generic_homepage(url: str) -> bool:
    """True for a site root such as https://example.gov.in/ — never a notice/apply URL."""
    parsed = urllib.parse.urlsplit(canonical_url(url) or "")
    if not parsed.netloc:
        return False
    path = parsed.path.rstrip("/") or "/"
    return path == "/" and not parsed.query


def is_placeholder_detail(value: Any) -> bool:
    text = clean_text(value).lower().strip(" .:-–—")
    return text in PLACEHOLDER_DETAILS or text.startswith("published ")


def is_direct_pdf_url(url: str) -> bool:
    path = urllib.parse.urlsplit(canonical_url(url) or url).path.lower()
    return path.endswith(".pdf")


def is_discovery_host(url: str) -> bool:
    return host_name(url) in DISCOVERY_HOSTS


def strip_discovery_branding(value: str) -> str:
    text = clean_text(value)
    for term in DISCOVERY_BRAND_TERMS + OFFLINE_BRAND_TERMS:
        text = re.sub(rf"(?i)\b{re.escape(term)}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -|:–—")


def fingerprint(candidate: Candidate) -> str:
    material = f"{canonical_url(candidate.url)}\n{clean_title(candidate.title).lower()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _download_direct(url: str, timeout: int) -> Download:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/atom+xml,application/pdf;q=0.9,*/*;q=0.5",
            "Accept-Language": "en-IN,en;q=0.8",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"response is larger than {MAX_DOWNLOAD_BYTES} bytes")
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"response is larger than {MAX_DOWNLOAD_BYTES} bytes")
        return Download(
            url=response.geturl(),
            content_type=(response.headers.get_content_type() or "").lower(),
            data=data,
        )


# Read-only text mirrors used only when a source refuses direct connections
# (for example a firewall that drops datacenter IPs mid-TLS-handshake). They
# relay the exact public page content; the parsed result is always attributed
# to the original official URL, never to the mirror.
#
# Reconnected 2026-09-03. The previous chain could not fetch anything at all,
# which is why 32 of 66 monitored sources sat at `consecutiveFailures: 24` in
# data/seen-notices.json with "mirror fetch failed: HTTP Error 422":
#
#   * api.allorigins.win — dropped. It returned a service-wide Cloudflare
#     522 (/raw) and 520 (/get) for every URL, verified even against
#     https://www.google.com/, so it was pure dead weight on every run.
#   * r.jina.ai — kept, but driven with the documented reader headers. Its
#     default browser engine waits for `networkidle` and gives up after 15s,
#     answering HTTP 422 (`status: 42206`) for the slow *.gov.in notice pages
#     (sssb.punjab.gov.in and jkssb.nic.in both reproduced it). The first
#     attempt therefore uses `X-Engine: curl` — a plain HTTP fetch with no JS
#     and no networkidle wait, which is what these static notice tables need —
#     and only the second attempt spends time on the browser engine, with an
#     explicit `X-Timeout` so it is not cut off at 15s.
#   * web.archive.org — added as a last resort, freshness-guarded. A mirror is
#     transport only and never a source of truth, and Wayback happily serves a
#     capture from a year ago (sssb.punjab.gov.in resolved to 29 Aug 2025), so
#     a capture older than WAYBACK_MAX_CAPTURE_AGE_DAYS is rejected rather than
#     published as a fresh notice. `id_` returns the ORIGINAL archived bytes,
#     so hrefs inside stay official URLs instead of /web/... mirror links.
WAYBACK_MAX_CAPTURE_AGE_DAYS = 21


@dataclass(frozen=True)
class MirrorSpec:
    template: str
    headers: tuple[tuple[str, str], ...] = ()
    timeout: int = 30
    max_capture_age_days: int | None = None


SOURCE_MIRRORS = (
    MirrorSpec(
        template="https://r.jina.ai/{url}",
        headers=(
            ("X-Engine", "curl"),
            ("X-Timeout", "25"),
            ("X-Respond-With", "html"),
        ),
        timeout=35,
    ),
    MirrorSpec(
        template="https://r.jina.ai/{url}",
        headers=(
            ("X-Engine", "browser"),
            ("X-Timeout", "40"),
            ("X-Respond-With", "html"),
        ),
        timeout=50,
    ),
    MirrorSpec(
        template="https://web.archive.org/web/{wayback_stamp}id_/{url}",
        timeout=30,
        max_capture_age_days=WAYBACK_MAX_CAPTURE_AGE_DAYS,
    ),
)


def _wayback_capture_age_days(resolved_url: str, now: datetime | None = None) -> float | None:
    """Age in days of a Wayback capture, read off the URL it resolved to.

    Returns None when the resolved URL carries no 14-digit capture stamp, i.e.
    the page was never archived and Wayback served its "not in archive" page.
    """
    match = re.search(r"/web/(\d{14})", resolved_url or "")
    if not match:
        return None
    try:
        captured = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    reference = now or datetime.now(timezone.utc)
    return (reference - captured).total_seconds() / 86400.0


def _download_via_mirror(url: str, timeout: int) -> Download:
    last_error: Exception | None = None
    attempts: list[str] = []
    for spec in SOURCE_MIRRORS:
        mirror_url = spec.template.format(
            quoted=urllib.parse.quote(url, safe=""),
            url=url,
            wayback_stamp=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        )
        try:
            request = urllib.request.Request(
                mirror_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
                    "Accept-Language": "en-IN,en;q=0.8",
                    **dict(spec.headers),
                },
            )
            with urllib.request.urlopen(request, timeout=max(timeout, spec.timeout)) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise ValueError(f"response is larger than {MAX_DOWNLOAD_BYTES} bytes")
                if response.status != 200 or len(data) < 256:
                    raise ValueError("mirror returned an unusable response")
                if spec.max_capture_age_days is not None:
                    age = _wayback_capture_age_days(response.geturl())
                    if age is None:
                        raise ValueError("archive has no capture for this URL")
                    if age > spec.max_capture_age_days:
                        raise ValueError(
                            f"archived capture is {age:.0f} day(s) old "
                            f"(limit {spec.max_capture_age_days})"
                        )
                return Download(
                    # Keep the OFFICIAL url so every downstream link/fingerprint
                    # continues to point at the source, not at the mirror.
                    url=url,
                    content_type=(response.headers.get_content_type() or "").lower(),
                    data=data,
                )
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
            attempts.append(f"{type(exc).__name__}: {exc}")
    # Name every mirror that was tried: sourceHealth stores this string, so a
    # future reader can tell "the archive was too stale" apart from "the reader
    # refused the site" without re-running the fetch.
    detail = " | ".join(attempts)
    suffix = f" [{detail}]" if attempts else ""
    raise RuntimeError(f"mirror fetch failed: {last_error}{suffix}")


def _should_try_mirror(error: Exception | None) -> bool:
    """Only connection-level/refusal errors justify a mirror fetch.

    A 404/410 means the notice page is genuinely gone — a mirror would serve
    the same emptiness. Refusals (TLS handshake kills, resets, timeouts, 403
    WAF blocks, 5xx) may succeed from a different network path.
    """
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (403, 408, 425, 429) or error.code >= 500
    if isinstance(error, (OSError, urllib.error.URLError)):
        return True
    return False


def fetch_url(url: str, timeout: int = 25, retries: int = 2, proxy_fallback: bool = False) -> Download:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return _download_direct(url, timeout)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.2 * (attempt + 1))
    if proxy_fallback and _should_try_mirror(last_error):
        try:
            download = _download_via_mirror(url, timeout)
            print(f"  Fetched via mirror after direct failure: {url}", file=sys.stderr)
            return download
        except (OSError, ValueError, urllib.error.URLError, RuntimeError) as exc:
            last_error = exc
    raise RuntimeError(str(last_error or "download failed"))


def decode_document(download: Download) -> str:
    for encoding in ("utf-8", "utf-16", "windows-1252", "latin-1"):
        try:
            return download.data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return download.data.decode("utf-8", errors="replace")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element: ET.Element, names: Iterable[str]) -> str:
    wanted = {name.lower() for name in names}
    for child in element.iter():
        if local_name(child.tag) in wanted:
            value = clean_text(" ".join(child.itertext()))
            if value:
                return value
    return ""


def parse_feed(text: str, base_url: str) -> list[Candidate]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    root_name = local_name(root.tag)
    if root_name not in {"rss", "feed", "rdf"}:
        return []

    entries = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    candidates: list[Candidate] = []
    for entry in entries:
        title = child_text(entry, {"title"})
        summary = child_text(entry, {"description", "summary", "content", "encoded"})
        summary = strip_markup(summary)
        published = child_text(entry, {"pubdate", "published", "updated", "date"})
        link = ""
        for node in entry.iter():
            if local_name(node.tag) != "link":
                continue
            href = node.attrib.get("href", "")
            relation = node.attrib.get("rel", "alternate")
            if href and relation in {"alternate", ""}:
                link = href
                break
            if clean_text(node.text):
                link = clean_text(node.text)
                break
        link = canonical_url(urllib.parse.urljoin(base_url, link))
        if title and link:
            candidates.append(Candidate(clean_title(title), link, summary[:1200], parse_published(published)))
    return candidates


def strip_markup(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", value or ""))


# Labels used by notice tables for the file links themselves. They describe the
# attachment, not the notice, so a row is preferred over these as the title.
ATTACHMENT_LABELS = (
    "advertisement",
    "advertisement notice",
    "advt",
    "notice",
    "notification",
    "application form",
    "google form link",
    "google form",
    "form link",
    "apply link",
    "application fee",
    "application fee link",
    "online payment link",
    "payment link",
    "detail",
    "details",
    "pdf",
    "english",
    "hindi",
    "punjabi",
)
# Link labels inside a notice row that point at the notice itself rather than at
# a helper resource (fee payment, blank form, Google Form, etc.).
PRIMARY_ATTACHMENT_PATTERN = re.compile(
    r"(?i)\b(?:advertisement|advt|notification|notice|corrigendum|addendum|"
    r"result|answer\s*key|merit\s*list|shortlisted|detailed?)\b"
)
HELPER_ATTACHMENT_PATTERN = re.compile(
    r"(?i)\b(?:google\s*form|form\s*link|application\s*fee|fee\s*link|"
    r"payment|onlinesbi|sbicollect|apply\s*online)\b"
)


def _is_attachment_label(title: str) -> bool:
    normalised = clean_text(title).lower().strip(" .:-–—")
    normalised = re.sub(r"^\d+\s*[).:-]?\s*", "", normalised)
    return normalised in ATTACHMENT_LABELS or len(normalised) < 8


def _row_notice_title(row: dict[str, Any]) -> str:
    """Longest descriptive subject in a notice-table row.

    Most boards print the subject as plain text and keep attachment links in a
    separate download column. Some official tables (including Chandigarh
    Administration Public Notices) put the complete subject inside the PDF
    anchor itself and leave no plain-text subject cell. In that layout the
    longest non-attachment link label is the notice title, not the shorter
    department column.
    """
    best = ""
    for cell in row.get("cells", []):
        # A download column carries its text inside the anchors, so judging cells by
        # their non-anchor text keeps the notice subject from losing to a long list
        # of file labels.
        text = clean_text(cell.get("plainText", "")) if cell.get("links") else clean_text(cell.get("text", ""))
        text = re.sub(r"^\s*\d+\s*[).:-]\s*", "", text).strip(" ,;|")
        if not text or _is_attachment_label(text):
            continue
        if re.fullmatch(r"(?i)[\d\s./-]*", text) or parse_date_token(text):
            continue
        if len(text) > len(best):
            best = text
    # Discovery-feed tables often put the recruiting organisation in an anchor
    # and the actual post name in a neighbouring plain-text cell. Do not let the
    # longer organisation label replace the post name (which made LinkingSky
    # rows look like bare department names and caused every row to be skipped).
    linked_titles = [
        clean_title(label)
        for _, label in row.get("links", [])
        if not _is_attachment_label(label)
        and not is_junk_job_title(label)
        and len(clean_title(label)) >= 8
    ]
    if best and linked_titles:
        different = [label for label in linked_titles if label.lower() != best.lower()]
        if different:
            best = f"{different[0]} — {best}"
    else:
        for linked_title in linked_titles:
            if len(linked_title) > len(best):
                best = linked_title
    return clean_title(best)


def _row_notice_date(row: dict[str, Any]) -> str:
    for cell in row.get("cells", []):
        parsed = parse_date_token(clean_text(cell.get("text", "")))
        if parsed:
            return parsed
    return ""


def _row_primary_link(row: dict[str, Any]) -> str:
    """Pick the link in a row that represents the notice document itself."""
    fallback = ""
    for url, label in row.get("links", []):
        safe = canonical_url(url)
        if not safe or HELPER_ATTACHMENT_PATTERN.search(label or ""):
            continue
        is_pdf = urllib.parse.urlsplit(safe).path.lower().endswith(".pdf")
        if PRIMARY_ATTACHMENT_PATTERN.search(label or "") and is_pdf:
            return safe
        if is_pdf and not fallback:
            fallback = safe
    return fallback


def table_row_candidates(parser: NoticeHTMLParser) -> tuple[list[Candidate], set[str]]:
    """Read notice tables where one row = one notice with several file links.

    Returns the row notices plus every URL they already account for, so the same
    files are not published a second time under their bare attachment labels.
    """
    candidates: list[Candidate] = []
    claimed: set[str] = set()
    for row in parser.rows:
        title = _row_notice_title(row)
        if len(title) < 12 or not row.get("links"):
            continue
        url = _row_primary_link(row)
        if not url:
            continue
        # Link labels ("Google Form Link", "Application Fee") describe attachments,
        # not the notice, so they are deliberately kept out of the summary used for
        # classification and keyword filtering.
        candidates.append(Candidate(title, url, "", "", _row_notice_date(row)))
        claimed.update(
            canonical_url(link) for link, _ in row.get("links", []) if canonical_url(link)
        )
    return candidates, claimed


def parse_html(text: str, base_url: str) -> tuple[list[Candidate], NoticeHTMLParser]:
    parser = NoticeHTMLParser(base_url)
    parser.feed(text)
    # Every link inside a parsed notice row is already represented by that row, so it
    # must not be published again under its bare attachment label ("Advertisement",
    # "Application Form", "Google Form Link", ...).
    row_candidates, claimed_urls = table_row_candidates(parser)
    candidates = list(row_candidates)
    candidates.extend(
        Candidate(clean_title(title), canonical_url(url))
        for url, title in parser.links
        if canonical_url(url) and clean_title(title) and canonical_url(url) not in claimed_urls
    )
    return candidates, parser


def source_candidates(download: Download) -> list[Candidate]:
    text = decode_document(download)
    feed_items = parse_feed(text, download.url)
    if feed_items:
        return feed_items
    html_items, _ = parse_html(text, download.url)
    return html_items


# ---------------------------------------------------------------------------
# Page-source rule (mandatory, runs on every workflow run)
#
# After checking an official website listing, if no new job notification is
# found, the monitor re-reads the RAW page source of that official website and
# publishes only links found there. The rule applies automatically to every
# official website link in automation/sources.json,
# automation/official-organizations.json and data/notification-source-links.json
# (existing or added later) — no extra configuration is needed.
# ---------------------------------------------------------------------------
# Attribute names that may carry a notice URL even when the visible listing
# parser misses them: <noscript> fallback blocks, <iframe>/<embed>/<object>
# embeds, image maps (<area>), JavaScript-generated links and data-* hooks.
PAGE_SOURCE_URL_ATTRS = (
    "href", "src", "data-href", "data-url", "data-link", "data-src",
)
# Document extensions that can carry an official notice/notification.
PAGE_SOURCE_DOC_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf", ".odt",
)
# Static assets that can never be a notice (skipped in the raw scan).
PAGE_SOURCE_ASSET_EXTENSIONS = (
    ".css", ".js", ".mjs", ".json", ".xml", ".map", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".webp", ".ico", ".avif", ".woff", ".woff2", ".ttf",
    ".eot", ".mp4", ".mp3", ".zip", ".rar", ".7z", ".tar", ".gz",
)
# Path words that mark a URL as a notice/document link in the raw source.
PAGE_SOURCE_NOTICE_TOKENS = (
    "notice", "notification", "notifications", "advt", "advertisement",
    "advert", "recruit", "recruitment", "vacancy", "vacancies", "result",
    "answer-key", "answerkey", "answer", "corrigendum", "addendum",
    "admission", "admit", "application", "career", "careers", "job", "jobs",
    "employ", "download", "form",
)
# Path words that mean a raw-source URL is page chrome, not a notice.
PAGE_SOURCE_IGNORED_URL_TOKENS = (
    "tender", "quotation", "login", "signin", "logout", "register", "privacy",
    "terms", "twitter", "facebook", "instagram", "youtube", "whatsapp",
    "telegram", "stylesheets", "scripts", "images", "fonts",
)


def _page_source_anchor_labels(text: str, base_url: str) -> dict[str, str]:
    """Map absolute URL -> cleaned anchor label for every <a> in the raw source.

    The normal listing parser already reads visible anchors; this map exists so
    a raw-source URL (e.g. one inside <noscript> or <iframe>) can reuse the
    label the page gives it.
    """
    labels: dict[str, str] = {}
    for match in re.finditer(r"(?is)<a\b([^>]{0,600}?)>(.*?)</a\s*>", text):
        attrs, inner = match.group(1), match.group(2)
        href_match = re.search(
            r"""(?ix)\bhref\s*=\s*["']([^"']+)["']""", attrs
        )
        if not href_match:
            continue
        url = canonical_url(urllib.parse.urljoin(base_url, href_match.group(1).strip()))
        if not url:
            continue
        label = clean_text(re.sub(r"(?is)<[^>]+>", " ", inner))
        if label:
            labels.setdefault(url, label)
    return labels


def _is_page_source_asset(url: str) -> bool:
    return urllib.parse.urlsplit(url).path.lower().endswith(PAGE_SOURCE_ASSET_EXTENSIONS)


def _looks_like_page_source_notice(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    path = parts.path.lower()
    if path.endswith(PAGE_SOURCE_DOC_EXTENSIONS):
        return True
    if any(token in path for token in PAGE_SOURCE_IGNORED_URL_TOKENS):
        return False
    return any(token in path for token in PAGE_SOURCE_NOTICE_TOKENS)


def _page_source_notice_urls(text: str, base_url: str) -> list[tuple[str, str]]:
    """Notice-like (absolute URL, raw occurrence) pairs in page order.

    Reads every href/src/data-* value in the whole source — including blocks
    the visible listing parser deliberately skips (<script>, <style>,
    <noscript>, <svg>) — plus bare http(s) URLs (JS configs, JSON-LD, meta
    content). Same-page anchors, static assets and aggregator/portal hosts are
    excluded. The raw occurrence is kept so context can be read from the exact
    source location (relative hrefs do not appear verbatim in the page text).
    """
    attribute_pattern = re.compile(
        r"""(?ix)\b(?:%s)\s*=\s*["']([^"']+)["']"""
        % "|".join(PAGE_SOURCE_URL_ATTRS)
    )
    urls: list[tuple[str, str]] = []
    seen: set[str] = set()

    def consider(raw_url: str) -> None:
        occurrence = raw_url.strip()
        url = canonical_url(occurrence.rstrip(".,;:)]}>\"'"))
        if not url or url in seen:
            return
        if url.split("#", 1)[0] == base_url.split("#", 1)[0]:
            return  # same-page anchor / self link
        if is_discovery_host(url) or is_offline_form_url(url):
            return
        if _is_page_source_asset(url) or not _looks_like_page_source_notice(url):
            return
        seen.add(url)
        urls.append((url, occurrence))

    for raw in attribute_pattern.findall(text):
        consider(urllib.parse.urljoin(base_url, raw))
    for raw in re.findall(r"(?i)https?://[^\s\"'<>\\]+", text):
        consider(raw)
    return urls


def _page_source_context(text: str, occurrence: str) -> str:
    """Plain text that immediately precedes a URL in the raw source.

    Used as the title when the link has no anchor label (iframes, noscript
    blocks, bare URLs): the notice title usually sits right before its link.
    """
    index = text.find(occurrence)
    if index == -1:
        index = text.lower().find(occurrence.lower())
    if index == -1:
        return ""
    window = text[max(0, index - 400) : index]
    window = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", window)
    window = re.sub(r"(?is)<[^>]+>", " ", window)
    window = clean_text(window)
    if not window:
        return ""
    window = window[-160:]
    separators = list(re.finditer(r"(?:\s(?:[|»›•·]|[-–—]{1,2})\s|\s{2,})", window))
    if separators:
        window = window[separators[-1].end() :]
    return window.strip(" |»›•-–—")[:160]


def _page_source_candidate_title(url: str, label: str, text: str, occurrence: str) -> str:
    """Pick a publishable title for a raw-source link.

    Anchor label first, then the text preceding the URL in the raw source,
    then the URL's own document name. Generic labels ("click here") and
    code-remnant context ("var n = { url:") are never used; an empty result
    means the link cannot be published.
    """
    context = _page_source_context(text, occurrence)
    if context and re.search(r"[={}\\]", context):
        context = ""
    for candidate in (label, context):
        if candidate and not is_junk_job_title(candidate) and len(candidate) >= 8:
            return clean_title(candidate)
    name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
    name = re.sub(
        r"\.(?:pdf|docx?|xlsx?|pptx?|rtf|odt|html?|aspx?|php|jsp)$",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(r"[_+%]+", " ", name)
    name = re.sub(r"(?i)\b(?:download|click|here|view|open)\b", " ", name)
    name = clean_title(name)
    if len(name) >= 8 and not is_junk_job_title(name):
        return name
    return ""


def page_source_candidates(
    download: Download, source: dict[str, Any], max_links: int = 200
) -> list[Candidate]:
    """Deep scan of the raw page source for notices the listing parser missed.

    Official pages frequently publish notices in places the visible listing
    parser skips: <noscript> fallback blocks, <iframe>/<embed> PDF embeds,
    image maps (<area href>), JavaScript-generated links and data-* hooks.
    This re-reads the raw source and keeps only links that classify as
    supported notices for the source.
    """
    text = decode_document(download)
    labels = _page_source_anchor_labels(text, download.url)
    candidates: list[Candidate] = []
    for url, occurrence in _page_source_notice_urls(text, download.url):
        label = clean_text(labels.get(url, ""))
        title = _page_source_candidate_title(url, label, text, occurrence)
        if not title:
            continue
        candidate = Candidate(clean_title(title), url, summary=label[:400])
        if looks_like_notice(candidate, source):
            candidates.append(candidate)
        if len(candidates) >= max_links:
            break
    return deduplicate_candidates(candidates)


def page_source_fallback_candidates(
    download: Download,
    discovered: list[Candidate],
    known: set[str],
    source: dict[str, Any],
) -> list[Candidate]:
    """Page-source rule: candidates the raw page source adds beyond the listing.

    Only meaningful for HTML pages (feeds are already fully parsed by the
    listing step). Returns raw-source candidates that are not already known to
    the monitor and not already in the listing, so the caller can publish them
    like any other newly discovered notice.
    """
    if parse_feed(decode_document(download), download.url):
        return []
    listed_urls = {canonical_url(candidate.url) for candidate in discovered}
    extras: list[Candidate] = []
    for candidate in page_source_candidates(download, source):
        if fingerprint(candidate) in known:
            continue
        if canonical_url(candidate.url) in listed_urls:
            continue
        extras.append(candidate)
    return deduplicate_candidates(extras)


def allowed_notice_types(source: dict[str, Any]) -> set[str]:
    configured = source.get("noticeTypes")
    if not isinstance(configured, list):
        return set(DEFAULT_NOTICE_TYPES)
    return {clean_text(value).lower() for value in configured} & DEFAULT_NOTICE_TYPES


def classify_notice(candidate: Candidate, source: dict[str, Any]) -> str | None:
    """Classify a link without guessing beyond its title/feed summary."""
    title = clean_title(candidate.title)
    lowered = f"{title} {candidate.summary}".lower()
    allowed = allowed_notice_types(source)
    if len(title) < 8 or is_junk_job_title(title):
        return None
    if any(term in lowered for term in EXCLUDED_TERMS):
        return None

    exclude_terms = [clean_text(term).lower() for term in source.get("excludeKeywords", [])]
    if any(term and term in lowered for term in exclude_terms):
        return None

    notice_type: str | None = None
    if any(term in lowered for term in ANSWER_KEY_TERMS):
        notice_type = "answer-key"
    elif any(term in lowered for term in RESULT_TERMS):
        notice_type = "result"
    elif any(term in lowered for term in ADMIT_CARD_TERMS) or _announces_exam_schedule(lowered):
        notice_type = "admit-card"
    elif any(term in lowered for term in UPDATE_TERMS) and any(
        term in lowered for term in ADMISSION_TERMS
    ):
        notice_type = "admission"
    elif any(term in lowered for term in UPDATE_TERMS) and any(
        term in lowered for term in RECRUITMENT_CONTEXT_TERMS
    ):
        notice_type = "corrigendum"
    elif (
        any(term in lowered for term in UPDATE_TERMS)
        and "corrigendum" in allowed
        and "admission" not in allowed
    ):
        notice_type = "corrigendum"
    elif any(term in lowered for term in ADMISSION_TERMS):
        notice_type = "admission"
    elif any(term in lowered for term in RECRUITMENT_TERMS):
        notice_type = "recruitment"
    else:
        include_terms = [clean_text(term).lower() for term in source.get("includeKeywords", [])]
        if any(term and term in lowered for term in include_terms):
            fallback = clean_text(source.get("defaultNoticeType", "recruitment")).lower()
            notice_type = fallback if fallback in DEFAULT_NOTICE_TYPES else "recruitment"

    return notice_type if notice_type in allowed else None


def looks_like_notice(candidate: Candidate, source: dict[str, Any]) -> bool:
    return classify_notice(candidate, source) is not None


def deduplicate_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    result: list[Candidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = fingerprint(candidate)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def parse_published(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except ValueError:
        return ""


def parse_date_token(value: str) -> str:
    value = clean_text(value).lower().replace(",", "")
    numeric = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", value)
    if numeric:
        day, month, year = (int(part) for part in numeric.groups())
        year += 2000 if year < 100 else 0
    else:
        # Accepts "13 June 2026", "13-Jun-2026" and "13/June/2026".
        words = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?[\s./-]+([a-z]+)[\s./-]+(\d{4})", value)
        if not words:
            return ""
        day, month_name, year_text = words.groups()
        day, month, year = int(day), MONTHS.get(month_name, 0), int(year_text)
    try:
        return datetime(year, month, day).strftime("%d-%m-%Y")
    except ValueError:
        return ""


def find_labelled_date(text: str, labels: str) -> str:
    # Official notices often insert phrases such as "of online registration" between
    # a date label and its value. Keep the window short so an unrelated date is not used.
    match = re.search(
        rf"(?is)(?:{labels})(?:\s+(?:is|on))?\s*[:–-]?\s*[^.;|]{{0,90}}?\b({DATE_TOKEN})",
        text,
    )
    return parse_date_token(match.group(1)) if match else ""


def detect_extension(text: str) -> tuple[bool, str]:
    """Return (is_extension, new_date) from a corrigendum/addendum body.

    ``is_extension`` is True only when the text carries an explicit last-date
    extension phrase. ``new_date`` is the revised deadline when one can be read
    from the text, otherwise the empty string. When no date can be read the
    extension is reported but not applied, so a stale deadline is never invented.
    """
    lowered = clean_text(text).lower()
    if not any(term in lowered for term in EXTENSION_TERMS):
        return False, ""
    pattern = (
        r"(?is)(?:last\s+date(?:\s+(?:has\s+been|is|stands?|further))?\s*(?:further\s+)?extended"
        r"|closing\s+date\s+extended"
        r"|extended\s*(?:up\s+to|till|until|to)"
        r"|extension\s*(?:of|in)?\s*(?:the\s+)?(?:last|closing|application)\s+date"
        r")\s*[:–-]?\s*[^.;|]{0,60}?\b(" + DATE_TOKEN + r")"
    )
    match = re.search(pattern, text)
    return True, parse_date_token(match.group(1)) if match else ""


def infer_vacancies(text: str) -> str:
    patterns = (
        r"(?i)\brecruitment\s+(?:of|for)\s+([1-9]\d{0,5}(?:,\d{3})?)(?:\s+[a-z][a-z&/()'-]*){0,8}\s+(?:vacancies|vacancy|posts?|positions?)\b",
        r"(?i)\b([1-9]\d{0,5}(?:,\d{3})?)\s+(?:vacancies|vacancy|posts?|positions?)\b",
        r"(?i)\b(?:vacancies|vacancy|posts?|positions?)\s*(?:are|is|:|-)?\s*([1-9]\d{0,5}(?:,\d{3})?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)} Posts"
    return "See Notification"


def infer_qualification(text: str, source: dict[str, Any]) -> tuple[str, str]:
    lowered = text.lower()
    found: list[str] = []
    if re.search(r"\b(?:8th|eighth)\b", lowered):
        found.append("8th")
    if re.search(r"\b(?:10th|matric(?:ulation)?)\b", lowered):
        found.append("10th")
    if re.search(r"\b(?:12th|10\+2|senior secondary)\b", lowered):
        found.append("12th")
    if re.search(r"\b(?:iti|industrial training institute|diploma)\b", lowered):
        found.append("ITI / Diploma")
    if re.search(r"\b(?:graduate|graduation|bachelor(?:'s)?|b\.?e\.?|b\.?tech)\b", lowered):
        found.append("Graduate")
    if re.search(r"\b(?:post.?graduate|master(?:'s)?|m\.?tech|ph\.?d)\b", lowered):
        found.append("Post Graduate")
    if re.search(r"\b(?:b\.?ed|e\.?t\.?t|pstet|ctet)\b", lowered):
        found.append("B.Ed / ETT")

    unique = list(dict.fromkeys(found))
    qualification = " / ".join(unique[:4]) if unique else "See Official Notification"
    if source.get("categorySlug") == "punjab-police":
        category = "Police"
    elif "B.Ed / ETT" in unique:
        category = "B.Ed/ETT"
    elif "ITI / Diploma" in unique:
        category = "Diploma/ITI"
    elif "Graduate" in unique or "Post Graduate" in unique:
        category = "Graduate"
    elif "12th" in unique:
        category = "12th"
    else:
        category = "8th/10th"
    return qualification, category


def infer_advertisement_number(text: str) -> str:
    patterns = (
        r"(?i)\b(?:advertisement|advt\.?|notification)\s*(?:no\.?|number|#)\s*[:.-]?\s*([A-Z0-9][A-Z0-9/._-]{1,30})",
        r"(?i)\b(CRA\s*[-/]?\s*\d{2,4}[/.-]\d{2,4})\b",
        r"(?i)\b(CEN\s*[-/]?\s*\d{1,3}[/.-]\d{2,4})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = clean_text(match.group(1)).strip(" .,:;-").upper()
            if value in INVALID_ADVT_NUMBERS or value.rstrip(".") in INVALID_ADVT_NUMBERS:
                continue
            return value
    return "See Official Notice"


def infer_age(text: str) -> str:
    patterns = (
        r"(?i)\bage (?:limit|as on)?\s*(?:is|:|-)?\s*(\d{2}\s*(?:to|-|–)\s*\d{2}\s*years?)",
        r"(?i)\bbetween\s+(\d{2})\s+and\s+(\d{2})\s+years?",
        r"(?i)\b(?:maximum|max\.?|upper) age\s*(?:limit)?\s*(?:is|:|-)?\s*(\d{2}\s*years?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            if len(match.groups()) == 2:
                return f"{match.group(1)} to {match.group(2)} Years"
            return clean_text(match.group(1))
    return "See Official Notification"


def useful_summary(text: str, title: str, source_name: str, notice_type: str) -> str:
    cleaned = clean_text(text)
    if cleaned:
        sentences = re.split(r"(?<=[.!?])\s+|\s*[|•]\s*", cleaned)
        useful = [
            sentence
            for sentence in sentences
            if len(sentence) >= 35
            and any(
                term in sentence.lower()
                for term in (
                    "recruit", "vacan", "application", "post", "eligib", "admission",
                    "answer key", "result", "merit", "corrigendum", "addendum"
                )
            )
        ]
        if useful:
            return clean_text(" ".join(useful[:3]))[:700]
        if len(cleaned) >= 60 and len(cleaned) <= 900:
            return cleaned
    labels = {
        "recruitment": "recruitment notice",
        "admission": "admission notice",
        "answer-key": "answer key",
        "result": "result notice",
        "admit-card": "admit card / exam notice",
        "corrigendum": "recruitment corrigendum/addendum",
    }
    return (
        f"{source_name} published a new {labels.get(notice_type, 'official notice')}: {title}. "
        "Open the official link to verify all dates, conditions and instructions."
    )


def pdf_text(data: bytes) -> str:
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        return clean_text(" ".join((page.extract_text() or "") for page in reader.pages[:10]))[:MAX_TEXT_LENGTH]
    except Exception as exc:  # A malformed PDF must not stop other sources.
        print(f"  PDF text extraction skipped: {exc}", file=sys.stderr)
        return ""


def enrich_candidate(candidate: Candidate, source: dict[str, Any]) -> tuple[str, str, str, str]:
    """Return (searchable text, description source, best apply URL, best PDF URL).

    The PDF URL is the direct notification PDF when one can be found. If the
    candidate itself is a PDF, that URL is returned. If the candidate is an
    HTML detail page that contains a PDF link, the strongest PDF on that page
    (preferring labelled advertisement/notification/result links over generic
    helpers) is returned so the homepage can show the real PDF under
    ``Official Notice / Portal`` automatically. When no PDF is found on the
    detail page the candidate URL itself is kept (the official detail page).
    """
    combined = clean_text(f"{candidate.title}. {candidate.summary}")
    description_source = candidate.summary
    apply_url = candidate.url
    pdf_url = candidate.url
    if source.get("enrichDetails", True) is False:
        return combined, description_source, apply_url, pdf_url

    try:
        download = fetch_url(
            candidate.url,
            timeout=int(source.get("detailTimeout", 20)),
            retries=1,
            proxy_fallback=bool(source.get("proxyFallback")),
        )
    except RuntimeError as exc:
        print(f"  Could not enrich {candidate.url}: {exc}", file=sys.stderr)
        return combined, description_source, apply_url, pdf_url

    is_pdf = download.content_type == "application/pdf" or urllib.parse.urlsplit(download.url).path.lower().endswith(".pdf")
    if is_pdf:
        extracted = pdf_text(download.data)
        # Candidate itself is the notification PDF — use its final URL after redirects.
        pdf_url = canonical_url(download.url) or candidate.url
        return clean_text(f"{combined}. {extracted}")[:MAX_TEXT_LENGTH], description_source or extracted, apply_url, pdf_url

    text = decode_document(download)
    _, parser = parse_html(text, download.url)
    richer = clean_text(f"{combined}. {parser.description}. {parser.text}")[:MAX_TEXT_LENGTH]
    description_source = description_source or parser.description
    for url, label in parser.links:
        if re.search(r"(?i)\b(?:apply online|online application|register now|new registration|click here to apply|apply now|candidate registration|application form|online portal|apply|registration)\b", label or ""):
            safe = canonical_url(url)
            if safe:
                apply_url = safe
                break
    if apply_url == candidate.url:
        for url, _ in parser.links:
            path_lower = urllib.parse.urlsplit(url).path.lower()
            if any(term in path_lower for term in ("/apply", "/register", "/registration", "/online")):
                safe = canonical_url(url)
                if safe:
                    apply_url = safe
                    break
    # Find the strongest PDF on the detail page for the Official Notice button.
    best_pdf = ""
    fallback_pdf = ""
    for url, label in parser.links:
        safe = canonical_url(url)
        if not safe:
            continue
        # Most official PDFs end with .pdf in the path; also handle rare cases
        # like download.php?file=xyz.pdf by checking for .pdf in the URL.
        path = urllib.parse.urlsplit(safe).path.lower()
        is_pdf_url = path.endswith(".pdf")
        if not is_pdf_url and ".pdf" in safe.lower():
            # Only treat as PDF if the label or URL strongly suggests it.
            if re.search(r"(?i)\bpdf\b", label or "") or PRIMARY_ATTACHMENT_PATTERN.search(label or ""):
                is_pdf_url = True
        if not is_pdf_url:
            continue
        if HELPER_ATTACHMENT_PATTERN.search(label or ""):
            continue
        if PRIMARY_ATTACHMENT_PATTERN.search(label or "") and is_pdf_url:
            best_pdf = safe
            break
        if is_pdf_url and not fallback_pdf:
            fallback_pdf = safe
    if best_pdf:
        pdf_url = best_pdf
    elif fallback_pdf:
        pdf_url = fallback_pdf
    else:
        pdf_url = candidate.url
    return richer, description_source, apply_url, pdf_url


NOTICE_PRESENTATION = {
    "recruitment": {
        "newBadge": "NEW JOB ALERT", "oldBadge": "JOB NOTICE",
        "newColor": "bg-red-600", "oldColor": "bg-blue-600",
        "applyLabel": "Open Official Application",
    },
    "admission": {
        "newBadge": "NEW ADMISSION", "oldBadge": "ADMISSION",
        "newColor": "bg-purple-600", "oldColor": "bg-purple-600",
        "applyLabel": "Open Admission Notice",
    },
    "answer-key": {
        "newBadge": "NEW ANSWER KEY", "oldBadge": "ANSWER KEY",
        "newColor": "bg-emerald-600", "oldColor": "bg-emerald-600",
        "applyLabel": "Open Official Answer Key",
    },
    "result": {
        "newBadge": "NEW RESULT", "oldBadge": "RESULT",
        "newColor": "bg-rose-600", "oldColor": "bg-rose-600",
        "applyLabel": "Open Official Result",
    },
    "admit-card": {
        "newBadge": "NEW ADMIT CARD", "oldBadge": "ADMIT CARD",
        "newColor": "bg-emerald-600", "oldColor": "bg-emerald-600",
        "applyLabel": "Download Admit Card",
    },
    "corrigendum": {
        "newBadge": "NEW UPDATE", "oldBadge": "RECRUITMENT UPDATE",
        "newColor": "bg-amber-600", "oldColor": "bg-amber-600",
        "applyLabel": "Open Updated Notice",
    },
}


def notice_presentation(notice_type: str, is_new: bool) -> tuple[str, str]:
    presentation = NOTICE_PRESENTATION.get(notice_type, NOTICE_PRESENTATION["recruitment"])
    age = "new" if is_new else "old"
    return presentation[f"{age}Badge"], presentation[f"{age}Color"]


def notice_steps(notice_type: str) -> list[str]:
    if notice_type in {"result", "answer-key"}:
        return [
            "Open the official result or answer-key link below.",
            "Match the post, advertisement number, examination date and set/category carefully.",
            "Download the official file and retain it for reference."
        ]
    if notice_type == "admit-card":
        return [
            "Open the official admit card or call letter portal link below.",
            "Log in using your registration credentials, roll number, and date of birth.",
            "Download and print the official admit card / hall ticket."
        ]
    if notice_type == "admission":
        return [
            "Open the official admission notification and review eligible courses, criteria and dates.",
            "Fill the online or offline admission form with required student and parent details.",
            "Submit the registration and save the acknowledgement receipt."
        ]
    if notice_type == "corrigendum":
        return [
            "Read the corrigendum/addendum together with the original recruitment advertisement.",
            "Check every revised date, vacancy, eligibility condition and instruction.",
            "Use only the latest instructions published on the official website."
        ]
    return [
        "Open the official notification and read the complete eligibility conditions.",
        "Confirm the application dates, fee, age limit and required documents on the official website.",
        "Use only the official application link and keep the submitted form or receipt for reference."
    ]


def job_from_candidate(candidate: Candidate, source: dict[str, Any], now: datetime) -> dict[str, Any]:
    source_name = strip_discovery_branding(
        clean_text(source.get("name") or source.get("department") or "Official website")
    )
    # A bare website address (e.g. "sbi.gov.in") is not an authority; strip it so
    # the department is inferred from the title or resolved from the official host.
    department = sanitize_department(source.get("department")) or sanitize_department(source_name)
    if not department:
        department = infer_recruiting_department(candidate.title)
    if not department:
        department = (
            department_from_url(str(source.get("url", "")))
            or department_from_url(candidate.url)
        )
    title = official_job_title(candidate.title, department)
    if not title:
        raise ValueError("notice has no specific recruiting department and vacancy title")
    notice_type = classify_notice(candidate, source) or "recruitment"
    searchable, description_source, apply_url, discovered_pdf_url = enrich_candidate(candidate, source)
    qualification, qual_category = infer_qualification(searchable, source)
    candidate_url = canonical_url(candidate.url)
    discovered_pdf_url = canonical_url(discovered_pdf_url) or candidate_url
    # If the detail page's best PDF points to a discovery host, discard it.
    if is_discovery_host(discovered_pdf_url):
        discovered_pdf_url = candidate_url
    source_url = canonical_url(source["url"])
    if is_discovery_host(candidate_url) or is_discovery_host(source_url):
        raise ValueError("discovery-feed URLs cannot be published as job details")
    is_pdf = urllib.parse.urlsplit(candidate_url).path.lower().endswith(".pdf")
    # Prefer the PDF discovered on the detail page for the Official Notice link
    # when one exists; otherwise keep the candidate URL itself (direct PDF or
    # official detail page). This puts the real notification PDF under
    # ``Official Notice / Portal`` automatically, when possible.
    pdf_link_final = discovered_pdf_url if discovered_pdf_url else candidate_url
    # Guard against discovery hosts and ensure a canonical form.
    if is_discovery_host(pdf_link_final):
        pdf_link_final = candidate_url
    pdf_link_final = canonical_url(pdf_link_final) or candidate_url
    last_date = find_labelled_date(searchable, LAST_DATE_LABELS)
    start_date = find_labelled_date(
        searchable,
        r"start(?:ing)?\s+date|opening\s+date|applications?\s+open",
    )
    discovered = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stable_id = int(hashlib.sha256(fingerprint(candidate).encode()).hexdigest()[:12], 16)
    badge, badge_color = notice_presentation(notice_type, True)
    presentation = NOTICE_PRESENTATION[notice_type]
    is_extension, extension_date = detect_extension(searchable) if notice_type == "corrigendum" else (False, "")

    apply_final = (
        canonical_url(source_url if is_pdf and apply_url == candidate_url else apply_url)
        or candidate_url
    )
    if is_discovery_host(apply_final) or is_generic_homepage(apply_final):
        apply_final = "" if is_generic_homepage(candidate_url) or is_discovery_host(candidate_url) else candidate_url
    if is_generic_homepage(pdf_link_final) or is_discovery_host(pdf_link_final):
        pdf_link_final = "" if is_generic_homepage(candidate_url) or is_discovery_host(candidate_url) else candidate_url

    return {
        "id": stable_id,
        "title": title,
        "department": department,
        "vacancies": infer_vacancies(searchable),
        "qualification": qualification,
        "qualCategory": qual_category,
        "lastDate": last_date or "See Notification",
        "startDate": start_date
        or (f"Published {candidate.notice_date}" if candidate.notice_date else "")
        or (f"Published {candidate.published_at[:10]}" if candidate.published_at else "Newly Published"),
        "examDate": "See Official Notification",
        "location": clean_text(source.get("location") or ("Punjab" if source.get("type") == "punjab" else "All India")),
        "applyMode": "Offline" if any(marker in searchable.lower() for marker in OFFLINE_APPLY_MARKERS) else "Online / As Notified",
        "alertType": notice_type,
        "badge": badge,
        "badgeColor": badge_color,
        "type": "punjab" if source.get("type") == "punjab" else "central",
        "categorySlug": clean_text(source.get("categorySlug") or "central"),
        "advtNo": infer_advertisement_number(searchable),
        "feeGen": "See Official Notification",
        "feeSC": "See Official Notification",
        "feeMode": "As Notified",
        "age": infer_age(searchable),
        "details": useful_summary(description_source or searchable[:1200], title, source_name, notice_type),
        "howToApply": notice_steps(notice_type),
        "pdfLink": "" if is_discovery_host(pdf_link_final) or is_generic_homepage(pdf_link_final) else pdf_link_final,
        "applyLink": "" if is_discovery_host(apply_final) or is_generic_homepage(apply_final) else apply_final,
        "applyLabel": presentation["applyLabel"],
        "sourceName": source_name,
        "sourceUrl": source_url,
        "noticeUrl": candidate_url,
        "publishedAt": candidate.published_at,
        "discoveredAt": discovered,
        # Internal fields used only to link a last-date-extension corrigendum back to
        # its original recruitment. They are stripped by apply_extensions() and are
        # never written to data/auto-jobs.json.
        "isExtension": is_extension,
        "extensionDate": extension_date,
        "automated": True
    }


_EXTENSION_LINK_STOPWORDS = {
    "corrigendum",
    "corrigenda",
    "addendum",
    "advertisement",
    "advt",
    "notification",
    "notice",
    "regarding",
    "dated",
    "recruitment",
    "recruitments",
    "vacancy",
    "vacancies",
    "application",
    "online",
    "extended",
    "extension",
    "posts",
    "post",
    "official",
}


def _extension_title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", clean_text(title).lower())
    return {word for word in words if len(word) >= 3 and word not in _EXTENSION_LINK_STOPWORDS}


def _extension_matches(corrigendum: dict[str, Any], target: dict[str, Any]) -> bool:
    """Heuristically decide whether a corrigendum belongs to a given job."""
    if target.get("alertType") not in {"recruitment", "admission"}:
        return False
    corr_advt = clean_text(corrigendum.get("advtNo", "")).lower()
    targ_advt = clean_text(target.get("advtNo", "")).lower()
    if (
        corr_advt
        and corr_advt != "see official notice"
        and targ_advt
        and targ_advt != "see official notice"
        and corr_advt == targ_advt
    ):
        return True
    if clean_text(corrigendum.get("department", "")).lower() != clean_text(target.get("department", "")).lower():
        return False
    corr_tokens = _extension_title_tokens(corrigendum.get("title", ""))
    targ_tokens = _extension_title_tokens(target.get("title", ""))
    if not corr_tokens or not targ_tokens:
        return False
    overlap = len(corr_tokens & targ_tokens) / max(len(corr_tokens), len(targ_tokens))
    return overlap >= 0.4


def apply_extensions(jobs: list[dict[str, Any]]) -> bool:
    """Link last-date-extension corrigenda to their original recruitments.

    For each corrigendum that announces an extension, the matching recruitment is
    marked with the new deadline (and its original one preserved). Corrigenda are
    matched by advertisement number first, then by department + title overlap.
    Internal ``isExtension`` / ``extensionDate`` fields are removed from every job
    so they are not persisted. Returns True when any job was changed.
    """
    changed = False
    for job in jobs:
        is_extension = bool(job.pop("isExtension", False))
        extension_date = clean_text(job.pop("extensionDate", ""))
        if job.get("alertType") != "corrigendum":
            continue
        if not is_extension:
            continue
        if not extension_date:
            # Extension announced but no new date could be read: leave deadlines
            # untouched rather than guessing.
            continue
        targets = [candidate for candidate in jobs if _extension_matches(job, candidate)]
        # Prefer advertisement-number matches when present.
        targets.sort(
            key=lambda candidate: 0
            if clean_text(candidate.get("advtNo", "")).lower() == clean_text(job.get("advtNo", "")).lower()
            else 1
        )
        if not targets:
            continue
        for target in targets:
            target.setdefault("originalLastDate", target.get("lastDate", "See Notification"))
            target["lastDate"] = extension_date
            target["lastDateExtended"] = True
            target["extendedLastDate"] = extension_date
            target["extensionNoticeUrl"] = job.get("pdfLink") or job.get("applyLink") or ""
            target["extensionNoticeTitle"] = clean_text(job.get("title", ""))
            changed = True
    return changed


def strip_internal_job_fields(jobs: list[dict[str, Any]]) -> bool:
    """Drop monitor-only fields so they never reach data/auto-jobs.json."""
    changed = False
    for job in jobs:
        for field in ("isExtension", "extensionDate"):
            if field in job:
                job.pop(field, None)
                changed = True
    return changed


def normalize_stored_departments(jobs: list[dict[str, Any]]) -> bool:
    """Replace a domain-as-department with the real authority and drop the
    leading website link from the title (e.g. "sbi.gov.in — Result" -> department
    becomes "State Bank of India (SBI)" and the title is rebuilt without it)."""
    changed = False
    for job in jobs:
        department = clean_text(job.get("department", ""))
        if department and not is_website_domain(department):
            continue
        resolved = (
            department_from_url(str(job.get("sourceUrl", "")))
            or department_from_url(str(job.get("noticeUrl", "")))
            or department_from_url(str(job.get("pdfLink", "")))
            or department_from_url(department)
        )
        if not resolved:
            continue
        raw_title = strip_website_domains(clean_title(job.get("title", ""))).strip(" —–-:")
        new_title = official_job_title(raw_title, resolved)
        if not new_title:
            continue
        job["department"] = resolved
        job["title"] = new_title
        source_name = clean_text(job.get("sourceName", ""))
        if not is_specific_department(source_name) or is_website_domain(source_name):
            job["sourceName"] = resolved
        changed = True
        print(f"  Resolved domain department -> {resolved}: {new_title[:70]}")
    return changed


def reclassify_stored_jobs(jobs: list[dict[str, Any]]) -> bool:
    """Re-derive each stored alert's column from its title.

    Classification rules tighten over time (shortlisted/eligible/score-card lists
    belong in Results; a written-test/exam-date announcement belongs in Admit
    Card). Stored alerts keep their first-seen badge age but move to the correct
    column and pick up that column's badge, colour, apply label and steps.
    Returns True when any job changed.
    """
    changed = False
    for job in jobs:
        title = clean_title(job.get("title", ""))
        candidate = Candidate(
            title,
            clean_text(job.get("noticeUrl") or job.get("pdfLink") or job.get("applyUrl") or ""),
        )
        new_type = classify_notice(candidate, {})
        if not new_type or new_type == job.get("alertType"):
            continue
        is_new = str(job.get("badge", "")).upper().startswith("NEW")
        badge, badge_color = notice_presentation(new_type, is_new)
        job["alertType"] = new_type
        job["badge"] = badge
        job["badgeColor"] = badge_color
        job["applyLabel"] = NOTICE_PRESENTATION[new_type]["applyLabel"]
        job["howToApply"] = notice_steps(new_type)
        changed = True
        print(f"  Re-routed notice to '{new_type}': {title[:70]}")
    return changed


def _date_sort_key(value: str) -> datetime | None:
    parsed = parse_date_token(clean_text(value))
    if not parsed:
        return None
    try:
        return datetime.strptime(parsed, "%d-%m-%Y")
    except ValueError:
        return None


def _is_weak_public_link(url: str, source_url: str = "") -> bool:
    target = canonical_url(url)
    if not target or is_generic_homepage(target) or is_discovery_host(target):
        return True
    if source_url and target == canonical_url(source_url):
        return True
    return False


def _is_better_notice_link(new: str, old: str, source_url: str = "") -> bool:
    new_url = canonical_url(new)
    if not new_url or is_discovery_host(new_url) or is_generic_homepage(new_url):
        return False
    if _is_weak_public_link(old, source_url):
        return True
    if is_direct_pdf_url(new_url) and not is_direct_pdf_url(old):
        return True
    return False


def job_notice_urls(job: dict[str, Any]) -> set[str]:
    urls: set[str] = set()
    for field in ("noticeUrl", "pdfLink", "applyLink"):
        url = canonical_url(job.get(field, ""))
        if url:
            urls.add(url)
    return urls


def find_existing_job_for_candidate(
    jobs: list[dict[str, Any]], candidate: Candidate, source: dict[str, Any]
) -> dict[str, Any] | None:
    """Locate the already-published alert that corresponds to this notice URL."""
    candidate_url = canonical_url(candidate.url)
    if not candidate_url:
        return None
    exact = [job for job in jobs if candidate_url in job_notice_urls(job)]
    if len(exact) == 1:
        return exact[0]
    if exact:
        source_url = canonical_url(source.get("url", ""))
        same_source = [
            job for job in exact if canonical_url(job.get("sourceUrl", "")) == source_url
        ]
        return (same_source or exact)[0]
    source_url = canonical_url(source.get("url", ""))
    title = official_job_title(
        candidate.title, clean_text(source.get("department") or source.get("name") or "")
    ).lower()
    if not title:
        return None
    titled = [
        job
        for job in jobs
        if canonical_url(job.get("sourceUrl", "")) == source_url
        and clean_text(job.get("title", "")).lower() == title
    ]
    return titled[0] if len(titled) == 1 else None


def merge_job_details(existing: dict[str, Any], fresh: dict[str, Any]) -> bool:
    """Copy verified details from a re-fetched notice onto the published job.

    Identity fields (id, discoveredAt) stay put. Placeholder values and generic
    homepage links are replaced; a later official last date overwrites an older
    one, but an already-applied extension is never reverted to an earlier date.
    """
    changed = False
    source_url = clean_text(existing.get("sourceUrl") or fresh.get("sourceUrl") or "")

    if not existing.get("noticeUrl") and fresh.get("noticeUrl"):
        existing["noticeUrl"] = fresh["noticeUrl"]
        changed = True

    if not existing.get("publishedAt") and fresh.get("publishedAt"):
        existing["publishedAt"] = fresh["publishedAt"]
        changed = True

    for field in (
        "title",
        "department",
        "vacancies",
        "qualification",
        "qualCategory",
        "advtNo",
        "age",
        "examDate",
        "applyMode",
        "applyLabel",
        "details",
        "howToApply",
    ):
        new = fresh.get(field)
        old = existing.get(field)
        if new in (None, ""):
            continue
        if field == "howToApply" and not isinstance(new, list):
            continue
        if is_placeholder_detail(old) and not is_placeholder_detail(new):
            existing[field] = new
            changed = True
        elif field in {"title", "department"} and new != old and not is_placeholder_detail(new):
            existing[field] = new
            changed = True

    new_last = parse_date_token(fresh.get("lastDate", ""))
    old_last = parse_date_token(existing.get("lastDate", ""))
    if new_last:
        new_dt = _date_sort_key(new_last)
        old_dt = _date_sort_key(old_last or "")
        if not old_last or is_placeholder_detail(existing.get("lastDate", "")):
            existing["lastDate"] = new_last
            changed = True
        elif new_last != old_last and new_dt and old_dt:
            if existing.get("lastDateExtended") and new_dt < old_dt:
                pass
            else:
                existing["lastDate"] = new_last
                changed = True

    new_start = clean_text(fresh.get("startDate", ""))
    if new_start and not is_placeholder_detail(new_start):
        if is_placeholder_detail(existing.get("startDate", "")):
            existing["startDate"] = new_start
            changed = True

    for field in ("pdfLink", "applyLink"):
        if _is_better_notice_link(fresh.get(field, ""), existing.get(field, ""), source_url):
            existing[field] = canonical_url(fresh.get(field, ""))
            changed = True
        elif is_generic_homepage(existing.get(field, "")):
            existing[field] = ""
            changed = True

    return changed


def backfill_extracted_fields(jobs: list[dict[str, Any]]) -> bool:
    """Fill placeholder dates/vacancies/advt numbers from text already stored."""
    changed = False
    for job in jobs:
        blob = " ".join(
            clean_text(job.get(field, ""))
            for field in ("title", "details", "qualification")
        )
        if is_placeholder_detail(job.get("lastDate", "")):
            found = find_labelled_date(blob, LAST_DATE_LABELS)
            if found:
                job["lastDate"] = found
                changed = True
        if is_placeholder_detail(job.get("vacancies", "")):
            found = infer_vacancies(blob)
            if found != "See Notification":
                job["vacancies"] = found
                changed = True
        if is_placeholder_detail(job.get("advtNo", "")):
            found = infer_advertisement_number(blob)
            if found != "See Official Notice":
                job["advtNo"] = found
                changed = True
        if is_placeholder_detail(job.get("age", "")):
            found = infer_age(blob)
            if found != "See Official Notification":
                job["age"] = found
                changed = True
        for field in ("pdfLink", "applyLink", "offlineFormLink"):
            if is_generic_homepage(job.get(field, "")):
                job[field] = ""
                changed = True
        if not canonical_url(job.get("noticeUrl", "")):
            for field in ("pdfLink", "applyLink"):
                url = canonical_url(job.get(field, ""))
                if url and not is_generic_homepage(url):
                    job["noticeUrl"] = url
                    changed = True
                    break
    return changed


def refresh_published_source_jobs(
    jobs: list[dict[str, Any]],
    discovered: list[Candidate],
    known: set[str],
    source: dict[str, Any],
    now: datetime,
) -> bool:
    """Re-extract details for already-published notices still listed on the source.

    The first scan only stores what the listing/PDF yielded that day. Later runs
    must update last dates, vacancy counts, apply links and notification PDFs
    when the official page now has them — otherwise the homepage keeps stale
    \"See Notification\" placeholders forever.
    """
    pending: list[tuple[Candidate, dict[str, Any]]] = []
    for candidate in discovered:
        if fingerprint(candidate) not in known:
            continue
        existing = find_existing_job_for_candidate(jobs, candidate, source)
        if existing is None:
            continue
        pending.append((candidate, existing))

    def refresh_score(item: tuple[Candidate, dict[str, Any]]) -> int:
        existing = item[1]
        score = 0
        for field in ("lastDate", "vacancies", "advtNo", "age", "qualification"):
            if is_placeholder_detail(existing.get(field, "")):
                score += 2
        if _is_weak_public_link(existing.get("applyLink", ""), existing.get("sourceUrl", "")):
            score += 2
        if _is_weak_public_link(existing.get("pdfLink", ""), existing.get("sourceUrl", "")):
            score += 2
        if not is_direct_pdf_url(existing.get("pdfLink", "")):
            score += 1
        return score

    pending.sort(key=refresh_score, reverse=True)
    limit = max(0, int(source.get("maxRefreshPerRun", source.get("maxNewPerRun", 5))))
    changed = False
    refreshed = 0
    for candidate, existing in pending[:limit]:
        try:
            fresh = job_from_candidate(candidate, source, now)
        except Exception as exc:
            print(f"  Could not refresh {candidate.url}: {exc}", file=sys.stderr)
            continue
        if merge_job_details(existing, fresh):
            changed = True
            refreshed += 1
            print(f"  Updated details: {clean_text(existing.get('title', ''))[:80]}")
    if pending:
        print(f"  Refreshed {refreshed}/{min(len(pending), limit)} already-published notice(s)")
    return changed



def publish_unpublished_seen_notices(
    jobs: list[dict[str, Any]],
    discovered: list[Candidate],
    known: set[str],
    source: dict[str, Any],
    now: datetime,
) -> int:
    """Publish still-open notices that bootstrap only marked as seen.

    The first successful scan fingerprints every listing link and publishes
    ``bootstrapCount`` items. Active vacancies that were already on the page
    that day were then skipped forever. Catch them up when the listing still
    shows a readable, unexpired last date.
    """
    published_urls: set[str] = set()
    for job in jobs:
        published_urls |= job_notice_urls(job)
    pending: list[Candidate] = []
    for candidate in discovered:
        if fingerprint(candidate) not in known:
            continue
        if canonical_url(candidate.url) in published_urls:
            continue
        if find_existing_job_for_candidate(jobs, candidate, source) is not None:
            continue
        last_date = find_labelled_date(
            f"{candidate.title} {candidate.summary}", LAST_DATE_LABELS
        )
        if _dated_notice_is_active(last_date, now) is not True:
            continue
        pending.append(candidate)

    limit = max(0, int(source.get("maxCatchUpPerRun", source.get("maxNewPerRun", 5))))
    added = 0
    for candidate in pending[:limit]:
        try:
            job = job_from_candidate(candidate, source, now)
        except Exception as exc:
            print(f"  Could not catch up {candidate.url}: {exc}", file=sys.stderr)
            continue
        if _dated_notice_is_active(job.get("lastDate", ""), now) is False:
            continue
        jobs.append(job)
        added += 1
        print(f"  Caught up unpublished active notice: {clean_text(job.get('title', ''))[:80]}")
    if pending:
        print(f"  Catch-up published {added}/{min(len(pending), limit)} previously skipped notice(s)")
    return added


def _bootstrap_candidate_score(candidate: Candidate, source: dict[str, Any], now: datetime) -> int:
    """Rank first-scan candidates so `bootstrapCount` publishes real notices.

    The first successful scan marks every listing link as seen and publishes
    only the top `bootstrapCount`. Taking them in raw page order once published
    a navigation/portal link ("Apply Online (Recruitment Portal)") instead of
    the actual vacancy advertisements, so rank substantive, current, same-host
    notices first.
    """
    score = 0
    text = f"{candidate.title} {candidate.summary}"
    deadline = find_labelled_date(text, LAST_DATE_LABELS)
    activity = _dated_notice_is_active(deadline, now)
    if activity is True:
        score += 6
    elif activity is None:
        score += 2
    url = canonical_url(candidate.url)
    candidate_host = host_name(url)
    source_host = host_name(canonical_url(source.get("url", "")))
    if candidate_host and candidate_host == source_host:
        score += 2
    if url.lower().endswith(".pdf"):
        score += 1
    title = clean_title(candidate.title)
    if re.search(r"(?i)\b(?:recruitment|vacanc|admission|posts?\s+of|applications?|apply)\b", title):
        score += 1
    if is_junk_job_title(title):
        score -= 8
    if is_generic_homepage(url):
        score -= 8
    return score


def select_bootstrap_candidates(
    unseen: list[Candidate],
    source: dict[str, Any],
    now: datetime,
) -> list[Candidate]:
    """First-scan candidates ordered so the published ones are real notices."""
    return sorted(unseen, key=lambda candidate: _bootstrap_candidate_score(candidate, source, now), reverse=True)


def record_source_success(state: dict[str, Any], source_id: str, now: datetime) -> bool:
    """Track per-source reachability in seen-notices.json (committed data).

    Only writes on a meaningful transition so a healthy run never dirties the
    data files (the workflow commits only when a data file actually changed).
    """
    health = state.setdefault("sourceHealth", {})
    entry = health.get(source_id)
    if entry is None:
        health[source_id] = {
            "lastSuccessAt": now.isoformat().replace("+00:00", "Z"),
            "consecutiveFailures": 0,
        }
        return True
    failures = int(entry.get("consecutiveFailures") or 0)
    if failures or entry.get("lastSuccessAt") is None:
        entry["lastSuccessAt"] = now.isoformat().replace("+00:00", "Z")
        entry["consecutiveFailures"] = 0
        entry.pop("lastFailureAt", None)
        entry.pop("lastError", None)
        return True
    return False


def record_source_failure(state: dict[str, Any], source_id: str, now: datetime, error: str) -> bool:
    health = state.setdefault("sourceHealth", {})
    entry = health.setdefault(source_id, {"consecutiveFailures": 0})
    entry["consecutiveFailures"] = int(entry.get("consecutiveFailures") or 0) + 1
    entry["lastFailureAt"] = now.isoformat().replace("+00:00", "Z")
    entry["lastError"] = clean_text(error)[:300]
    return True


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read {path}: {exc}") from exc


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (AttributeError, ValueError):
        return None


def sanitize_published_jobs(jobs: list[dict[str, Any]], now: datetime) -> bool:
    """Enforce specific authority/post titles and remove known expired jobs."""
    changed = backfill_extracted_fields(jobs)
    kept: list[dict[str, Any]] = []
    for job in jobs:
        raw_title = strip_link_label_noise(clean_title(job.get("title", "")))
        if is_junk_job_title(raw_title):
            changed = True
            continue
        department = clean_text(job.get("department", ""))
        if not is_specific_department(department):
            # A listing row label ("View 22 Oct 2025") or a bare domain is not
            # an authority. Resolve the real one from the notice before giving
            # up, so a genuine alert is repaired instead of silently dropped.
            department = (
                infer_recruiting_department(raw_title)
                or department_from_url(str(job.get("sourceUrl", "")))
                or department_from_url(str(job.get("noticeUrl", "")))
                or department_from_url(str(job.get("pdfLink", "")))
            )
        specific_title = official_job_title(raw_title, department)
        if not specific_title:
            changed = True
            continue
        if job.get("department") != department or job.get("title") != specific_title:
            job["department"] = department
            job["title"] = specific_title
            changed = True
        if (
            clean_text(job.get("alertType", "recruitment")).lower() in {"recruitment", "admission"}
            and _dated_notice_is_active(job.get("lastDate", ""), now) is False
        ):
            changed = True
            continue
        kept.append(job)
    if len(kept) != len(jobs):
        jobs[:] = kept
    return changed


def refresh_badges(
    jobs: list[dict[str, Any]],
    now: datetime,
    new_hours: int = 72,
    *,
    new_days: int | None = None,
) -> bool:
    # Keep the old keyword usable for callers while making the default window
    # explicit and precise in hours.
    if new_days is not None:
        new_hours = new_days * 24
    changed = False
    for job in jobs:
        # Publication time is authoritative for the 72-hour NEW window. If an
        # official page does not expose it, fall back to when the monitor found it.
        published = parse_timestamp(job.get("publishedAt", ""))
        discovered = parse_timestamp(job.get("discoveredAt", ""))
        timestamp = published or discovered
        age_hours = (now - timestamp).total_seconds() / 3600 if timestamp else float("inf")
        is_new = 0 <= age_hours <= new_hours
        notice_type = clean_text(job.get("alertType", "recruitment")).lower()
        if notice_type not in NOTICE_PRESENTATION:
            notice_type = "recruitment"
        expected_badge, expected_color = notice_presentation(notice_type, is_new)
        if (
            job.get("alertType") != notice_type
            or job.get("badge") != expected_badge
            or job.get("badgeColor") != expected_color
        ):
            job["alertType"] = notice_type
            job["badge"] = expected_badge
            job["badgeColor"] = expected_color
            changed = True
    return changed


DISCOVERY_STOPWORDS = {
    "a", "an", "and", "for", "from", "in", "of", "on", "or", "the", "to", "with",
    "job", "jobs", "vacancy", "vacancies", "recruitment", "notification", "notice",
    "apply", "online", "offline", "latest", "new", "update", "updates", "2024",
    "2025", "2026", "2027", "post", "posts", "official",
}


def organization_aliases(org: dict[str, Any]) -> list[str]:
    aliases = [clean_text(org.get("name", "")), clean_text(org.get("department", ""))]
    aliases.extend(clean_text(item) for item in org.get("aliases", []) or [])
    return [alias.lower() for alias in aliases if len(alias) >= 3]


def approved_official_organizations(
    sources: list[dict[str, Any]],
    extra_path: Path = DEFAULT_OFFICIAL_ORGS,
) -> list[dict[str, Any]]:
    """Approved official boards only. Discovery feeds are never included."""
    orgs: list[dict[str, Any]] = []
    extra = read_json(extra_path, {"organizations": []})
    for entry in extra.get("organizations", []) if isinstance(extra, dict) else []:
        if isinstance(entry, dict) and canonical_url(entry.get("url", "")) and not is_discovery_host(entry.get("url", "")):
            orgs.append(entry)
    seen_ids = {clean_text(org.get("id")) for org in orgs}
    for source in sources:
        if source.get("role") == "discovery" or is_discovery_host(source.get("url", "")):
            continue
        source_id = clean_text(source.get("id"))
        if not source_id or source_id in seen_ids:
            continue
        orgs.append(source)
        seen_ids.add(source_id)
    return orgs


def match_official_organization(headline: str, organizations: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = strip_discovery_branding(headline).lower()
    best: dict[str, Any] | None = None
    best_len = 0
    for org in organizations:
        for alias in organization_aliases(org):
            if len(alias) <= best_len:
                continue
            if re.search(rf"(?i)(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text):
                best = org
                best_len = len(alias)
    return best


def headline_tokens(headline: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", strip_discovery_branding(headline).lower())
    return {word for word in words if word not in DISCOVERY_STOPWORDS}


def official_notices_for_headline(headline: str, candidates: list[Candidate]) -> list[Candidate]:
    tokens = headline_tokens(headline)
    scored: list[tuple[int, Candidate]] = []
    for candidate in candidates:
        overlap = tokens & headline_tokens(candidate.title)
        if overlap:
            scored.append((len(overlap), candidate))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _, candidate in scored[:3]]


def looks_like_discovery_headline(candidate: Candidate) -> bool:
    title = strip_discovery_branding(candidate.title)
    if len(title) < 12 or title.lower() in GENERIC_TITLES:
        return False
    lowered = f"{title} {candidate.summary}".lower()
    if any(term in lowered for term in EXCLUDED_TERMS):
        return False
    hints = RECRUITMENT_TERMS + ADMISSION_TERMS + ANSWER_KEY_TERMS + RESULT_TERMS + UPDATE_TERMS + (
        "jobs", "job ", " vacancy", "notification", "advt", "advertisement"
    )
    # Job-listing feeds such as LinkingSky often put the organisation and post
    # in separate table cells and omit words like "recruitment" entirely. The
    # row parser preserves the date cell; in a discovery feed that date plus a
    # non-generic title is sufficient evidence that this is a job lead.
    return bool(candidate.notice_date) or any(term in lowered for term in hints)


def load_discovery_feeds(path: Path = DEFAULT_DISCOVERY_FEEDS) -> list[dict[str, Any]]:
    registry = read_json(path, {"feeds": []})
    feeds: list[dict[str, Any]] = []
    for entry in registry.get("feeds", []) if isinstance(registry, dict) else []:
        if not isinstance(entry, dict):
            continue
        url = canonical_url(entry.get("url", ""))
        feed_id = clean_text(entry.get("id"))
        # Discovery feeds may live on a headline aggregator host or on one of
        # the offline-form portals (onlineforms.in / speedjob.in). Either way a
        # feed only ever supplies leads: the notice must still be verified on the
        # recruiting board's own website before anything is published, and the
        # portal's own URLs/branding are never shown on the homepage.
        if not url or not feed_id or not (is_discovery_host(url) or is_offline_form_url(url)):
            continue
        feeds.append({
            "id": feed_id,
            "name": clean_text(entry.get("name") or feed_id),
            "url": url,
            "maxHeadlines": int(entry.get("maxHeadlines") or registry.get("maxHeadlinesPerFeed", 40)),
            "maxNewPerRun": int(entry.get("maxNewPerRun") or registry.get("maxNewPerFeed", 5)),
        })
    return feeds


def offline_vacancy_covered_by_portal(
    job: dict[str, Any], offline_pool: list[dict[str, Any]]
) -> bool:
    """True when an offline-apply vacancy is already covered by an offline-form portal.

    Offline vacancies found on other discovery feeds are published only when
    the offline-form portal has no entry for them.
    """
    if not str(job.get("applyMode", "")).lower().startswith("offline"):
        return False
    return (
        match_offline_form(job.get("title", ""), job.get("department", ""), offline_pool)
        is not None
    )


def process_discovery_feeds(
    organizations: list[dict[str, Any]],
    state: dict[str, Any],
    now: datetime,
    dry_run: bool = False,
    offline_pool: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Scan aggregator headlines, then publish only matching official notices.

    Online-apply vacancies publish normally. An offline-apply vacancy is
    published only when no offline-form portal has an entry for it, because the
    offline-form portal is the single source for offline vacancies.
    """
    offline_pool = list(offline_pool or [])
    jobs: list[dict[str, Any]] = []
    added = 0
    state_changed = False
    state_sources = state.setdefault("sources", {})
    official_cache: dict[str, list[Candidate]] = {}
    official_downloads: dict[str, Download] = {}
    official_raw_cache: dict[str, list[Candidate]] = {}
    registered_websites: set[str] = set()

    for feed in load_discovery_feeds():
        print(f"Checking discovery feed {feed['name']}: {feed['url']}")
        try:
            download = fetch_url(
                feed["url"],
                timeout=25,
                proxy_fallback=bool(feed.get("proxyFallback")),
            )
            headlines = deduplicate_candidates(
                candidate
                for candidate in source_candidates(download)[: feed["maxHeadlines"]]
                if looks_like_discovery_headline(candidate)
            )
        except Exception as exc:
            print(f"  Discovery feed unavailable: {exc}", file=sys.stderr)
            continue

        source_state = state_sources.setdefault(feed["id"], {"initializedAt": None, "fingerprints": []})
        known = set(source_state.get("fingerprints") or [])
        unseen = [headline for headline in headlines if fingerprint(headline) not in known]
        first_success = not source_state.get("initializedAt")
        selected = unseen[: 0 if first_success else feed["maxNewPerRun"]]
        source_state["fingerprints"] = list(dict.fromkeys(
            (source_state.get("fingerprints") or []) + [fingerprint(item) for item in (headlines if first_success else selected)]
        ))[-2000:]
        if first_success:
            source_state["initializedAt"] = now.isoformat().replace("+00:00", "Z")
        if first_success or selected:
            state_changed = True

        print(
            f"  Found {len(headlines)} headline(s), {len(unseen)} unseen, "
            f"{'baselining only' if first_success else f'resolving {len(selected)}'}"
        )
        if first_success:
            continue

        published_this_feed = 0
        for headline in selected:
            # Official-website auto-registration: the article behind a discovery
            # headline prints an "Official Website" row next to its notification
            # links. Whenever that row holds a real official domain, register it
            # so the monitor starts checking that official website directly.
            register_official_website_from_article(
                headline.url, now=now, dry_run=dry_run, seen=registered_websites,
                proxy_fallback=bool(feed.get("proxyFallback")),
            )
            official = match_official_organization(headline.title, organizations)
            if official is None:
                print(f"  Skipped unmatched headline: {headline.title[:90]}")
                continue
            official_url = canonical_url(official.get("url", ""))
            if not official_url or is_discovery_host(official_url):
                print(f"  Skipped {official.get('id')}: no approved official URL")
                continue
            if official_url not in official_cache:
                try:
                    official_download = fetch_url(
                        official_url,
                        timeout=int(official.get("timeout", 25)),
                        proxy_fallback=bool(official.get("proxyFallback")),
                    )
                    official_downloads[official_url] = official_download
                    official_cache[official_url] = deduplicate_candidates(
                        candidate
                        for candidate in source_candidates(official_download)[: int(official.get("maxLinks", 600))]
                        if looks_like_notice(candidate, official) and not is_discovery_host(candidate.url)
                    )
                except Exception as exc:
                    print(f"  Official source unavailable ({official.get('name')}): {exc}", file=sys.stderr)
                    official_cache[official_url] = []
            matches = official_notices_for_headline(headline.title, official_cache[official_url])
            if not matches and official_url in official_downloads:
                # Page-source rule: the headline is only a lead. If the official
                # website's visible listing did not show the notice, check the
                # raw page source of that official website before dropping it.
                # Applies to every approved official link, existing or added
                # later — no extra configuration needed.
                if official_url not in official_raw_cache:
                    official_raw_cache[official_url] = page_source_candidates(
                        official_downloads[official_url], official
                    )
                raw_matches = official_notices_for_headline(
                    headline.title, official_raw_cache[official_url]
                )
                if raw_matches:
                    print(
                        f"  Listing showed no match; raw page source of {official.get('name')} "
                        f"matched the headline"
                    )
                    matches = raw_matches
            if not matches:
                print(f"  No official notice matched {official.get('name')} for: {headline.title[:80]}")
                continue
            official_source_state = state_sources.setdefault(
                clean_text(official.get("id") or official_url),
                {"initializedAt": now.isoformat().replace("+00:00", "Z"), "fingerprints": []},
            )
            known_official = set(official_source_state.get("fingerprints") or [])
            for official_candidate in matches:
                key = fingerprint(official_candidate)
                if key in known_official:
                    continue
                try:
                    job = job_from_candidate(official_candidate, official, now)
                except Exception as exc:
                    print(f"  Could not build official job from {official_candidate.url}: {exc}", file=sys.stderr)
                    continue
                if any(
                    is_discovery_host(str(job.get(field, ""))) or is_offline_form_url(str(job.get(field, "")))
                    for field in ("pdfLink", "applyLink", "sourceUrl")
                ):
                    print(f"  Dropped job that still pointed at a discovery host: {job.get('title')}")
                    continue
                if offline_vacancy_covered_by_portal(job, offline_pool):
                    print(
                        f"  Skipped offline vacancy already covered by the offline-forms portal: "
                        f"{job.get('title')[:80]}"
                    )
                    continue
                jobs.append(job)
                known_official.add(key)
                added += 1
                published_this_feed += 1
                state_changed = True
            official_source_state["fingerprints"] = list(dict.fromkeys(
                (official_source_state.get("fingerprints") or []) + list(known_official)
            ))[-2000:]
            if official_source_state.get("initializedAt") is None:
                official_source_state["initializedAt"] = now.isoformat().replace("+00:00", "Z")
        print(f"  Published {published_this_feed} official alert(s) from discovery")

    return jobs, added, state_changed


# ---------------------------------------------------------------------------
# Offline application forms (external offline-form portals)
# ---------------------------------------------------------------------------
def is_offline_form_url(url: str) -> bool:
    """True when the URL belongs to one of the configured offline-form portals."""
    return host_name(url) in OFFLINE_FORM_HOSTS


def strip_offline_branding(value: str) -> str:
    """Remove offline-form portal branding from a title or source name."""
    text = clean_text(value)
    for term in OFFLINE_BRAND_TERMS:
        text = re.sub(rf"(?i)(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", " ", text)
    # Leftover host fragments once the brand name itself has been removed.
    text = re.sub(r"(?i)(?<![a-z0-9])www\.\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -|:–—")


def is_pdf_url(url: str) -> bool:
    """True when the URL points at a PDF document (query strings ignored)."""
    return is_direct_pdf_url(url)


def _label_matches(label: str, markers: Iterable[str]) -> bool:
    text = clean_text(label).lower()
    return any(marker in text for marker in markers)


def _pick_offline_document(urls: Iterable[str], *, allow_homepage: bool = False) -> str:
    """Pick the best document URL: portal-hosted PDF first, any PDF second, then
    the first labelled link (e.g. a Google Drive form copy or an official page)."""
    seen: list[str] = []
    for url in urls:
        target = canonical_url(url)
        if not target or target in seen:
            continue
        if is_generic_homepage(target) and not allow_homepage:
            continue
        # A portal homepage/listing is never the application form or notice.
        if is_offline_form_url(target) and not is_pdf_url(target):
            path = urllib.parse.urlsplit(target).path.rstrip("/")
            if path in {"", "/", "/latest-offline-forms", "/latest-job", "/latest-jobs"}:
                continue
        seen.append(target)
    if not seen:
        return ""
    for target in seen:
        if is_offline_form_url(target) and is_pdf_url(target):
            return target
    for target in seen:
        if is_pdf_url(target):
            return target
    return seen[0]


def _offline_page_department(page_text: str) -> str:
    """Extract the recruiting authority printed in an offline vacancy article."""
    labelled = re.search(
        r"(?is)\bDepartment\s*/?\s*Organi[sz]ation\s*[:|–—-]?\s*(.{3,180}?)"
        r"(?=\s+(?:Advertisement|Advt|Post\s+Name|Vacanc(?:y|ies)|Salary|Application\s+Mode)\b)",
        page_text,
    )
    if labelled:
        department = clean_text(labelled.group(1)).strip(" .:|–—-")
        if is_specific_department(department):
            return department[:180]

    intro = re.search(
        r"(?is)([^.!?]{3,220}?)\s+(?:invites?\s+applications?|has\s+(?:recently\s+)?"
        r"(?:released|issued|published))\b",
        page_text,
    )
    if intro:
        department = clean_text(intro.group(1)).rsplit(":-", 1)[-1].strip(" .:|–—-")
        # Remove navigation/page-title text that can precede the actual sentence.
        if len(department) > 140 and " recruitment " in department.lower():
            department = re.split(r"(?i)\brecruitment\s+20\d{2}\b", department)[-1]
            department = department.strip(" .:|–—-")
        if is_specific_department(department) and len(department) <= 180:
            return department
    return ""


# Bumped whenever the article extractor learns a new field, so pages cached by
# an older run are re-read once (v2 added the "Official Website" row).
OFFLINE_EXTRACTOR_VERSION = 2

OFFICIAL_WEBSITE_LABEL_RE = re.compile(
    r"official\s+(?:web\s*site|website|portal|site)|department\s+website|board\s+website",
    re.IGNORECASE,
)


def official_website_links(html_text: str, base_url: str = "") -> list[str]:
    """Return the links published in a page's "Official Website" section.

    Portals print the official website in a table row ("Official Website" in one
    cell, a "Visit Now"/"Click Here" anchor in the next) or as a labelled line.
    Both layouts are read here, because the anchor's own text never contains the
    label. Only links that pass ``looks_like_official_website()`` are returned.
    """
    text = html_text or ""
    found: list[str] = []

    def collect(block: str) -> None:
        for match in re.finditer(r"<a\b[^>]*?href\s*=\s*[\"']([^\"'#]+)[\"']", block, re.IGNORECASE):
            url = canonical_url(urllib.parse.urljoin(base_url, match.group(1)))
            if looks_like_official_website(url) and url not in found:
                found.append(url)

    # 1) Table rows / list items whose visible text carries the label.
    for block_match in re.finditer(
        r"<(tr|li|p|div)\b[^>]*>(.*?)</\1>", text, re.IGNORECASE | re.DOTALL
    ):
        block = block_match.group(2)
        if len(block) > 4000:
            continue
        visible = re.sub(r"<[^>]+>", " ", block)
        if OFFICIAL_WEBSITE_LABEL_RE.search(visible):
            collect(block)

    # 2) Fallback: an anchor that follows the label within the same text run.
    if not found:
        for label_match in OFFICIAL_WEBSITE_LABEL_RE.finditer(text):
            collect(text[label_match.end(): label_match.end() + 400])

    return found


def offline_page_documents(
    page_url: str, download: Download | None = None, proxy_fallback: bool = False
) -> dict[str, str]:
    """Read an offline vacancy page and extract verifiable publishing details.

    In addition to the direct form/notification documents and apply mode, the
    returned mapping carries the recruiting ``department`` plus the application
    ``startDate`` and ``lastDate`` when printed on the article. Those fields let
    the publisher reject expired archives and avoid generic feed-link titles.
    """
    if download is None:
        download = fetch_url(page_url, timeout=25, proxy_fallback=proxy_fallback)
    text = decode_document(download)
    _, parser = parse_html(text, download.url)
    form_candidates: list[str] = []
    notification_candidates: list[str] = []
    website_candidates: list[str] = []
    # Portals label their links either in a table row ("Official Notification" in
    # one cell, "Download" in the next — the parser rewrites those generic
    # labels from the row context) or as a self-describing standalone link
    # ("CLICK HERE FOR OFFICIAL DETAIL", whose own text is rewritten away). Both
    # label variants are tested so either layout resolves to the same documents.
    raw_labels = dict(parser.raw_links)
    for href, label in parser.links:
        url = canonical_url(href)
        if not url:
            continue
        labels = [clean_text(label).lower()]
        raw_label = clean_text(raw_labels.get(href, "")).lower()
        if raw_label and raw_label not in labels:
            labels.append(raw_label)
        filename = urllib.parse.urlsplit(url).path.lower().rsplit("/", 1)[-1]
        pdf = is_pdf_url(url)
        homepage = is_generic_homepage(url)
        if _label_matches(filename, OFFLINE_FORM_FILE_MARKERS) or any(
            (pdf and _label_matches(label_lower, OFFLINE_FORM_LABEL_MARKERS))
            or (
                not pdf
                and (
                    "download application" in label_lower
                    or "proforma" in label_lower
                    or "application format" in label_lower
                )
            )
            for label_lower in labels
        ):
            form_candidates.append(url)
        # The notification link must be identified precisely: a notification-like
        # filename, or a short label with a notification marker that is not the
        # form link and not the "Official Website" row (whose contextual label
        # picks up the notification cell text). This keeps related-job article
        # titles out as well.
        if _label_matches(filename, OFFLINE_NOTIFICATION_FILE_MARKERS) or any(
            _label_matches(label_lower, OFFLINE_NOTIFICATION_LABEL_MARKERS)
            and not _label_matches(label_lower, OFFLINE_FORM_LABEL_MARKERS)
            and "official website" not in label_lower
            and len(label_lower.split()) <= 6
            for label_lower in labels
        ):
            if not homepage:
                notification_candidates.append(url)
        if (
            not pdf
            and not is_offline_form_url(url)
            and any("official website" in label_lower for label_lower in labels)
        ):
            website_candidates.append(url)

    page_text = parser.text.lower()
    intro_modes = [
        match.group(1).lower()
        for match in APPLY_MODE_PHRASE_RE.finditer(page_text)
    ]
    # Only accept "or/and X mode" alternatives that follow an intro sentence, so
    # an unrelated "online mode" mention cannot misclassify the vacancy.
    alt_modes = (
        [match.group(1).lower() for match in APPLY_MODE_ALT_RE.finditer(page_text)]
        if intro_modes
        else []
    )
    modes = intro_modes + alt_modes
    if "offline" in modes or any(
        marker in page_text for marker in OFFLINE_ARTICLE_MARKERS
    ):
        apply_mode = "offline"
    elif "online" in modes:
        apply_mode = "online"
    elif any(marker in page_text for marker in ONLINE_ARTICLE_MARKERS):
        # Checked before the offline dispatch hints: online articles say the
        # form "need not to be sent", which contains an offline hint verbatim.
        apply_mode = "online"
    elif any(marker in page_text for marker in OFFLINE_DISPATCH_MARKERS):
        apply_mode = "offline"
    else:
        apply_mode = ""
    # The "Official Website" row/section of the page: its anchor text is generic
    # ("Visit Now"/"Click Here"), so the label is read from the row context.
    website_candidates.extend(
        url for url in official_website_links(text, download.url)
        if url not in website_candidates
    )
    return {
        "extractorVersion": OFFLINE_EXTRACTOR_VERSION,
        "form": _pick_offline_document(form_candidates),
        "notification": _pick_offline_document(notification_candidates),
        "website": _pick_offline_document(website_candidates, allow_homepage=True),
        "applyMode": apply_mode,
        "department": _offline_page_department(parser.text),
        "startDate": find_labelled_date(
            parser.text,
            r"application\s+form\s+begin|start(?:ing)?\s+(?:from|date)|opening\s+date|applications?\s+open",
        ),
        "lastDate": find_labelled_date(
            parser.text,
            r"application\s+form\s+submission\s+last\s+date|last\s+date(?:\s+for\s+(?:submission|application|receipt|registration))?|closure\s+date|closing\s+date",
        ),
        "pageTitle": strip_offline_branding(parser.page_title),
    }


def mask_offline_url(url: str, redirect: dict[str, str]) -> str:
    """Mask an offline-form portal URL behind redirect.html; other hosts pass through."""
    target = canonical_url(url)
    if not target:
        return ""
    if is_offline_form_url(target):
        redirect.setdefault(redirect_token(target), target)
        return offline_form_link(target)
    return target


def _offline_listing_last_date(title: str) -> str:
    """Last date appended to a table-style offline vacancy listing row."""
    matches = list(re.finditer(DATE_TOKEN, clean_text(title), re.IGNORECASE))
    return parse_date_token(matches[-1].group(0)) if matches else ""


def _offline_listing_title(title: str) -> str:
    """Normalise a vacancy name scraped from an offline-form listing page.

    Table-style listings (department | posts | last date | link) are read as one
    row, so the row's last-date column ends up appended to the vacancy name.
    """
    text = strip_offline_branding(clean_title(title))
    text = re.sub(r"(?i)\s*(?:last date\s*[:\-]?\s*)?" + DATE_TOKEN + r"\s*$", "", text)
    text = re.sub(r"(?i)\s+mentioned\s+in\s+page\s*$", "", text)
    return text.strip(" -|:–—,")


def _offline_keywords(title: str) -> list[str]:
    """Derive fuzzy-match keywords from a scraped offline-form title."""
    return [
        token
        for token in re.findall(r"[a-z0-9]+", clean_text(title).lower())
        if token not in OFFLINE_STOPWORDS
    ]


def load_offline_forms(path: Path = DEFAULT_OFFLINE_FORMS) -> list[dict[str, Any]]:
    """Load the maintained registry of offline-apply forms on the offline-form portals."""
    data = read_json(path, {})
    entries = data.get("offlineForms", []) if isinstance(data, dict) else []
    forms: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = canonical_url(entry.get("url", ""))
        title = clean_text(entry.get("title", ""))
        if not url or not is_offline_form_url(url) or not title:
            continue
        forms.append({
            "title": title,
            "keywords": [
                clean_text(k) for k in (entry.get("keywords") or _offline_keywords(title)) if clean_text(k)
            ],
            "url": url,
            "department": clean_text(entry.get("department") or "Official Recruitment Notice"),
            "type": clean_text(entry.get("type") or "central"),
            "categorySlug": clean_text(entry.get("categorySlug") or "central"),
            "location": clean_text(entry.get("location") or "All India"),
            "lastDate": clean_text(entry.get("lastDate")),
            "curated": True,
        })
    return forms


def offline_form_tokens(entry: dict[str, Any]) -> set[str]:
    text = " ".join([str(entry.get("title", "")), *[str(k) for k in entry.get("keywords", [])]])
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if token not in OFFLINE_STOPWORDS}


def match_offline_form(
    title: str, department: str, forms: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return the best-matching offline-form portal entry for a job, or None."""
    query = offline_form_tokens({"title": f"{title} {department}", "keywords": []})
    if not query:
        return None
    best_entry = None
    best_score = 0.0
    for entry in forms:
        tokens = offline_form_tokens(entry)
        overlap = len(query & tokens)
        if overlap == 0:
            continue
        score = overlap / max(len(query), 1)
        if score > best_score:
            best_score = score
            best_entry = entry
    return best_entry if best_score >= OFFLINE_MATCH_MIN else None


def redirect_token(url: str) -> str:
    """Opaque, stable token that hides the external offline-form URL on the site."""
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:12]


def build_redirect_map(
    forms: list[dict[str, Any]], existing: dict[str, str] | None = None
) -> dict[str, str]:
    mapping = dict(existing or {})
    for entry in forms:
        mapping.setdefault(redirect_token(entry["url"]), entry["url"])
    return mapping


def offline_form_link(entry_url: str) -> str:
    return f"{REDIRECT_PAGE}?f={redirect_token(entry_url)}"


def offline_job_from_entry(
    entry: dict[str, Any],
    now: datetime,
    redirect: dict[str, str],
    page_documents: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an offline-apply vacancy whose form link is masked behind redirect.html.

    When the vacancy page carries the direct offline application-form PDF, that
    PDF becomes the masked download target; likewise the official notification
    document (portal-hosted when no official website copy exists) becomes the
    official-notice link. Everything portal-hosted stays masked so the portal
    URL never appears on the website.
    """
    url = canonical_url(entry["url"])
    documents = _sanitize_offline_documents(
        {str(key): str(value) for key, value in (page_documents or {}).items()}
    )
    form_target = canonical_url(documents.get("form") or "") or url
    if is_generic_homepage(form_target):
        form_target = url
    notification_target = (
        canonical_url(documents.get("notification") or "")
        or canonical_url(documents.get("website") or "")
    )
    if notification_target and is_generic_homepage(notification_target):
        notification_target = ""
    offline_link = mask_offline_url(form_target, redirect)
    pdf_link = mask_offline_url(notification_target or url, redirect)
    is_punjab = clean_text(entry.get("type")) == "punjab"
    stable_id = int(hashlib.sha256(("offline:" + url).encode("utf-8")).hexdigest()[:12], 16)
    discovered = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    raw_title = strip_offline_branding(clean_title(entry["title"]))
    department = clean_text(
        documents.get("department") or entry.get("department") or infer_recruiting_department(raw_title)
    )
    entry_title = official_job_title(raw_title, department)
    if not entry_title:
        raise ValueError("offline vacancy has no specific recruiting department and post name")
    last_date = clean_text(documents.get("lastDate") or entry.get("lastDate"))
    start_date = clean_text(documents.get("startDate"))
    return {
        "id": stable_id,
        "title": entry_title,
        "department": department,
        "vacancies": "See Notification",
        "qualification": "See Official Notification",
        "qualCategory": "Graduate",
        "lastDate": last_date or "See Notification",
        "startDate": start_date or "Newly Published",
        "examDate": "See Official Notification",
        "location": entry["location"],
        "applyMode": "Offline",
        "alertType": "recruitment",
        "badge": "OFFLINE FORM",
        "badgeColor": "bg-slate-700",
        "type": "punjab" if is_punjab else "central",
        "categorySlug": clean_text(
            entry.get("categorySlug") or ("punjab-jobs" if is_punjab else "central")
        ),
        "advtNo": "See Official Notice",
        "feeGen": "See Official Notification",
        "feeSC": "See Official Notification",
        "feeMode": "As Notified",
        "age": "See Official Notification",
        "details": (
            f"Offline application vacancy for {entry_title}. "
            "Download the offline application form and apply before the last date "
            "notified by the recruiting authority."
        ),
        "howToApply": OFFLINE_APPLY_STEPS,
        "pdfLink": pdf_link,
        "applyLink": offline_link,
        "applyLabel": "Download Offline Application Form",
        "offlineFormLink": offline_link,
        "offlineFormName": (
            "Download Offline Application Form (PDF)"
            if documents.get("form")
            else "Download Offline Application Form"
        ),
        "sourceName": department,
        "sourceUrl": url,
        "publishedAt": "",
        "discoveredAt": discovered,
        "isExtension": False,
        "extensionDate": "",
        "automated": True,
    }


def gather_offline_forms_pool(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge the maintained registry with links scraped from configured offline-form listing sources.

    The portal's own listing is authoritative for the vacancy name: a scraped
    entry refreshes the title/keywords of a registry entry for the same URL
    while keeping the registry's curated department/type/location.
    """
    pool: dict[str, dict[str, Any]] = {}
    registry_urls: set[str] = set()
    for entry in load_offline_forms():
        pool[entry["url"]] = entry
        registry_urls.add(entry["url"])
    for source in config.get("sources", []):
        if source.get("role") != "offline-forms" or source.get("enabled", True) is False:
            continue
        source_url = canonical_url(source.get("url", ""))
        if not source_url:
            continue
        try:
            download = fetch_url(
                source_url,
                timeout=int(source.get("timeout", 25)),
                proxy_fallback=bool(source.get("proxyFallback")),
            )
            for cand in source_candidates(download)[: int(source.get("maxLinks", 600))]:
                cand_url = canonical_url(cand.url)
                if not cand_url or not is_offline_form_url(cand_url):
                    continue
                # The portal's own branding must never reach a published alert.
                listing_last_date = _offline_listing_last_date(cand.title)
                title = _offline_listing_title(cand.title)
                if len(title) < 8 or is_junk_job_title(title):
                    continue
                if cand_url in registry_urls:
                    registry_entry = pool[cand_url]
                    registry_entry["title"] = title
                    registry_entry["keywords"] = _offline_keywords(title)
                    if listing_last_date:
                        registry_entry["lastDate"] = listing_last_date
                    continue
                pool.setdefault(cand_url, {
                    "title": title,
                    "keywords": _offline_keywords(title),
                    "url": cand_url,
                    "department": infer_recruiting_department(title),
                    "type": clean_text(source.get("type") or "central"),
                    "categorySlug": clean_text(source.get("categorySlug") or "central"),
                    "location": clean_text(source.get("location") or "All India"),
                    "lastDate": listing_last_date,
                    "curated": False,
                })
        except Exception as exc:
            print(
                f"  Offline-forms listing unavailable ({source.get('name')}): {exc}",
                file=sys.stderr,
            )
    return list(pool.values())


def _redirect_target_for_link(
    link: str, redirect: dict[str, str], existing_map: dict[str, str]
) -> str:
    """Resolve a masked redirect.html link back to its target URL ('' if not masked)."""
    match = re.search(
        r"redirect\.html\?f=([0-9a-f]{12})", clean_text(link), re.IGNORECASE
    )
    if not match:
        return ""
    token = match.group(1)
    return canonical_url(existing_map.get(token) or redirect.get(token) or "")


def _dated_notice_is_active(last_date: str, now: datetime) -> bool | None:
    """True/False for a readable deadline; None when the deadline is unknown."""
    parsed = parse_date_token(clean_text(last_date))
    if not parsed:
        return None
    deadline = datetime.strptime(parsed, "%d-%m-%Y").date()
    return deadline >= now.date()


def _sanitize_offline_documents(documents: dict[str, Any]) -> dict[str, str]:
    """Drop portal homepages and site roots that slipped into cached documents."""
    cleaned: dict[str, Any] = {
        str(key): (value if key == "extractorVersion" else str(value or ""))
        for key, value in documents.items()
    }
    website = canonical_url(cleaned.get("website") or "")
    if website and is_offline_form_url(website):
        cleaned["website"] = ""
    form = canonical_url(cleaned.get("form") or "")
    if form and is_generic_homepage(form):
        cleaned["form"] = ""
    notification = canonical_url(cleaned.get("notification") or "")
    if notification and is_generic_homepage(notification):
        cleaned["notification"] = ""
    if notification and is_offline_form_url(notification) and not is_pdf_url(notification):
        path = urllib.parse.urlsplit(notification).path.rstrip("/")
        if path in {"", "/", "/latest-offline-forms", "/latest-job", "/latest-jobs"}:
            cleaned["notification"] = ""
    return cleaned


def _offline_documents_need_refresh(documents: dict[str, Any]) -> bool:
    """True when a cached extraction is stale and the page must be re-read.

    Stale means the cached form link is a site homepage, or the entry was cached
    by an older extractor that did not yet read the "Official Website" row.
    """
    try:
        cached_version = int(documents.get("extractorVersion", 1))
    except (TypeError, ValueError):
        cached_version = 1
    if cached_version < OFFLINE_EXTRACTOR_VERSION:
        return True
    form = canonical_url(documents.get("form") or "")
    return bool(form and is_generic_homepage(form))


def process_offline_forms(
    config: dict[str, Any],
    jobs: list[dict[str, Any]],
    state: dict[str, Any],
    now: datetime,
    dry_run: bool = False,
    pool: list[dict[str, Any]] | None = None,
) -> tuple[int, bool]:
    """Publish offline-apply vacancies with a masked offline application form link.

    Returns (added, changed). The offline-form portals are used for offline-apply
    vacancies only: entries whose portal page says online-apply are skipped, and
    online vacancies come from the other discovery feeds. Portal URLs never
    appear in the visible site links; they are only recorded in
    data/offline-redirects.json and resolved by redirect.html. The offline form
    link points at the direct application-form PDF from the vacancy page
    whenever the page provides one, and the official notice link points at the
    notification document from the same page (or the official website the page
    links) when the job has no official-website copy of it.
    """
    if pool is None:
        pool = gather_offline_forms_pool(config)
    if not pool:
        return 0, False
    # Any configured offline-form portal may opt into mirror-fetching its
    # listing and vacancy pages when the portal refuses direct connections.
    offline_proxy_fallback = any(
        bool(source.get("proxyFallback"))
        for source in config.get("sources", [])
        if source.get("role") == "offline-forms" and source.get("enabled", True)
    )
    existing_redirects = read_json(DEFAULT_OFFLINE_REDIRECTS, {})
    existing_map = (
        existing_redirects.get("redirects", {})
        if isinstance(existing_redirects, dict)
        else {}
    )
    redirect = build_redirect_map(pool, existing_map)

    # Per-page extraction cache persisted in state, so each vacancy page is
    # scraped for its direct form/notification PDF only once. Failed extractions
    # are not cached and are retried on a later run.
    page_cache = state.setdefault("offlinePageDocuments", {})
    if not isinstance(page_cache, dict):
        page_cache = {}
        state["offlinePageDocuments"] = page_cache
    cache_before = len(page_cache)

    # Official-website auto-registration: every notification page read here is
    # checked for its "Official Website" row. When that row points at a genuine
    # official domain, the link is stored in data/notification-source-links.json
    # so the monitor starts checking that official website (and, when its listing
    # shows nothing new, its raw page source) from the next run — no manual
    # configuration needed.
    configured_source_urls = {
        canonical_url(source.get("url", ""))
        for source in (config.get("sources") or [])
        if isinstance(source, dict)
    }
    seen_official_websites: set[str] = set()

    def note_official_website(documents: dict[str, Any]) -> None:
        website = canonical_url(documents.get("website", "") if isinstance(documents, dict) else "")
        if not website or website in seen_official_websites:
            return
        seen_official_websites.add(website)
        try:
            register_official_websites_from_documents(
                documents,
                config_urls=configured_source_urls,
                now=now,
                dry_run=dry_run,
            )
        except Exception as exc:  # never let registration break a monitoring run
            print(f"  Could not register official website {website}: {exc}", file=sys.stderr)

    def page_documents(page_url: str) -> dict[str, str]:
        key = canonical_url(page_url)
        cached = page_cache.get(key)
        required_fields = {"form", "notification", "website", "applyMode", "department", "lastDate"}
        if (
            isinstance(cached, dict)
            and required_fields.issubset(cached)
            and not _offline_documents_need_refresh(cached)
        ):
            documents = _sanitize_offline_documents(cached)
            note_official_website(documents)
            return documents
        try:
            documents = _sanitize_offline_documents(
                offline_page_documents(key, proxy_fallback=offline_proxy_fallback)
            )
        except Exception as exc:
            print(
                f"  Offline page document extraction failed ({key}): {exc}",
                file=sys.stderr,
            )
            if isinstance(cached, dict):
                return _sanitize_offline_documents(cached)
            return {
                "extractorVersion": OFFLINE_EXTRACTOR_VERSION,
                "form": "", "notification": "", "website": "", "applyMode": "",
                "department": "", "startDate": "", "lastDate": "", "pageTitle": "",
            }
        page_cache[key] = documents
        note_official_website(documents)
        return dict(documents)

    added = 0
    changed = False

    # Clean-up passes over already-published alerts:
    # 1) drop offline alerts whose titles are listing-page chrome rather than
    #    real vacancies (nav/footer links that slipped through earlier runs);
    # 2) strip stale offline-form fields from non-offline jobs (online-apply
    #    vacancies must not carry portal links);
    # 3) drop offline alerts whose own portal page now says online-apply.
    kept: list[dict[str, Any]] = []
    for job in jobs:
        if (
            str(job.get("applyMode", "")).lower().startswith("offline")
            and clean_title(str(job.get("title", ""))).lower()
            in OFFLINE_LISTING_JUNK_TITLES
        ):
            changed = True
            continue
        if not str(job.get("applyMode", "")).lower().startswith("offline"):
            if job.get("offlineFormLink") or job.get("offlineFormName"):
                job.pop("offlineFormLink", None)
                job.pop("offlineFormName", None)
                if clean_text(job.get("applyLabel")) == "Download Offline Application Form":
                    job["applyLabel"] = "Open Official Application"
                changed = True
            kept.append(job)
            continue
        source_url = canonical_url(job.get("sourceUrl") or "")
        documents: dict[str, str] = {}
        if source_url and is_offline_form_url(source_url) and not is_pdf_url(source_url):
            documents = page_documents(source_url)
            if documents.get("applyMode") == "online":
                print(
                    f"  Dropped online-apply vacancy mislabelled as offline: {job.get('title')}"
                )
                changed = True
                continue

        department = clean_text(
            documents.get("department")
            or job.get("department")
            or infer_recruiting_department(job.get("title", ""))
        )
        if not is_specific_department(department):
            department = infer_recruiting_department(job.get("title", ""))
        specific_title = official_job_title(job.get("title", ""), department)
        if not specific_title:
            print(f"  Dropped vacancy without a specific department/post name: {job.get('title')}")
            changed = True
            continue
        if job.get("department") != department or job.get("title") != specific_title:
            job["department"] = department
            job["title"] = specific_title
            changed = True
        verified_last_date = clean_text(documents.get("lastDate") or job.get("lastDate"))
        if verified_last_date and verified_last_date != "See Notification" and job.get("lastDate") != verified_last_date:
            job["lastDate"] = verified_last_date
            changed = True
        if _dated_notice_is_active(job.get("lastDate", ""), now) is False:
            print(f"  Dropped expired offline vacancy: {job.get('title')}")
            changed = True
            continue
        kept.append(job)
    jobs[:] = kept

    existing_titles = {clean_text(job.get("title", "")).lower() for job in jobs}
    jobs_by_source = {
        canonical_url(job.get("sourceUrl") or ""): job
        for job in jobs
        if job.get("sourceUrl")
    }
    for entry in pool:
        entry_url = canonical_url(entry["url"])
        documents = page_documents(entry_url)
        if documents.get("applyMode") == "online":
            # Online-apply vacancies come from the other discovery feeds, never
            # from the offline-form portal.
            print(
                f"  Skipped online-apply vacancy on the offline-forms portal: "
                f"{clean_title(entry['title'])[:80]}"
            )
            continue

        verified_entry = dict(entry)
        verified_entry["department"] = clean_text(
            documents.get("department")
            or entry.get("department")
            or infer_recruiting_department(entry.get("title", ""))
        )
        if not is_specific_department(verified_entry["department"]):
            verified_entry["department"] = infer_recruiting_department(entry.get("title", ""))
        verified_entry["lastDate"] = clean_text(
            documents.get("lastDate") or entry.get("lastDate")
        )
        if not official_job_title(verified_entry.get("title", ""), verified_entry["department"]):
            print(
                f"  Skipped vacancy without a specific department/post name: "
                f"{clean_title(entry['title'])[:80]}"
            )
            continue
        active = _dated_notice_is_active(verified_entry["lastDate"], now)
        if active is False:
            print(f"  Skipped expired offline vacancy: {clean_title(entry['title'])[:80]}")
            continue
        if active is None and not verified_entry.get("curated"):
            print(
                f"  Skipped unverified offline vacancy without a readable last date: "
                f"{clean_title(entry['title'])[:80]}"
            )
            continue

        specific_title = official_job_title(
            verified_entry["title"], verified_entry["department"]
        )
        existing = jobs_by_source.get(entry_url)
        if existing:
            form_target = canonical_url(documents.get("form") or "") or entry_url
            if is_generic_homepage(form_target):
                form_target = entry_url
            notification_target = (
                canonical_url(documents.get("notification") or "")
                or canonical_url(documents.get("website") or "")
            )
            if notification_target and is_generic_homepage(notification_target):
                notification_target = ""
            offline_link = mask_offline_url(form_target, redirect)
            pdf_link = mask_offline_url(notification_target or entry_url, redirect)
            for field, value in (
                ("title", specific_title),
                ("department", verified_entry["department"]),
                ("lastDate", verified_entry["lastDate"] or existing.get("lastDate")),
                ("startDate", documents.get("startDate") or existing.get("startDate")),
                ("offlineFormLink", offline_link),
                ("applyLink", offline_link),
                ("pdfLink", pdf_link),
                ("applyLabel", "Download Offline Application Form"),
                (
                    "offlineFormName",
                    "Download Offline Application Form (PDF)"
                    if documents.get("form")
                    else "Download Offline Application Form",
                ),
            ):
                if value and existing.get(field) != value:
                    # Never replace a real notification PDF with a weaker page.
                    if field == "pdfLink":
                        current_target = _redirect_target_for_link(
                            str(existing.get("pdfLink") or ""), redirect, existing_map
                        ) or str(existing.get("pdfLink") or "")
                        new_target = _redirect_target_for_link(
                            str(value), redirect, existing_map
                        ) or str(value)
                        if is_direct_pdf_url(current_target) and not is_direct_pdf_url(new_target):
                            continue
                    existing[field] = value
                    changed = True
            continue
        title_lower = specific_title.lower()
        if title_lower in existing_titles:
            continue
        jobs.append(offline_job_from_entry(verified_entry, now, redirect, documents))
        existing_titles.add(title_lower)
        added += 1
        changed = True

    # Attach the (masked) offline application form to every offline-apply job and
    # upgrade already-published alerts whose link still resolves to the vacancy
    # page to the direct application-form PDF / notification document.
    for job in jobs:
        if not str(job.get("applyMode", "")).lower().startswith("offline"):
            continue
        if not job.get("offlineFormLink"):
            entry = match_offline_form(
                job.get("title", ""), job.get("department", ""), pool
            )
            if entry:
                documents = page_documents(entry["url"])
                form_target = canonical_url(documents.get("form") or "") or canonical_url(
                    entry["url"]
                )
                job["offlineFormLink"] = mask_offline_url(form_target, redirect)
                job["offlineFormName"] = (
                    "Download Offline Application Form (PDF)"
                    if documents.get("form")
                    else "Download Offline Application Form"
                )
                job["applyLabel"] = "Download Offline Application Form"
                changed = True
            continue

        offline_link = clean_text(job.get("offlineFormLink"))
        target = _redirect_target_for_link(offline_link, redirect, existing_map)
        if target and is_offline_form_url(target):
            if is_pdf_url(target):
                continue  # Already points at a direct document.
            page_url = target
        else:
            source_url = canonical_url(job.get("sourceUrl") or "")
            if (
                source_url
                and is_offline_form_url(source_url)
                and not is_pdf_url(source_url)
            ):
                page_url = source_url
            else:
                continue
        documents = page_documents(page_url)
        form_target = canonical_url(documents.get("form") or "")
        notification_target = (
            canonical_url(documents.get("notification") or "")
            or canonical_url(documents.get("website") or "")
        )
        if form_target:
            new_link = mask_offline_url(form_target, redirect)
            if new_link and new_link != offline_link:
                if clean_text(job.get("applyLink")) == offline_link:
                    job["applyLink"] = new_link
                job["offlineFormLink"] = new_link
                job["offlineFormName"] = "Download Offline Application Form (PDF)"
                changed = True
        if notification_target:
            current_pdf = clean_text(job.get("pdfLink"))
            current_target = _redirect_target_for_link(
                current_pdf, redirect, existing_map
            )
            current_is_page = bool(
                current_target
                and is_offline_form_url(current_target)
                and not is_pdf_url(current_target)
            )
            if not current_pdf or current_is_page:
                new_pdf = mask_offline_url(notification_target, redirect)
                if new_pdf and new_pdf != current_pdf:
                    job["pdfLink"] = new_pdf
                    changed = True

    if len(page_cache) > cache_before:
        changed = True

    if changed and not dry_run:
        write_json(DEFAULT_OFFLINE_REDIRECTS, {
            "version": 1,
            "updatedAt": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "redirects": redirect,
        })
    print(
        f"Finished: {added} offline form alert(s) published, "
        f"{len(redirect)} redirect token(s) registered."
    )
    return added, changed


NOTIFICATION_SOURCE_LINKS = ROOT / "data" / "notification-source-links.json"


def looks_like_official_website(url: str) -> bool:
    """True when a URL found in an article's "Official Website" row is usable.

    Discovery-feed / offline-form article pages publish a table row labelled
    "Official Website". That row is the recruiting board's own site, so it may be
    registered as a monitor source — but only when it is a real official domain
    and not another job blog, a social/telegram link, a shortener or the portal
    itself.
    """
    normalized = canonical_url(url)
    if not normalized or is_pdf_url(normalized):
        return False
    if is_discovery_host(normalized) or is_offline_form_url(normalized):
        return False
    host = host_name(normalized)
    if not host or host in NON_OFFICIAL_WEBSITE_HOSTS:
        return False
    if any(host == blocked or host.endswith(f".{blocked}") for blocked in NON_OFFICIAL_WEBSITE_HOSTS):
        return False
    return host.endswith(OFFICIAL_WEBSITE_DOMAIN_SUFFIXES)


def register_official_website_link(
    url: str,
    name: str = "",
    department: str = "",
    *,
    path: Path | None = None,
    config_urls: set[str] | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> bool:
    """Add an official website found on a discovery article as a monitor source.

    The link is appended to data/notification-source-links.json, which
    ``additional_link_sources()`` turns into a normal source on the next run — so
    the official listing (and, when it shows nothing new, its raw page source) is
    checked automatically from then on. Returns True when a new link was stored.
    """
    path = path or NOTIFICATION_SOURCE_LINKS
    normalized = canonical_url(url)
    if not looks_like_official_website(normalized):
        return False
    if config_urls and normalized in config_urls:
        return False

    registry = read_json(path, {"version": 1, "links": []})
    if not isinstance(registry, dict) or not isinstance(registry.get("links"), list):
        registry = {"version": 1, "links": []}
    known = {
        canonical_url(entry.get("url", "")) if isinstance(entry, dict) else canonical_url(entry)
        for entry in registry["links"]
    }
    if normalized in known:
        return False

    host = host_name(normalized)
    label = strip_discovery_branding(clean_text(name)) or host
    org = strip_discovery_branding(clean_text(department)) or label
    registry["links"].append({
        "url": normalized,
        "name": label,
        "department": org,
        "type": "central",
        "categorySlug": "central",
        "location": "All India",
        "noticeTypes": sorted(DEFAULT_NOTICE_TYPES),
        "addedBy": "discovery-official-website",
        "addedAt": (now or datetime.now(timezone.utc)).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z"),
    })
    print(f"  Registered official website from the notification page: {normalized}")
    if not dry_run:
        write_json(path, registry)
    return True


def register_official_websites_from_documents(
    documents: dict[str, Any],
    *,
    path: Path | None = None,
    config_urls: set[str] | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> bool:
    """Register the "Official Website" link extracted from an article page."""
    if not isinstance(documents, dict):
        return False
    return register_official_website_link(
        documents.get("website", ""),
        name=documents.get("pageTitle", ""),
        department=documents.get("department", ""),
        path=path,
        config_urls=config_urls,
        now=now,
        dry_run=dry_run,
    )


def register_official_website_from_article(
    article_url: str,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
    seen: set[str] | None = None,
    config_urls: set[str] | None = None,
    proxy_fallback: bool = False,
) -> bool:
    """Read a discovery-feed article and register its "Official Website" link.

    Discovery articles publish the recruiting board's own website next to the
    notification/apply rows. Reading it here means a board that is not yet
    configured becomes a monitored official source automatically — the notices
    themselves are still only ever published from that official website.
    """
    url = canonical_url(article_url)
    if not url or (seen is not None and url in seen):
        return False
    if seen is not None:
        seen.add(url)
    if not (is_discovery_host(url) or is_offline_form_url(url)) or is_pdf_url(url):
        return False
    try:
        download = fetch_url(url, timeout=20, proxy_fallback=proxy_fallback)
        websites = official_website_links(decode_document(download), download.url)
    except Exception as exc:
        print(f"  Could not read the article for its official website ({url}): {exc}", file=sys.stderr)
        return False
    registered = False
    for website in websites:
        if register_official_website_link(
            website, name=host_name(website), now=now, dry_run=dry_run, config_urls=config_urls
        ):
            registered = True
    return registered


def additional_link_sources(path: Path | None = None) -> list[dict[str, Any]]:
    """Turn user-added and auto-discovered notification URLs into monitor sources.

    Each generated source goes through the same per-source pipeline as the
    configured sources, so the page-source rule (after checking the official
    website, if no new job notification is found, check the raw page source of
    that official website) applies to user-added links too, with no extra
    configuration.
    """
    path = path or NOTIFICATION_SOURCE_LINKS
    registry = read_json(path, {"links": []})
    links = registry.get("links", []) if isinstance(registry, dict) else []
    generated: list[dict[str, Any]] = []
    for entry in links:
        if isinstance(entry, str):
            entry = {"url": entry}
        if not isinstance(entry, dict):
            continue
        url = canonical_url(entry.get("url", ""))
        if not url or is_discovery_host(url):
            continue
        host = urllib.parse.urlsplit(url).netloc.removeprefix("www.")
        source_id = "custom-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        stored_department = clean_text(entry.get("department") or entry.get("name") or "")
        # A registry entry can hold the bare domain it auto-discovered (e.g.
        # "ibps.in"). Resolve the authority behind that host instead of feeding
        # a website address into the pipeline as a department name.
        if not is_specific_department(stored_department):
            stored_department = organization_from_host(url) or host
        stored_name = clean_text(entry.get("name") or "")
        if is_website_domain(stored_name) or not stored_name:
            # The label shown on a card is never a URL; prefer the authority name.
            stored_name = stored_department or host
        source = {
            "id": source_id,
            "name": stored_name or "Additional job notification source",
            "department": stored_department,
            "url": url,
            "type": clean_text(entry.get("type") or "central").lower(),
            "categorySlug": clean_text(entry.get("categorySlug") or "central"),
            "location": clean_text(entry.get("location") or "All India"),
            "noticeTypes": entry.get("noticeTypes") or sorted(DEFAULT_NOTICE_TYPES),
            "bootstrapCount": int(entry.get("bootstrapCount", 1)),
            "maxNewPerRun": int(entry.get("maxNewPerRun", 8)),
            "includeKeywords": entry.get("includeKeywords", []),
            "excludeKeywords": entry.get("excludeKeywords", []),
        }
        # Mirror opt-in and timeouts configured on the registry entry, so a
        # registered official site that refuses datacenter connections is still
        # readable. Mirrors are transport only: every link parsed from them keeps
        # the official URL and no mirror host is ever published.
        if entry.get("proxyFallback"):
            source["proxyFallback"] = True
        for key in ("timeout", "detailTimeout"):
            if key in entry:
                source[key] = int(entry[key])
        generated.append(source)
    return generated


def run(config_path: Path, output_path: Path, state_path: Path, dry_run: bool = False) -> int:
    config = read_json(config_path, {})
    if not isinstance(config.get("sources"), list):
        raise RuntimeError(f"{config_path} must contain a sources array")

    configured_urls = {canonical_url(source.get("url", "")) for source in config["sources"]}
    # The repository-level user registry augments the repository's normal config.
    # A caller supplying a temporary/custom config expects that config to remain
    # isolated (not silently mixed with the live site's additional sources).
    extra_sources = (
        additional_link_sources()
        if config_path.resolve() == DEFAULT_CONFIG.resolve()
        else []
    )
    for source in extra_sources:
        if source["url"] not in configured_urls:
            config["sources"].append(source)
            configured_urls.add(source["url"])

    output = read_json(output_path, {"version": 1, "updatedAt": None, "jobs": []})
    state = read_json(state_path, {"version": 1, "sources": {}})
    jobs = list(output.get("jobs") or [])
    state_sources = state.setdefault("sources", {})
    now = datetime.now(timezone.utc).replace(microsecond=0)
    jobs_changed = sanitize_published_jobs(jobs, now)
    if refresh_badges(jobs, now, int(config.get("newBadgeHours", 72))):
        jobs_changed = True
    state_changed = False
    added = 0
    successful_sources = 0

    for source in config["sources"]:
        if source.get("enabled", True) is False:
            continue
        if source.get("role") == "discovery" or source.get("role") == "offline-forms" or is_discovery_host(
            source.get("url", "")
        ):
            continue
        source_id = clean_text(source.get("id"))
        source_url = canonical_url(source.get("url", ""))
        if not source_id or not source_url:
            print("Skipping a source without a valid id/url", file=sys.stderr)
            continue
        print(f"Checking {source.get('name', source_id)}: {source_url}")
        proxy_fallback = bool(source.get("proxyFallback"))
        try:
            download = fetch_url(
                source_url,
                timeout=int(source.get("timeout", 25)),
                proxy_fallback=proxy_fallback,
            )
            discovered = deduplicate_candidates(
                candidate
                for candidate in source_candidates(download)[: int(source.get("maxLinks", 600))]
                if looks_like_notice(candidate, source)
            )
        except Exception as exc:
            if record_source_failure(state, source_id, now, str(exc)):
                state_changed = True
            failures_in_a_row = int(
                (state.get("sourceHealth", {}).get(source_id, {}) or {}).get("consecutiveFailures") or 0
            )
            print(
                f"  Source unavailable; keeping existing data "
                f"({failures_in_a_row} consecutive failed run(s)): {exc}",
                file=sys.stderr,
            )
            if failures_in_a_row >= 2:
                print(
                    f"  WARNING: {source.get('name', source_id)} has been unreachable for "
                    f"{failures_in_a_row} consecutive runs — its alerts are not being updated. "
                    f"Recorded in data/seen-notices.json (sourceHealth)."
                )
            continue

        successful_sources += 1
        if record_source_success(state, source_id, now):
            state_changed = True
        source_state = state_sources.setdefault(source_id, {"initializedAt": None, "fingerprints": []})
        known = set(source_state.get("fingerprints") or [])
        unseen = [candidate for candidate in discovered if fingerprint(candidate) not in known]
        if not unseen:
            # Page-source rule (mandatory, runs on every workflow run for every
            # official website link — existing or newly added, no extra config):
            # after checking the official website, if no new job notification
            # was found in the listing, check the page source of the official
            # website and publish only links found there.
            page_source_extras = page_source_fallback_candidates(
                download, discovered, known, source
            )
            if page_source_extras:
                print(
                    f"  Listing showed no new notification; raw page source of the "
                    f"official website exposes {len(page_source_extras)} additional "
                    f"notice link(s)"
                )
                discovered = deduplicate_candidates([*discovered, *page_source_extras])
                unseen = [
                    candidate
                    for candidate in discovered
                    if fingerprint(candidate) not in known
                ]
        first_success = not source_state.get("initializedAt")
        if first_success:
            ranked = select_bootstrap_candidates(unseen, source, now)
            selected = ranked[: max(0, int(source.get("bootstrapCount", 1)))]
            source_state["fingerprints"] = [fingerprint(candidate) for candidate in discovered][-2000:]
            source_state["initializedAt"] = now.isoformat().replace("+00:00", "Z")
            state_changed = True
        else:
            selected = unseen[: max(0, int(source.get("maxNewPerRun", 5)))]
            if selected:
                merged_fingerprints = list(source_state.get("fingerprints") or []) + [
                    fingerprint(candidate) for candidate in selected
                ]
                source_state["fingerprints"] = list(dict.fromkeys(merged_fingerprints))[-2000:]
                state_changed = True

        print(f"  Found {len(discovered)} supported alert link(s), {len(unseen)} unseen, publishing {len(selected)}")
        for candidate in selected:
            try:
                job = job_from_candidate(candidate, source, now)
            except Exception as exc:
                print(f"  Could not build job from {candidate.url}: {exc}", file=sys.stderr)
                continue
            jobs.append(job)
            added += 1
            jobs_changed = True
            print(f"  Published: {clean_text(job.get('title', ''))[:90]}")

        if not first_success:
            if refresh_published_source_jobs(jobs, discovered, known, source, now):
                jobs_changed = True
            caught_up = publish_unpublished_seen_notices(jobs, discovered, known, source, now)
            if caught_up:
                added += caught_up
                jobs_changed = True

    # The offline-form portal is the single source for offline-apply vacancies;
    # its pool is built once and shared with the discovery-feed pipeline, which
    # uses it to skip offline vacancies the portal already covers.
    offline_source_active = any(
        source.get("role") == "offline-forms"
        for source in config.get("sources", [])
    )
    offline_pool: list[dict[str, Any]] = []
    if offline_source_active:
        offline_pool = gather_offline_forms_pool(config)

    discovery_jobs, discovery_added, discovery_state_changed = process_discovery_feeds(
        approved_official_organizations(config["sources"]),
        state,
        now,
        dry_run,
        offline_pool,
    )
    if discovery_jobs:
        jobs.extend(discovery_jobs)
        added += discovery_added
        jobs_changed = True
    if discovery_state_changed:
        state_changed = True

    if offline_source_active:
        offline_added, offline_changed = process_offline_forms(
            config, jobs, state, now, dry_run, offline_pool
        )
        if offline_added:
            added += offline_added
            jobs_changed = True
        if offline_changed:
            # Offline processing also mutates jobs (direct form/notification PDF
            # link upgrades, junk-alert purges), so the jobs file must be
            # rewritten even when no new alert was added this run.
            state_changed = True
            jobs_changed = True

    # Resolve any stored notice whose department/title still carries a bare
    # website link ("sbi.gov.in — Result") into the real authority name, and
    # move stored notices to their correct column as classification tightens.
    if normalize_stored_departments(jobs):
        jobs_changed = True
    if reclassify_stored_jobs(jobs):
        jobs_changed = True
    if apply_extensions(jobs):
        jobs_changed = True
    if strip_internal_job_fields(jobs):
        jobs_changed = True
    # Re-run after refresh/backfill so a newly-read expired last date is removed
    # and placeholder fields filled from stored notice text are persisted.
    if sanitize_published_jobs(jobs, now):
        jobs_changed = True

    if jobs_changed:
        unique_jobs: list[dict[str, Any]] = []
        known_job_keys: set[tuple[str, str]] = set()
        for job in sorted(jobs, key=lambda item: item.get("discoveredAt", ""), reverse=True):
            key = (clean_text(job.get("title")).lower(), canonical_url(job.get("pdfLink", "")))
            if key not in known_job_keys:
                known_job_keys.add(key)
                unique_jobs.append(job)
        jobs = unique_jobs[: max(1, int(config.get("maxStoredJobs", 100)))]
        output = {
            "version": 1,
            "updatedAt": now.isoformat().replace("+00:00", "Z"),
            "jobs": jobs,
        }

    print(
        f"Finished: {successful_sources} source(s) available, {added} new alert(s), "
        f"{len(jobs)} automatic alert(s) stored."
    )
    if dry_run:
        print("Dry run: no files written.")
        return 0
    if jobs_changed:
        write_json(output_path, output)
    elif not output_path.exists():
        write_json(output_path, output)
    if state_changed:
        write_json(state_path, state)
    elif not state_path.exists():
        write_json(state_path, state)
    return 0


def capture_protected_layout(
    root: Path = ROOT, protected_paths: Iterable[str] = PROTECTED_LAYOUT_PATHS
) -> dict[str, bytes]:
    """Capture the visual website files before an automation run."""
    snapshot: dict[str, bytes] = {}
    for relative in protected_paths:
        path = root / relative
        files = path.rglob("*") if path.is_dir() else (path,)
        for file_path in files:
            if file_path.is_file():
                snapshot[file_path.relative_to(root).as_posix()] = file_path.read_bytes()
    return snapshot


def restore_protected_layout(
    snapshot: dict[str, bytes],
    root: Path = ROOT,
    protected_paths: Iterable[str] = PROTECTED_LAYOUT_PATHS,
) -> None:
    """Restore protected files and remove layout files created during a run."""
    current = capture_protected_layout(root, protected_paths)
    for relative in current.keys() - snapshot.keys():
        (root / relative).unlink()
    for relative, content in snapshot.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update automatic recruitment, admission, answer-key, result and corrigendum alerts")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    layout_snapshot = capture_protected_layout()
    try:
        try:
            result = run(args.config, args.output, args.state, args.dry_run)
        finally:
            if capture_protected_layout() != layout_snapshot:
                restore_protected_layout(layout_snapshot)
                raise RuntimeError(
                    "Layout protection stopped and reverted an attempted change to index.html or assets/"
                )
        return result
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
