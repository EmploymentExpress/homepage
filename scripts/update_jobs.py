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
DEFAULT_OUTPUT = ROOT / "data" / "auto-jobs.json"
DEFAULT_STATE = ROOT / "data" / "seen-notices.json"
DISCOVERY_HOSTS = {"haryanajobs.in", "rozgarnews.com"}
DISCOVERY_BRAND_TERMS = ("haryanajobs", "haryana jobs", "rozgarnews", "rozgar news")

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
    "admission notice",
    "admission notification",
    "admission form",
    "admissions open",
    "admission to class",
    "online admission",
    "selection test",
    "jnvst",
    "lateral entry admission",
)
ANSWER_KEY_TERMS = ("answer key", "response key", "provisional key", "final key")
RESULT_TERMS = (
    "final result",
    "written test result",
    "result for",
    "result of",
    "merit list",
    "selection list",
    "selected candidates",
    "shortlisted candidates",
    "recommendation list",
)
UPDATE_TERMS = ("corrigendum", "addendum")
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
    "admit card",
    "examination schedule",
    "exam schedule",
    "interview schedule",
    "objection notice",
    "tender",
    "auction",
    "seniority list",
    "transfer order",
    "promotion order",
    "syllabus",
)
DEFAULT_NOTICE_TYPES = {"recruitment", "admission", "answer-key", "result", "corrigendum"}
GENERIC_TITLES = {
    "recruitment",
    "recruitments",
    "advertisement",
    "advertisements",
    "careers",
    "career",
    "apply online",
    "click here",
    "read more",
    "view more",
    "notification",
    "notifications",
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


class NoticeHTMLParser(HTMLParser):
    """Small, forgiving HTML extractor for links, metadata, and visible text."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self.page_title = ""
        self.description = ""
        self.visible_parts: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []
        self._anchor_context: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._hidden_depth = 0

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
            self._anchor_href = None
            self._anchor_parts = []
            self._anchor_context = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if not self._hidden_depth:
            text = clean_text(data)
            if text:
                self.visible_parts.append(text)
                if self._anchor_href:
                    self._anchor_parts.append(text)

    @property
    def text(self) -> str:
        return clean_text(" ".join(self.visible_parts))[:MAX_TEXT_LENGTH]


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_title(value: str) -> str:
    title = clean_text(value)
    title = re.sub(r"(?i)(?:!!\s*)?\bnew\b(?:\s*!!)?", " ", title)
    title = re.sub(
        r"(?i)^\s*(?:click here(?:\s+(?:to|for))?|download)\s*[-:–—]*\s*",
        "",
        title,
    )
    title = re.sub(r"\s+", " ", title).strip(" -|:–—")
    return title[:240]


def canonical_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(clean_text(value))
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if not k.lower().startswith("utm_")]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, urllib.parse.urlencode(query), "")
    )


def host_name(url: str) -> str:
    return urllib.parse.urlsplit(canonical_url(url) or url).netloc.lower().removeprefix("www.")


def is_discovery_host(url: str) -> bool:
    return host_name(url) in DISCOVERY_HOSTS


def strip_discovery_branding(value: str) -> str:
    text = clean_text(value)
    for term in DISCOVERY_BRAND_TERMS:
        text = re.sub(rf"(?i)\b{re.escape(term)}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -|:–—")


def fingerprint(candidate: Candidate) -> str:
    material = f"{canonical_url(candidate.url)}\n{clean_title(candidate.title).lower()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def fetch_url(url: str, timeout: int = 25, retries: int = 2) -> Download:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
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
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.2 * (attempt + 1))
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


def parse_html(text: str, base_url: str) -> tuple[list[Candidate], NoticeHTMLParser]:
    parser = NoticeHTMLParser(base_url)
    parser.feed(text)
    candidates = [
        Candidate(clean_title(title), canonical_url(url))
        for url, title in parser.links
        if canonical_url(url) and clean_title(title)
    ]
    return candidates, parser


def source_candidates(download: Download) -> list[Candidate]:
    text = decode_document(download)
    feed_items = parse_feed(text, download.url)
    if feed_items:
        return feed_items
    html_items, _ = parse_html(text, download.url)
    return html_items


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
    if len(title) < 8 or title.lower() in GENERIC_TITLES:
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
        words = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s+(\d{4})", value)
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
            return clean_text(match.group(1)).strip(" .,:;-").upper()
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


def enrich_candidate(candidate: Candidate, source: dict[str, Any]) -> tuple[str, str, str]:
    """Return (searchable text, description source, best apply URL)."""
    combined = clean_text(f"{candidate.title}. {candidate.summary}")
    description_source = candidate.summary
    apply_url = candidate.url
    if source.get("enrichDetails", True) is False:
        return combined, description_source, apply_url

    try:
        download = fetch_url(candidate.url, timeout=int(source.get("detailTimeout", 20)), retries=1)
    except RuntimeError as exc:
        print(f"  Could not enrich {candidate.url}: {exc}", file=sys.stderr)
        return combined, description_source, apply_url

    is_pdf = download.content_type == "application/pdf" or urllib.parse.urlsplit(download.url).path.lower().endswith(".pdf")
    if is_pdf:
        extracted = pdf_text(download.data)
        return clean_text(f"{combined}. {extracted}")[:MAX_TEXT_LENGTH], description_source or extracted, apply_url

    text = decode_document(download)
    _, parser = parse_html(text, download.url)
    richer = clean_text(f"{combined}. {parser.description}. {parser.text}")[:MAX_TEXT_LENGTH]
    description_source = description_source or parser.description
    for url, label in parser.links:
        if re.search(r"(?i)\b(?:apply online|online application|register now|new registration)\b", label):
            safe = canonical_url(url)
            if safe:
                apply_url = safe
                break
    return richer, description_source, apply_url


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
    title = clean_title(candidate.title)
    notice_type = classify_notice(candidate, source) or "recruitment"
    searchable, description_source, apply_url = enrich_candidate(candidate, source)
    qualification, qual_category = infer_qualification(searchable, source)
    candidate_url = canonical_url(candidate.url)
    source_url = canonical_url(source["url"])
    if is_discovery_host(candidate_url) or is_discovery_host(source_url):
        raise ValueError("discovery-feed URLs cannot be published as job details")
    is_pdf = urllib.parse.urlsplit(candidate_url).path.lower().endswith(".pdf")
    last_date = find_labelled_date(
        searchable,
        r"last\s+date(?:\s+for\s+(?:submission|application|receipt|registration))?|closing\s+date|applications?\s+close",
    )
    start_date = find_labelled_date(
        searchable,
        r"start(?:ing)?\s+date|opening\s+date|applications?\s+open",
    )
    discovered = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source_name = strip_discovery_branding(
        clean_text(source.get("name") or source.get("department") or "Official website")
    )
    stable_id = int(hashlib.sha256(fingerprint(candidate).encode()).hexdigest()[:12], 16)
    badge, badge_color = notice_presentation(notice_type, True)
    presentation = NOTICE_PRESENTATION[notice_type]
    is_extension, extension_date = detect_extension(searchable) if notice_type == "corrigendum" else (False, "")

    return {
        "id": stable_id,
        "title": title,
        "department": clean_text(source.get("department") or source_name),
        "vacancies": infer_vacancies(searchable),
        "qualification": qualification,
        "qualCategory": qual_category,
        "lastDate": last_date or "See Notification",
        "startDate": start_date or (f"Published {candidate.published_at[:10]}" if candidate.published_at else "Newly Published"),
        "examDate": "See Official Notification",
        "location": clean_text(source.get("location") or ("Punjab" if source.get("type") == "punjab" else "All India")),
        "applyMode": "Offline" if "offline application" in searchable.lower() else "Online / As Notified",
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
        "pdfLink": "" if is_discovery_host(candidate_url) else candidate_url,
        "applyLink": "" if is_discovery_host(apply_url or candidate_url) else (
            canonical_url(source_url if is_pdf and apply_url == candidate_url else apply_url) or candidate_url
        ),
        "applyLabel": presentation["applyLabel"],
        "sourceName": source_name,
        "sourceUrl": source_url,
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
    Internal ``isExtension`` / ``extensionDate`` fields are removed so they are not
    persisted. Returns True when any job was changed.
    """
    changed = False
    for job in jobs:
        if job.get("alertType") != "corrigendum":
            continue
        is_extension = bool(job.pop("isExtension", False))
        extension_date = clean_text(job.pop("extensionDate", ""))
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
    return any(term in lowered for term in hints)


def load_discovery_feeds(path: Path = DEFAULT_DISCOVERY_FEEDS) -> list[dict[str, Any]]:
    registry = read_json(path, {"feeds": []})
    feeds: list[dict[str, Any]] = []
    for entry in registry.get("feeds", []) if isinstance(registry, dict) else []:
        if not isinstance(entry, dict):
            continue
        url = canonical_url(entry.get("url", ""))
        feed_id = clean_text(entry.get("id"))
        if not url or not feed_id or not is_discovery_host(url):
            continue
        feeds.append({
            "id": feed_id,
            "name": clean_text(entry.get("name") or feed_id),
            "url": url,
            "maxHeadlines": int(entry.get("maxHeadlines") or registry.get("maxHeadlinesPerFeed", 40)),
            "maxNewPerRun": int(entry.get("maxNewPerRun") or registry.get("maxNewPerFeed", 5)),
        })
    return feeds


def process_discovery_feeds(
    organizations: list[dict[str, Any]],
    state: dict[str, Any],
    now: datetime,
    dry_run: bool = False,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Scan aggregator headlines, then publish only matching official notices."""
    jobs: list[dict[str, Any]] = []
    added = 0
    state_changed = False
    state_sources = state.setdefault("sources", {})
    official_cache: dict[str, list[Candidate]] = {}

    for feed in load_discovery_feeds():
        print(f"Checking discovery feed {feed['name']}: {feed['url']}")
        try:
            download = fetch_url(feed["url"], timeout=25)
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
                    official_download = fetch_url(official_url, timeout=int(official.get("timeout", 25)))
                    official_cache[official_url] = deduplicate_candidates(
                        candidate
                        for candidate in source_candidates(official_download)[: int(official.get("maxLinks", 600))]
                        if looks_like_notice(candidate, official) and not is_discovery_host(candidate.url)
                    )
                except Exception as exc:
                    print(f"  Official source unavailable ({official.get('name')}): {exc}", file=sys.stderr)
                    official_cache[official_url] = []
            matches = official_notices_for_headline(headline.title, official_cache[official_url])
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
                if any(is_discovery_host(str(job.get(field, ""))) for field in ("pdfLink", "applyLink", "sourceUrl")):
                    print(f"  Dropped job that still pointed at a discovery host: {job.get('title')}")
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


def additional_link_sources(path: Path = ROOT / "data" / "notification-source-links.json") -> list[dict[str, Any]]:
    """Turn user-added notification URLs into monitor sources automatically."""
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
        generated.append({
            "id": source_id,
            "name": clean_text(entry.get("name") or host or "Additional job notification source"),
            "department": clean_text(entry.get("department") or entry.get("name") or host),
            "url": url,
            "type": clean_text(entry.get("type") or "central").lower(),
            "categorySlug": clean_text(entry.get("categorySlug") or "central"),
            "location": clean_text(entry.get("location") or "All India"),
            "noticeTypes": entry.get("noticeTypes") or sorted(DEFAULT_NOTICE_TYPES),
            "bootstrapCount": int(entry.get("bootstrapCount", 1)),
            "maxNewPerRun": int(entry.get("maxNewPerRun", 8)),
            "includeKeywords": entry.get("includeKeywords", []),
            "excludeKeywords": entry.get("excludeKeywords", []),
        })
    return generated


def run(config_path: Path, output_path: Path, state_path: Path, dry_run: bool = False) -> int:
    config = read_json(config_path, {})
    if not isinstance(config.get("sources"), list):
        raise RuntimeError(f"{config_path} must contain a sources array")

    configured_urls = {canonical_url(source.get("url", "")) for source in config["sources"]}
    for source in additional_link_sources():
        if source["url"] not in configured_urls:
            config["sources"].append(source)
            configured_urls.add(source["url"])

    output = read_json(output_path, {"version": 1, "updatedAt": None, "jobs": []})
    state = read_json(state_path, {"version": 1, "sources": {}})
    jobs = list(output.get("jobs") or [])
    state_sources = state.setdefault("sources", {})
    now = datetime.now(timezone.utc).replace(microsecond=0)
    jobs_changed = refresh_badges(jobs, now, int(config.get("newBadgeHours", 72)))
    state_changed = False
    added = 0
    successful_sources = 0

    for source in config["sources"]:
        if source.get("enabled", True) is False:
            continue
        if source.get("role") == "discovery" or is_discovery_host(source.get("url", "")):
            continue
        source_id = clean_text(source.get("id"))
        source_url = canonical_url(source.get("url", ""))
        if not source_id or not source_url:
            print("Skipping a source without a valid id/url", file=sys.stderr)
            continue
        print(f"Checking {source.get('name', source_id)}: {source_url}")
        try:
            download = fetch_url(source_url, timeout=int(source.get("timeout", 25)))
            discovered = deduplicate_candidates(
                candidate
                for candidate in source_candidates(download)[: int(source.get("maxLinks", 600))]
                if looks_like_notice(candidate, source)
            )
        except Exception as exc:
            print(f"  Source unavailable; keeping existing data: {exc}", file=sys.stderr)
            continue

        successful_sources += 1
        source_state = state_sources.setdefault(source_id, {"initializedAt": None, "fingerprints": []})
        known = set(source_state.get("fingerprints") or [])
        unseen = [candidate for candidate in discovered if fingerprint(candidate) not in known]
        first_success = not source_state.get("initializedAt")
        if first_success:
            selected = unseen[: max(0, int(source.get("bootstrapCount", 1)))]
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

    discovery_jobs, discovery_added, discovery_state_changed = process_discovery_feeds(
        approved_official_organizations(config["sources"]),
        state,
        now,
        dry_run,
    )
    if discovery_jobs:
        jobs.extend(discovery_jobs)
        added += discovery_added
        jobs_changed = True
    if discovery_state_changed:
        state_changed = True

    if apply_extensions(jobs):
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Update automatic recruitment, admission, answer-key, result and corrigendum alerts")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return run(args.config, args.output, args.state, args.dry_run)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
