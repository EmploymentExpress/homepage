"""Short job-detail headline generator.

Turns a long official notice title into a short, scannable headline of the form:

    <Short department> <Total posts> <Post name(s)> <What the notice is about>

matching the familiar job-portal headline style, e.g.
"HAL Design Trainee, Management Trainee Online Form",
"Delhi Police 7565 Constable Exam Answer Key",
"NGEL Engineer/ Executive Vacancy Online Form".

Examples
--------
"Punjab State Legal Services Authority (PULSA) — View, Public notice regarding
 result for the post of Process Server (selection of candidate from the
 Ex-servicemen category) PDF 383 KB - opens in a new window View"
    -> "PULSA Process Server Result"

"Punjab Agricultural University (PAU), Ludhiana — Postponement of interview for
 the post of Lab Helper - College of Basic Scs. & Humanities"
    -> "PAU Lab Helper Interview Postponed"

Data-only helper: it never fetches anything and never touches the page layout.
Used by ``scripts/preview_short_headlines.py`` to render the before/after demo
and mirrored by the ``shortJobHeadline()`` helper in index.html.
"""

from __future__ import annotations

import re

MAX_HEADLINE_LENGTH = 72
MAX_DEPARTMENT_LENGTH = 34

STATES = [
    "Punjab", "Haryana", "Himachal Pradesh", "Chandigarh", "Delhi", "Rajasthan",
    "Uttar Pradesh", "Madhya Pradesh", "Gujarat", "Bihar", "Maharashtra",
    "Karnataka", "Tamil Nadu", "Kerala", "Odisha", "Assam",
]

STOP_WORDS = {"of", "for", "and", "in", "the", "&", "at", "on", "cum", "a"}

# Well-known recruiting bodies whose short form should be fixed, not guessed.
# Always in capital letters per headline rule.
DEPARTMENT_SHORT_FORMS = [
    (r"navodaya vidyalaya samiti", "NVS"),
    (r"punjab state power corporation", "PSPCL"),
    (r"punjab public service commission", "PPSC"),
    (r"punjab police recruitment board|punjab police", "PUNJAB POLICE"),
    (r"department of school education,? punjab|punjab school education board", "PSEB"),
    (r"staff selection commission", "SSC"),
    (r"railway recruitment board", "RRB"),
    (r"rail coach factory", "RCF"),
    (r"(join )?indian army", "INDIAN ARMY"),
    (r"indian air force", "IAF"),
    (r"ministry of defence", "MINISTRY OF DEFENCE"),
    (r"directorate general of quality assurance", "DGQA"),
    (r"central council for research in siddha", "CCRS"),
    (r"central university of punjab", "CUPB"),
    (r"high court of punjab and haryana|punjab and haryana high court", "PHHC"),
    (r"local audit department", "LOCAL AUDIT DEPT."),
    (r"department of industries", "INDUSTRIES DEPT."),
]

WORD_ABBREVIATIONS = [
    (r"\bDepartment\b", "DEPT."),
    (r"\bUniversity\b", "UNIV."),
    (r"\bInstitute\b", "INST."),
    (r"\bOrganization\b|\bOrganisation\b", "ORG."),
    (r"\bAdministration\b", "ADMIN."),
    (r"\bGovernment\b|\bGovt\.?\b", "GOVT."),
]

