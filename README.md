# EMPLOYMENT EXPRESS — Homepage

**Punjab's No.1 Govt Job Alert Portal** — Fast, accurate alerts for Navodaya Vidyalaya Samiti (NVS Chandigarh), Punjab Police, PSSSB, PPSC, PSPCL, School Education (Master Cadre / ETT), SSC, UPSC, Railway (RRB) & Indian Army/Agniveer.

Live site: **https://employmentexpress.github.io/homepage/**

---

### 🔔 Official Alerts

Get instant notifications for new vacancies, admit cards, results & answer keys:

- **Telegram:** https://t.me/employment_express1
- **WhatsApp Channel:** https://whatsapp.com/channel/0029Va9xQHV4tRrxpVKaG93w
- **YouTube — Subscribe YouTube Channel:** https://www.youtube.com/channel/UCI39CbrtpEflEPabKeCAd9A

> All `Join Telegram` / `Join WhatsApp` / `Subscribe YouTube Channel` buttons, floating social buttons, top-bar alerts, and footer icons link to the channels above. Subscriber counts have been intentionally removed for a clean, evergreen UI.

---

### ✨ Features (Aug 2026 Refresh)

- **Tailwind CSS** responsive layout — sticky header, breaking-news marquee with NVS Chandigarh RO & Punjab job alerts, 6-category quick filter, 4 adaptive mega-grid columns
- **Live Search** — filters by post name / department / qualification; debounced + highlighted + “No results” state
- **Qualification pills** — 10th / 12th / Graduate / ITI-Diploma / ETT-B.Ed (Teaching) / Defence-Police
- **Automation-ready Alert Monitor** — the monitor and workflow template are configured to check official pages/RSS feeds once every six hours for recruitment, admission, answer-key, result, corrigendum and addendum notices; linked HTML/PDF details are extracted into the generated feed
- **Dynamic Breaking Alerts** — newly discovered notices automatically use the correct `NEW JOB ALERT`, `NEW ADMISSION`, `NEW ANSWER KEY`, `NEW RESULT` or `NEW UPDATE` label and update the existing Breaking marquee for seven days
- **Master Vacancy Table (2026)** — curated vacancies plus automatic alerts including the RCF Kapurthala 734 Act Apprentice notification, with posts count, last date, source information, and `Apply/Info` modal
- **Job Detail Modal** — vacancy, location, apply mode, last date, dates & fees, age/eligibility, how-to-apply, PDF + Apply links, Web Share API; unknown automatic fields say “See Official Notification” rather than being guessed
- **Admit Card & Results columns** — direct “Get” / “NEW” pulses with toast feedback including NVS Chandigarh & JNVST lists
- **Syllabus & Official Portals widgets** + direct links to Navodaya Vidyalaya Samiti RO Chandigarh (`https://navodaya.gov.in/nvs/ro/Chandigarh/en/home/`)
- **Floating Telegram/WhatsApp/YouTube buttons** + footer disclaimer (YouTube with headline “Subscribe YouTube Channel”)
- **SEO:** canonical, Open Graph, Twitter Card, Organization + WebSite JSON-LD, `robots.txt` + `sitemap.xml` (lastmod 2026-08-17), Google Search Console verification meta tag (`google-site-verification`)
- **A11y & Performance:** semantic headings (`sr-only` H1), ARIA, keyboard `Esc` to close modal, focus rings, custom scrollbar, `preconnect` hints

---

### 📁 Structure

```
/
├── automation/
│   ├── update-job-alerts.workflow.yml       # Six-hour GitHub Actions template
│   ├── sources.json                         # Websites/feeds to monitor
│   └── requirements.txt                    # PDF extraction dependency
├── data/
│   ├── auto-jobs.json                       # Generated jobs consumed by the page
│   └── seen-notices.json                    # Generated de-duplication state
├── scripts/update_jobs.py                   # Generic HTML/RSS/PDF monitor
├── tests/test_update_jobs.py                # Parser and de-duplication tests
├── index.html                               # Single-page, data-driven homepage
├── assets/logo.png                          # Favicon / brand logo
├── sitemap.xml
├── robots.txt
└── README.md
```

---

### 🛠 Tech

