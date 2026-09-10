"""Job-detail headline generator (department + posts + apply-mode rule).

Turns a long official notice title into a job-portal-style headline built from
the department name, the post name(s) and - for recruitment notices - the
apply mode:

    <Department> <Post name(s)> Recruitment | Apply Online
    <Department> Various Post Recruitment | Apply Offline
    <Department> <Notice type>                        (non-recruitment notices)

Post-name rules (taken from the notice's own wording):

    1 post        -> the post name is shown
    2 to 4 posts  -> every post name, comma separated
    more than 4   -> "Various Post"
    none named    -> department only

Examples
--------
"PGIMER Chandigarh - Recruitment of Nursing Officer"
    -> "PGIMER Chandigarh Nursing Officer Recruitment | Apply Online"

"PGIMER Chandigarh - Recruitment of DEO, MTS and Pharmacist"
    -> "PGIMER Chandigarh DEO, MTS, Pharmacist Recruitment | Apply Online"

"PGIMER Chandigarh - Recruitment of MTS, DEO, Pharmacist, Steno, Driver"
    -> "PGIMER Chandigarh Various Post Recruitment | Apply Online"

"State Bank of India (SBI) - Preliminary Exam Call Letter"
    -> "SBI Admit Card"

Data-only helper: it never fetches anything and never touches the page layout.
Used by ``scripts/preview_short_headlines.py`` to render the before/after demo
and mirrored by the ``shortJobHeadline()`` helper in index.html (both
implementations must produce identical output).
"""

from __future__ import annotations

import re

MAX_DEPARTMENT_LENGTH = 34

STATES = [
    "Punjab", "Haryana", "Himachal Pradesh", "Chandigarh", "Delhi", "Rajasthan",
    "Uttar Pradesh", "Madhya Pradesh", "Gujarat", "Bihar", "Maharashtra",
    "Karnataka", "Tamil Nadu", "Kerala", "Odisha", "Assam",
]

# Cities kept visible next to a bare board acronym
# ("Postgraduate Institute ... (PGIMER), Chandigarh" -> "PGIMER Chandigarh").
CITIES = [
    "Chandigarh", "Ludhiana", "Jalandhar", "Amritsar", "Patiala", "Bathinda",
    "Mohali", "SAS Nagar", "Panchkula", "Faridkot", "Kapurthala", "Ferozepur",
    "Delhi", "New Delhi", "Mumbai", "Pune", "Kolkata", "Chennai", "Hyderabad",
    "Bengaluru", "Jaipur", "Lucknow", "Kanpur", "Varanasi", "Prayagraj",
    "Ahmedabad", "Surat", "Bhopal", "Indore", "Dehradun", "Shimla", "Guwahati",
]

# Small words that stay lowercase inside a title-cased name ("Ministry of Defence").
SMART_SMALL_WORDS = {"of", "and", "for", "the", "in", "at", "on", "to", "a", "an", "by", "cum", "as"}

# Well-known recruiting bodies whose short form should be fixed, not guessed.
DEPARTMENT_SHORT_FORMS = [
    (r"navodaya vidyalaya samiti", "NVS"),
    (r"punjab state power corporation", "PSPCL"),
    (r"punjab public service commission", "PPSC"),
    (r"punjab police recruitment board|punjab police", "Punjab Police"),
    (r"department of school education,? punjab|punjab school education board", "PSEB"),
    (r"staff selection commission", "SSC"),
    (r"railway recruitment board", "RRB"),
    (r"rail coach factory", "RCF"),
    (r"(join )?indian army", "Indian Army"),
    (r"indian air force", "IAF"),
    (r"ministry of defence", "Ministry of Defence"),
    (r"directorate general of quality assurance", "DGQA"),
    (r"central council for research in siddha", "CCRS"),
    (r"central university of punjab", "CUPB"),
    (r"high court of punjab and haryana|punjab and haryana high court", "PHHC"),
    (r"local audit department", "Local Audit Dept."),
    (r"department of industries", "Industries Dept."),
]