# Ordered notice-type rules: (label, regex tested against the cleaned title).
NOTICE_TYPE_RULES = [
    ("Corrigendum", r"\bcorrigend(?:um|a)\b"),
    ("Addendum", r"\bad+end(?:um|a)\b"),
    ("Cancelled", r"\bcancel(?:l?ed|lation|ling)?\b|\bwithdraw(?:n|al)\b"),
    ("Postponed", r"\bpostpon(?:ed|ement)\b|\bdeferred\b|\breschedul(?:ed|ing)\b"),
    ("Date Extended", r"\bextension\b|\bextended\b|\bre-?open(?:ed|ing)?\b"),
    ("Shortlisted", r"\bshort-?list(?:ed|ing)?\b|\bempanel(?:ment|led)\b|\beligible candidates\b|\bprovisionally (?:eligible|selected|shortlisted)\b|\blist of (?:eligible|shortlisted|selected) candidates\b|\bscore ?card list\b"),
    ("Exam Date", r"\bexam(?:ination)? (?:date|schedule|city|centre|center|timetable|time table)\b|\bdate ?sheet\b|\bwritten (?:test|exam(?:ination)?) (?:date|schedule)\b|\bcbt (?:date|schedule)\b|\bdate of (?:the )?(?:exam|examination|written test)\b"),
    ("Admit Card", r"\badmit card\b|\bcall letter\b|\broll ?(?:no|number)\b|\bhall ticket\b"),
    ("Answer Key", r"\banswer key\b|\bresponse sheet\b|\bobjection\b"),
    ("Waiting List", r"\bwaiting list\b|\bwait-?list\b"),
    ("Merit List", r"\bmerit list\b|\bselection list\b|\bfinal selection\b"),
    ("Result", r"\bresults?\b|\bcut-?off\b|\bscorecard\b"),
    ("Posting Orders", r"\bposting orders?\b|\bappointment orders?\b"),
    ("Walk-in Interview", r"\bwalk-?in(?:-?interview)?\b"),
    ("Admission", r"\badmission\b|\bentrance test\b|\bprospectus\b|\bcounsel?ling\b"),
    ("Notice", r"\bpublic notice\b|\bimportant notice\b"),
    ("Recruitment", r".*"),
]

# Headline suffix wording (job-portal style) for each detected notice type.
NOTICE_SUFFIXES = {
    "Recruitment": "Online Form",
    "Corrigendum": "Corrigendum Notice",
    "Addendum": "Addendum Notice",
    "Cancelled": "Vacancy Cancelled",
    "Postponed": "Exam Postponed",
    "Date Extended": "Last Date Extended",
    "Shortlisted": "Shortlisted Candidates",
    "Exam Date": "Exam Date",
    "Admit Card": "Admit Card",
    "Answer Key": "Answer Key",
    "Waiting List": "Waiting List",
    "Merit List": "Merit List",
    "Result": "Result",
    "Posting Orders": "Posting Orders",
    "Walk-in Interview": "Walk in Interview",
    "Admission": "Admission Form",
    "Notice": "Public Notice",
}

ALERT_TYPE_DEFAULTS = {
    "result": "Result",
    "answer-key": "Answer Key",
    "corrigendum": "Corrigendum",
    "admission": "Admission",
    "admit-card": "Admit Card",
    "recruitment": "Recruitment",
}

# Link-text / PDF-metadata noise emitted by official portals.
NOISE_PATTERNS = [
    r"\bPDF\s*\d+(?:\.\d+)?\s*(?:KB|MB)\b",
    r"-?\s*opens? in a new window",
    r"\bclick here\b", r"\bdownload\b", r"\bview\b",
    r"\bapplication form\b", r"\bonline form\b", r"\bapply online\b",
    r"\bofficial notification\b", r"\bnotification\b", r"\badvertisement\b",
    r"\blast date\b", r"\bregarding\b", r"\bapply (?:for|online)\b", r"\bapply\b",
]

BRACKET_DATE_BLURB = re.compile(
    r"\([^)]*\b(?:last date|submission of application|interview|apply|upto|up to|"
    r"selection committee|\d{1,2}[-./]\d{1,2}[-./]\d{2,4})[^)]*\)?",
    re.IGNORECASE,
)
OFFICE_TAIL = re.compile(
    r"\s*[-\u2013\u2014]\s*[^-\u2013\u2014]*\b(?:College|Department|Dept\.?|Institute|School|"
    r"Centre|Center|Office|Division|Directorate|University|Faculty|Campus|Station|Wing)\b.*$",
    re.IGNORECASE,
)
POST_LEAD = re.compile(r"\bposts?\s+of\s+(?P<post>.+)$", re.IGNORECASE)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _strip_date_blurbs(text: str) -> str:
    """Remove bracketed 'last date / interview on ...' blurbs before classifying."""
    return _clean(BRACKET_DATE_BLURB.sub(" ", _clean(text)))