- **Tailwind CSS CDN** (plus `tailwind.config` brand palette: `brand-50 → 900`, accent)
- **Font Awesome 6.4**, **Plus Jakarta Sans + Tiro Gurmukhi** (Google Fonts)
- **Vanilla JS** — `jobDatabase` (10 entries, `type: punjab|central`, `categorySlug`), `admitCards`, `resultsList`, renderers (`renderPunjabColumn`, `renderCentralColumn`, etc.), filters (`filterJobs`, `filterByQual`, `filterByCategory`), modal & toast

To add / edit a **curated** vacancy, edit `jobDatabase` in `index.html`. Automatically discovered vacancies live in `data/auto-jobs.json` and should not be edited by hand:

```js
{
  id: 8,
  title: "NVS Chandigarh PGT, TGT, Staff Nurse & Hostel Superintendent 2026",
  department: "Navodaya Vidyalaya Samiti (NVS), Regional Office Chandigarh",
  vacancies: "120+ Posts",
  qualification: "Post Graduate + B.Ed / Graduate / B.Sc Nursing / Diploma",
  qualCategory: "B.Ed/ETT",
  lastDate: "28-09-2026",
  badge: "NEW JOB ALERT",
  badgeColor: "bg-emerald-600",
  type: "central",
  categorySlug: "teacher",
  advtNo: "NVS-RO-CHD/REC/2026-27",
  age: "Up to 50 Years (Retired Teachers up to 65 Years)",
  details: "...",
  pdfLink: "https://navodaya.gov.in/nvs/ro/Chandigarh/en/home/",
  applyLink: "https://navodaya.gov.in/nvs/ro/Chandigarh/en/home/"
}
```

---

### 🤖 Automatic Job Alert Setup

The ready-to-install workflow template in `automation/update-job-alerts.workflow.yml` is configured to run once every six hours (`17 */6 * * *`, in UTC) and supports manual runs. Once installed, it:

1. Downloads every enabled page/feed in `automation/sources.json`.
2. Classifies recruitment, admission, answer-key, result, and recruitment corrigendum/addendum links while excluding unrelated exam schedules, admit cards, tenders and administrative notices.
3. Reads linked HTML metadata/body text and up to the first 10 pages of linked PDFs.
4. Extracts only details it can verify (vacancies, qualifications, dates, advertisement number and age). Missing details remain “See Official Notification.”
5. De-duplicates notices using `data/seen-notices.json`, adds new records to `data/auto-jobs.json`, and commits only when data changes.
6. Recruitment, admission and recruitment-update notices use the existing vacancy cards/table/modal. Results and answer keys use the existing **Results & Answer Key** column. All new types can appear in the existing Breaking marquee.

The workflow stages and commits only the two files under `data/`; it never rewrites `index.html`, CSS, or the page structure, so scheduled runs cannot change the existing layout.

> **Activation required:** this repository connection could not add a file under `.github/workflows`. After merging, create `.github/workflows/update-job-alerts.yml` through GitHub's web editor and copy the complete contents of `automation/update-job-alerts.workflow.yml` into it. Commit that file to the default branch, then use **GitHub → Actions → Update job alerts → Run workflow** for the first scan. Until this one-time activation is completed, alerts can be updated manually with `python3 scripts/update_jobs.py` but the six-hour schedule will not run.

Configured official pages cover PSSSB advertisements/results, PPSC, Punjab Police, PSPCL, NVS recruitment/JNVST updates, SSC, UPSC, RRB Chandigarh and RCF Kapurthala. The curated homepage currently highlights RCF Advertisement A-1/2026 for 734 Act Apprentice seats, with the official RCF portal linked for verification.

#### Add another website or RSS/Atom feed

Add an object to the `sources` array in `automation/sources.json`:

```json
{
  "id": "new-board",
  "name": "New Recruitment Board",
  "department": "New Recruitment Board",
  "url": "https://example.gov.in/recruitment/",
  "type": "punjab",
  "categorySlug": "punjab-jobs",
  "location": "Punjab",
  "noticeTypes": ["recruitment", "admission", "answer-key", "result", "corrigendum"],
  "bootstrapCount": 1,
  "maxNewPerRun": 5,
  "includeKeywords": ["hiring notice"],
  "excludeKeywords": ["contract award"]
}
```