WORD_ABBREVIATIONS = [
    (r"\bDepartment\b", "Dept."),
    (r"\bUniversity\b", "Univ."),
    (r"\bInstitute\b", "Inst."),
    (r"\bOrganization\b|\bOrganisation\b", "Org."),
    (r"\bAdministration\b", "Admin."),
    (r"\bGovernment\b|\bGovt\.?\b", "Govt."),
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

# Headline ending wording for each detected notice type. Recruitment is special:
# it becomes "Recruitment | Apply Online" / "Recruitment | Apply Offline".
NOTICE_SUFFIXES = {
    "Recruitment": "Recruitment",
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
    r"\b(?:recruitment|engagement|appointment)\s+(?:of|for)\b",
    r"\bPDF\s*\d+(?:\.\d+)?\s*(?:KB|MB)\b",
    r"-?\s*opens? in a new window",
    r"\bclick here\b", r"\bdownload\b", r"\bview\b",
    r"\bapplication form\b", r"\bonline form\b", r"\bapply online\b",
    r"\bofficial notification\b", r"\bnotification\b", r"\badvertisement\b",
    r"\blast date\b", r"\bregarding\b", r"\bapply (?:for|online)\b", r"\bapply\b",
    r"\bengagement\b", r"\blink download\b", r"\btentative\b",
    r"\bby (?:post|hand)\b", r"\bthrough (?:online|offline) mode\b",
    r"\bwritten test\b", r"\bqualifying test\b",
    r"\bexams?\b", r"\bexaminations?\b", r"\bonline\b", r"\boffline\b",
    r"\bregistration (?:from|on|opens?|starts?|begins?)\b[^,]*",
    r"\bscheduled to be held\b[^,]*", r"\bto be held (?:on|at)\b[^,]*",
    r"\brequest for proposal\b", r"\bpre-?bid\b",
    r"\bupdated vacancies\b", r"\bas on \d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b",
    r"\bcommon (?:recruitment )?process\b", r"\bfor audit year\b[^,]*",
    r"\bNo\.?\s*[A-Z]{1,6}(?:[/\-]\w+)+\b",
    r"\bto be conducted\b[^,]*", r"\bconducted (?:on|at)\b[^,]*",
    r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\.?\b",
    r"\bon (?:a )?(?:regular|contract|deputation|part-?time)\s+basis\b",
    r"\b\d{1,2}[-./][A-Za-z]{3,}[-./]\d{2,4}\b",
    r"\b(?:schedule|phase)\s*-?\s*[ivx]+\b", r"\b(?:schedule|phase)\b",
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
    r"\((?:Rajasthan|Punjab|Haryana|Himachal Pradesh|Chandigarh|Delhi|U\.T\.?)\)",
    r"\([^)]*\b(?:revised|tentative|amended|schedule|phase|extended)\b[^)]*\)",
]
# Collapsed double fillers left behind by removed phrases ("for for X").
FILLER_PAIR_RE = re.compile(
    r"\b(?:for|of|and|the|in|to)\s+(?:for|of|and|the|in|to)\b", re.IGNORECASE)

# Notice-type cue words must never survive into the post-name list.
CUE_WORD_RE = re.compile(
    r"\b(?:Recruitment|Result|Public Notice|Notice|Postponement|Postponed|Corrigendum|"
    r"Addendum|Cancellation|Shortlisted|Admission|Walk-?in-?Interview|Interview|"
    r"Posting Orders|Re-?Open(?:ed|ing)?|Extension|Extended|Cancell?ation|Cancell?ed|"
    r"Exam Date|Admit Card|Answer Key|Merit List|Waiting List|Date Extended)\b",
    re.IGNORECASE,
)

BRACKET_DATE_BLURB = re.compile(
    r"\([^)]*\b(?:last date|submission of application|interview|apply|upto|up to|"
    r"selection committee|\d{1,2}[-./]\d{1,2}[-./]\d{2,4})[^)]*\)?",
    re.IGNORECASE,
)
OFFICE_TAIL = re.compile(
    r"\s+[-\u2013\u2014]\s+[^-\u2013\u2014]*\b(?:College|Department|Dept\.?|Institute|School|"
    r"Centre|Center|Office|Division|Directorate|University|Faculty|Campus|Station|Wing)\b.*$",
    re.IGNORECASE,
)
# "for the post of Clerk", "for the post(s) of DEO and MTS", "recruitment of 90 posts of ..."
POST_LEAD = re.compile(r"\bposts?(?:\s*\(s\))?\s+of\s+(?P<post>.+)$", re.IGNORECASE)

GENERIC_POSTS = {
    "various post", "various posts", "other posts", "more", "post", "posts",
    "various", "various faculty posts", "misc", "vacancies", "vacancy",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


# A bare website address must never appear in a headline or be used as the
# department ("sbi.gov.in announced result", "iitbhu.aci.in latest vacancy").
# Matches a URL or host that ends in an Indian suffix / gTLD / a ".in" host with
# at least one label, while ignoring ordinary words and bracketed year tails.
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


def is_website_domain(value: str) -> bool:
    """True when the whole value is just a website address (URL or domain)."""
    text = _clean(value).strip(" .,:;–-|()[]{}\"'").lower()
    if not text:
        return False
    if WEBSITE_DOMAIN_RE.fullmatch(text):
        return True
    if re.fullmatch(r"(?:https?://)?(?:www\.)?\S+", text) and "." in text:
        host = re.sub(r"^https?://", "", text).split("/", 1)[0]
        return bool(re.search(r"\.[a-z]{2,}(?:\.[a-z]{2})?$", host))
    return False


def strip_website_domains(value: str) -> str:
    """Remove website URLs/domains from a headline/department, keeping words."""
    text = WEBSITE_DOMAIN_RE.sub(" ", _clean(value))
    return re.sub(r"\s+", " ", text).strip(" .,:;–-|'\"")


def _strip_date_blurbs(text: str) -> str:
    """Remove bracketed 'last date / interview on ...' blurbs before classifying."""
    return _clean(BRACKET_DATE_BLURB.sub(" ", _clean(text)))


def smart_title_case(text: str) -> str:
    """Title-case a name while keeping ALL-CAPS acronyms (DEO, MTS, PGIMER) intact."""
    def cap(index: int, token: str) -> str:
        match = re.search(r"[A-Za-z]", token)
        if not match:
            return token
        start = match.start()
        rest = token[start:]
        letters = re.sub(r"[^A-Za-z]", "", rest)
        if letters and rest == rest.upper():
            return token  # acronym / ALL-CAPS token: PGIMER, DEO, MTS, WCD
        if rest == rest.lower():
            if index > 0 and token.lower().strip(".,()[]&/-'\"") in SMART_SMALL_WORDS:
                return token  # small word stays lowercase ("Ministry of Defence")
            if not re.search(r"\d", token) and rest.rstrip(".,;:()[]&/-'\"").isalpha():
                return token[:start] + token[start].upper() + token[start + 1:]
            return token  # carries digits/internal punctuation (6th, 10+2, b.sc): keep as-is
        return token  # already mixed case (B.Sc, Dept., McDonald): keep

    return _clean(" ".join(cap(i, t) for i, t in enumerate(_clean(text).split(" "))))


def short_department(department: str, title: str = "") -> str:
    """Compress an official department name into a short, recognisable label."""
    # A website link is never a department name.
    department = strip_website_domains(department)
    dept = _clean(department)
    if not dept or is_website_domain(dept):
        # Fall back to the part before the em dash of a "Dept — Subject" title,
        # after stripping any website link from it.
        dept = _clean(strip_website_domains(_clean(title).split("—")[0]))
    if not dept or is_website_domain(dept):
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
        short = short[:MAX_DEPARTMENT_LENGTH].rsplit(" ", 1)[0].strip(" ,-\u2013\u2014")

    short = re.sub(r"\s+(?:for|of|and|the|in|&)$", "", short, flags=re.IGNORECASE).strip(" ,-\u2013\u2014")

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
    # 4) Keep the city visible when the short form is just the board's acronym
    #    ("Postgraduate Institute ... (PGIMER), Chandigarh" -> "PGIMER Chandigarh").
    if " " not in short:
        for city in CITIES:
            if re.search(rf"[,\u2013\u2014]\s*{re.escape(city)}\b", dept, flags=re.IGNORECASE) \
                    and city.lower() not in short.lower():
                short = f"{short} {city}"
                break
    return smart_title_case(_clean(short))


def notice_type(title: str, alert_type: str = "") -> str:
    """Classify what the notification is about (corrigendum, result, exam date...)."""
    text = _strip_date_blurbs(title).lower()
    for label, pattern in NOTICE_TYPE_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            if label == "Recruitment":
                return ALERT_TYPE_DEFAULTS.get(alert_type, "Recruitment")
            return label
    return ALERT_TYPE_DEFAULTS.get(alert_type, "Recruitment")


def apply_mode_suffix(apply_mode: str, title: str = "") -> str:
    """"Apply Online" or "Apply Offline", from the stored apply mode / notice wording."""
    hay = f"{apply_mode or ''} {title or ''}".lower()
    if re.search(r"\boffline\b|by post|by hand|through offline mode", hay):
        return "Apply Offline"
    return "Apply Online"


def headline_suffix(kind: str, title: str = "", apply_mode: str = "") -> str:
    """Map the detected notice type onto the headline ending wording."""
    if kind == "Recruitment":
        return f"Recruitment | {apply_mode_suffix(apply_mode, title)}"
    suffix = NOTICE_SUFFIXES.get(kind, kind)
    if kind == "Postponed" and re.search(r"interview", title, re.IGNORECASE):
        return "Interview Postponed"
    if kind == "Cancelled" and re.search(r"exam", title, re.IGNORECASE):
        return "Exam Cancelled"
    if kind == "Answer Key" and re.search(r"exam", title, re.IGNORECASE):
        return "Exam Answer Key"
    return suffix


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


def headline_posts(title: str, department: str = "", vacancies: str = "") -> list[str]:
    """Post name(s) for the headline: at most 4 names, or ["Various Post"] when more."""
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
    # Possessive remnant left when the department name is stripped ("UCO Bank's ..." -> "'S ...").
    subject = re.sub(r"(?:^|\s)['\u2019]s\b\s*", " ", subject, flags=re.IGNORECASE)
    subject = FILLER_PAIR_RE.sub(" ", subject)
    subject = re.sub(r"\b(?:19|20)\d{2}(?:\s*[-/]\s*\d{2,4})?\b", " ", subject)
    subject = re.sub(r"\((?:\s*|Advt\.?[^)]*)\)", " ", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\b(?:Advt\.?|Advertisement)\s*No\.?\s*[\w/\-]+", " ", subject, flags=re.IGNORECASE)
    subject = _clean(subject).strip(" ,;:|-\u2013\u2014<>")

    subject = re.sub(r"^\s*\d+\s*(?:posts?|vacancies)?\s*", "", subject, flags=re.IGNORECASE)
    subject = CUE_WORD_RE.sub(" ", subject)
    subject = re.sub(r"^\s*(?:for|of)\s+", "", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\s*\bforms?\b\s*$", "", subject, flags=re.IGNORECASE)
    subject = _clean(subject).strip(" ,;:|-\u2013\u2014<>")

    dept_words = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", _clean(department))}
    parts = [p for p in _split_posts(subject)
             if not (dept_words and {w.lower() for w in re.findall(r"[A-Za-z]{3,}", p)}
                     and {w.lower() for w in re.findall(r"[A-Za-z]{3,}", p)} <= dept_words)]
    parts = [p for p in parts if re.search(r"[A-Za-z]{2,}", p)]
    kept = [p for p in parts if p.lower() not in GENERIC_POSTS]

    various_cue = (
        len(kept) > 4
        or (kept and len(kept) != len(parts))
        or re.search(r"\bvarious\b", _clean(title), re.IGNORECASE) is not None
        or re.search(r"^various\b", _clean(vacancies), re.IGNORECASE) is not None
    )
    if various_cue:
        return ["Various Post"]
    return [smart_title_case(_clean(k).strip(" ,;:|-\u2013\u2014&<>"))
            for k in kept[:4] if _clean(k).strip(" ,;:|-\u2013\u2014&<>")]


def short_job_headline(title: str, department: str = "", alert_type: str = "",
                       vacancies: str = "", apply_mode: str = "") -> str:
    """Build the job-portal-style heading used as the job-details headline."""
    # A website link must never appear in the headline ("sbi.gov.in announced...").
    raw_title = strip_website_domains(_clean(title))
    department = strip_website_domains(department)
    dept = short_department(department, raw_title)
    kind = notice_type(raw_title, alert_type)

    if kind == "Recruitment":
        posts = ", ".join(headline_posts(raw_title, department, vacancies))
        body = _clean(f"{dept} {posts}".strip())
        return _clean(f"{body} {headline_suffix(kind, raw_title, apply_mode)}".strip())
    # Non-recruitment notices: department + notice type (no posts, no apply mode).
    return _clean(f"{dept} {headline_suffix(kind, raw_title)}".strip())


__all__ = [
    "short_job_headline", "short_department", "headline_posts", "notice_type",
    "headline_suffix", "apply_mode_suffix", "smart_title_case",
    "is_website_domain", "strip_website_domains",
]