def short_department(department: str, title: str = "") -> str:
    """Compress an official department name into a short, recognisable label."""
    dept = _clean(department)
    if not dept:
        # Fall back to the part before the em dash of a "Dept — Subject" title.
        dept = _clean(_clean(title).split("\u2014")[0])
    if not dept:
        return ""

    mapped = ""
    for pattern, short_form in DEPARTMENT_SHORT_FORMS:
        if re.search(pattern, dept, re.IGNORECASE):
            mapped = short_form
            break

    # 1) Prefer an acronym the department itself publishes in brackets.
    expansion = dept
    acronym = mapped
    for match in (re.finditer(r"\(([^)]{2,14})\)", dept) if not mapped else []):
        token = match.group(1).strip()
        letters = [c for c in token if c.isalpha()]
        uppers = [c for c in letters if c.isupper()]
        if len(uppers) >= 2 and letters and len(uppers) / len(letters) >= 0.75:
            acronym = _clean(token)
            break
    if acronym:
        short = acronym
    else:
        # 2) Otherwise use the leading segment, abbreviated and length-capped.
        head = re.split(r"[,\u2013\u2014]| - ", expansion)[0].strip()
        head = re.sub(r"\([^)]*\)", " ", head)
        short = _clean(head)
    if not acronym and len(short) > MAX_DEPARTMENT_LENGTH:
        for pattern, replacement in WORD_ABBREVIATIONS:
            short = re.sub(pattern, replacement, short, flags=re.IGNORECASE)
        short = _clean(short)
    if not acronym and len(short) > MAX_DEPARTMENT_LENGTH:
        short = short[:MAX_DEPARTMENT_LENGTH].rsplit(" ", 1)[0].strip(" ,-")

    short = re.sub(r"\s+(?:for|of|and|the|in|&)$", "", short, flags=re.IGNORECASE).strip(" ,-")

    # 3) Keep the state/UT visible when it is only implied.
    for state in STATES:
        if re.match(rf"^{re.escape(state)}\b", dept, flags=re.IGNORECASE) \
                and state.lower() not in short.lower() \
                and not short.upper().startswith(state[0].upper()):
            short = f"{state} {short}"
            break
    if re.search(r"\b(?:U\.?T\.?\s*Chandigarh|Chandigarh Administration)\b", dept, re.IGNORECASE) \
            and "chandigarh" not in short.lower():
        short = f"{short} Chandigarh"
    return _clean(short).upper()


def notice_type(title: str, alert_type: str = "") -> str:
    """Classify what the notification is about (corrigendum, result, exam date...)."""
    text = _strip_date_blurbs(title).lower()
    for label, pattern in NOTICE_TYPE_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            if label == "Recruitment":
                return ALERT_TYPE_DEFAULTS.get(alert_type, "Recruitment")
            return label
    return ALERT_TYPE_DEFAULTS.get(alert_type, "Recruitment")


def _department_aliases(department: str, title: str) -> list[str]:
    dept = _clean(department)
    aliases = {dept, short_department(dept, title)}
    aliases.add(re.split(r"[,\u2013\u2014]| - ", dept)[0].strip())
    for match in re.finditer(r"\(([^)]+)\)", dept):
        aliases.add(match.group(1).strip())
        aliases.add(dept[: match.start()].strip())
    aliases.add(re.sub(r"\([^)]*\)", " ", dept).strip())
    return sorted({_clean(a) for a in aliases if _clean(a)}, key=len, reverse=True)