1. Open `automation/sources.json` and copy one complete object inside the `sources` array.
2. Give it a unique lowercase `id`, update its display `name`, `department`, and set `url` to the direct official notices page or RSS/Atom feed.
3. Set `type` to `punjab` or `central`; `categorySlug` controls the existing homepage filter used for recruitment/admission/update cards.
4. Set `noticeTypes` to any combination of `recruitment`, `admission`, `answer-key`, `result`, and `corrigendum`. The `corrigendum` type includes recruitment addenda.
5. Save, test with `python3 scripts/update_jobs.py --dry-run`, then commit the configuration. The next active six-hour workflow run starts monitoring it.

Additional options:

- `includeKeywords` and `excludeKeywords` are optional for a website that uses unusual wording. If a custom include keyword should be treated as something other than recruitment, set `defaultNoticeType` to one of the supported notice types.
- Use `bootstrapCount: 0` when adding an old results/archive page so historical notices are marked as seen but not published as new. Use `1` to publish its first current notice.
- If one organization has separate advertisement, result and admission pages, add each page as a separate source object with a unique `id` and the appropriate `noticeTypes`.
- On a source's first successful scan, the monitor marks all existing links as seen and publishes only `bootstrapCount` links. Later runs publish only unseen links.
- No generic monitor can reliably read literally every website. A site that renders notices only through JavaScript, blocks GitHub's IP addresses, requires login/CAPTCHA, or has no stable links needs its public RSS/API endpoint configured instead.
- After installing the template under `.github/workflows`, scheduled workflows run only from GitHub's default branch. Repository **Actions → General → Workflow permissions** must allow read/write access, and branch protection must permit the bot commit (or be adjusted to your preferred review flow).

Run and test locally:

```bash
python3 -m pip install -r automation/requirements.txt
python3 -m unittest discover -s tests -v
python3 scripts/update_jobs.py --dry-run
```

---

### 🔍 Google Search Console Setup

1. Go to **https://search.google.com/search-console** and sign in.
2. Click **Add property** → choose **URL prefix** → enter `https://employmentexpress.github.io/homepage/` (must match the canonical + sitemap URL exactly, including trailing `/`).
3. Choose **HTML tag** verification method → copy the `content` value (looks like `dBw...123`).
4. In `index.html` replace `REPLACE_WITH_YOUR_GOOGLE_VERIFICATION_CODE` inside:

   ```html
   <meta name="google-site-verification" content="REPLACE_WITH_YOUR_GOOGLE_VERIFICATION_CODE">
   ```

   with your real code, commit and push — GitHub Pages will deploy in ~1-2 min.
5. Back in Search Console click **Verify**.
6. After verification: **Sitemaps** → submit `https://employmentexpress.github.io/homepage/sitemap.xml` → then **Request indexing** for the homepage if needed.
7. Optional additional verification (if you prefer / need backup): download the `googleXXXX.html` file Google offers and place it at the repo root (e.g. `google123abc.html` with content `google-site-verification: google123abc.html`) — this repo already has `robots.txt` allowing crawl and `sitemap.xml` referenced.

> Keep the meta tag in place permanently — removing it can de-verify the property.

### 🚀 Local Preview

```bash
python3 -m http.server 8000 --bind 0.0.0.0
# open https://8000-<sandboxId>.e2b.app
```

---

### 📅 Current Data (2026)

- Titles, meta, OG/Twitter, H1, flash cards, and table headers now read **2026**
- Active recruitments updated to **15 Sep – 28 Oct 2026** (relative to 17 Aug 2026)
- Footer: © 2026 EMPLOYMENT EXPRESS

---

### 🔗 Quick Links

- Telegram (official): https://t.me/employment_express1
- WhatsApp Channel (official): https://whatsapp.com/channel/0029Va9xQHV4tRrxpVKaG93w
- YouTube — Subscribe YouTube Channel: https://www.youtube.com/channel/UCI39CbrtpEflEPabKeCAd9A
- NVS RO Chandigarh: https://navodaya.gov.in/nvs/ro/Chandigarh/en/home/
- PSSSB: https://sssb.punjab.gov.in — Punjab Police: https://punjabpolice.gov.in — PPSC: https://ppsc.gov.in — PSPCL: https://pspcl.in

---

*Disclaimer: Independent private portal, not affiliated with any government department. Verify details on official gazettes/websites.*