def _split_posts(subject: str) -> list[str]:
    """Split a post list on commas/&/'and' while protecting bracketed text."""
    protected: list[str] = []

    def hide(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"\u0001{len(protected) - 1}\u0001"

    masked = re.sub(r"\([^)]*\)", hide, subject)
    parts = [p.strip() for p in re.split(r"\s*(?:,|&|\band\b)\s*", masked) if p.strip()]
    restored = []
    for part in parts:
        for i, original in enumerate(protected):
            part = part.replace(f"\u0001{i}\u0001", original)
        restored.append(_clean(part))
    return restored


AUTHORITY_FILLER_WORDS = {
    "board", "boards", "department", "dept", "dept.", "commission", "recruitment",
    "authority", "corporation", "university", "samiti", "office", "of", "the",
}


def _strip_leading_authority_words(subject: str, department: str) -> str:
    """Drop leading words that merely repeat the recruiting authority's name."""
    dept_words = {w.lower().strip(".,()") for w in re.split(r"\W+", _clean(department)) if w}
    words = _clean(subject).split()
    removed = 0
    while words and removed < 5:
        candidate = words[0].lower().strip(".,()")
        if candidate and (candidate in dept_words or candidate in AUTHORITY_FILLER_WORDS):
            words.pop(0)
            removed += 1
            continue
        break
    return _clean(" ".join(words)) or _clean(subject)


def short_subject(title: str, department: str = "") -> str:
    """Extract the post(s) / subject the notice is about."""
    subject = _strip_date_blurbs(title)
    for alias in _department_aliases(department, title):
        subject = re.sub(rf"^\s*{re.escape(alias)}\s*[,;:\u2013\u2014|-]*\s*", "", subject,
                         flags=re.IGNORECASE).strip()
        subject = re.sub(rf"\b{re.escape(alias)}\b", " ", subject, flags=re.IGNORECASE)

    subject = re.sub(r"\((?:selection of [^)]*|[^)]*category)\)", " ", subject, flags=re.IGNORECASE)
    subject = _strip_leading_authority_words(subject, department)

    post_match = POST_LEAD.search(subject)
    if post_match:
        subject = post_match.group("post")
    subject = re.sub(r"^\s*post\s+of\s+", "", subject, flags=re.IGNORECASE)

    subject = OFFICE_TAIL.sub("", subject)
    dash_split = [seg for seg in re.split(r"\s+[\u2013\u2014]\s+|\s+-\s+", subject) if _clean(seg)]
    if len(dash_split) > 1:
        meaningful = [seg for seg in dash_split
                      if len([w for w in re.findall(r"[A-Za-z]{3,}", seg)]) >= 1]
        subject = (meaningful or dash_split)[0]
    for pattern in NOISE_PATTERNS:
        subject = re.sub(pattern, " ", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\b(?:19|20)\d{2}(?:\s*[-/]\s*\d{2,4})?\b", " ", subject)
    subject = re.sub(r"\((?:\s*|Advt\.?[^)]*)\)", " ", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\b(?:Advt\.?|Advertisement)\s*No\.?\s*[\w/\-]+", " ", subject, flags=re.IGNORECASE)
    subject = _clean(subject).strip(" ,;:|-\u2013\u2014")

    subject = re.sub(r"^\s*\d+\s*(?:posts?|vacancies)?\s*", "", subject, flags=re.IGNORECASE)
    dept_words = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", _clean(department))}
    parts = [p for p in _split_posts(subject)
             if not (dept_words and {w.lower() for w in re.findall(r"[A-Za-z]{3,}", p)}
                     and {w.lower() for w in re.findall(r"[A-Za-z]{3,}", p)} <= dept_words)]
    parts = [p for p in parts if re.search(r"[A-Za-z]{2,}", p)]
    generic = {"various post", "various posts", "other posts", "more", "post", "posts",
               "various", "various faculty posts", "misc"}
    kept = [p for p in parts if p.lower() not in generic]
    truncated = len(kept) > 2 or len(kept) != len(parts)
    kept = [_clean(k).strip(" ,;:|-\u2013\u2014&") for k in kept if _clean(k)]
    if kept:
        subject = ", ".join(kept[:2])
        if truncated:
            subject = f"{subject} & Various Post"
    return _clean(subject).strip(" ,;:|-\u2013\u2014")


def vacancy_count(vacancies: str) -> str:
    """Return the total-post number when the vacancy field states a clean count."""
    text = _clean(vacancies)
    if not text or re.search(r"see notification|various|as per", text, re.IGNORECASE):
        return ""
    match = re.match(r"^\D{0,12}?(\d[\d,]{0,8})", text)
    if not match:
        return ""
    number = match.group(1).replace(",", "").lstrip("0")
    if not number or int(number) < 2:
        return ""
    return f"{int(number):,}"


def headline_suffix(kind: str, title: str = "", apply_mode: str = "") -> str:
    """Map the detected notice type onto job-portal headline wording."""
    suffix = NOTICE_SUFFIXES.get(kind, kind)
    if kind == "Recruitment" and re.search(r"offline|by post|by hand|walk", f"{apply_mode} {title}", re.IGNORECASE):
        return "Offline Form"
    if kind == "Postponed" and re.search(r"interview", title, re.IGNORECASE):
        return "Interview Postponed"
    if kind == "Cancelled" and re.search(r"exam", title, re.IGNORECASE):
        return "Exam Cancelled"
    if kind == "Answer Key" and re.search(r"exam", title, re.IGNORECASE):
        return "Exam Answer Key"
    return suffix


def short_job_headline(title: str, department: str = "", alert_type: str = "",
                       vacancies: str = "", apply_mode: str = "") -> str:
    """Build the short, job-portal-style headline used as the job-details heading."""
    raw_title = _clean(title)
    dept = short_department(department, raw_title)
    kind = notice_type(raw_title, alert_type)
    subject = short_subject(raw_title, department)

    # Never repeat the notice type (or its cue words) inside the subject.
    cue_words = r"|".join([
        re.escape(kind), "Recruitment", "Result", "Public Notice", "Notice",
        "Postponement", "Postponed", "Corrigendum", "Addendum", "Cancellation",
        "Shortlisted", "Admission", "Walk-?in-?Interview", "Interview", "Posting Orders",
        "Re-?Open(?:ed|ing)?", "Extension", "Extended", "Cancell?ation", "Cancell?ed",
        "Exam Date", "Admit Card", "Answer Key", "Merit List", "Waiting List", "Date Extended",
    ])
    subject = re.sub(rf"\b(?:{cue_words})\b", " ", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\s*\bforms?\b\s*$", "", _clean(subject), flags=re.IGNORECASE)
    subject = _clean(subject).strip(" ,;:|-\u2013\u2014&")

    suffix = headline_suffix(kind, raw_title, apply_mode)
    count = vacancy_count(vacancies)
    if count and re.search(rf"\b{re.escape(count)}\b", subject):
        count = ""

    prefix = ""
    if dept:
        lead = r"\b" if re.match(r"^\w", dept) else ""
        trail = r"\b" if re.search(r"\w$", dept) else r"(?!\w)"
        dept_pattern = rf"{lead}{re.escape(dept)}{trail}"
        if re.search(dept_pattern, subject, re.IGNORECASE):
            subject = re.sub(dept_pattern, dept, subject, flags=re.IGNORECASE)
        else:
            prefix = f"{dept} "
    if count:
        prefix = f"{prefix}{count} "

    headline = _clean(f"{prefix}{subject} {suffix}") if subject else _clean(f"{prefix}{suffix}")

    if len(headline) > MAX_HEADLINE_LENGTH:
        posts = [p.strip() for p in re.split(r",\s*", subject) if p.strip()]
        extra = " & Various Post" if (re.search(r"& Various Post$", subject) or len(posts) > 1) else ""
        first = posts[0] if posts else ""
        first_plain = _clean(re.sub(r"\([^)]*\)", " ", first)).strip(" ,;:|-\u2013\u2014&")
        candidates = [
            subject,
            _clean(re.sub(r"\s+,", ",", re.sub(r"\([^)]*\)", " ", subject))),
            f"{first}{extra}",
            f"{first_plain}{extra}",
            first_plain,
        ]
        headline = ""
        for body in candidates:
            body = _clean(body).strip(" ,;:|-\u2013\u2014&")
            if not body:
                continue
            attempt = _clean(f"{prefix}{body} {suffix}")
            if len(attempt) <= MAX_HEADLINE_LENGTH:
                headline = attempt
                break
        if not headline:
            budget = MAX_HEADLINE_LENGTH - len(prefix) - len(suffix) - 1
            body = first_plain or subject
            if budget > 12 and body:
                if len(body) > budget:
                    body = body[:budget].rsplit(" ", 1)[0]
                body = body.strip(" ,;:|-\u2013\u2014&")
                headline = _clean(f"{prefix}{body} {suffix}")
            else:
                headline = _clean(f"{prefix}{suffix}")
    return _clean(re.sub(r"\s+,", ",", headline))


__all__ = [
    "short_job_headline", "short_department", "short_subject", "notice_type",
    "headline_suffix", "vacancy_count",
]
