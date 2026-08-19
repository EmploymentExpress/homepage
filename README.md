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
- **Time-limited new alerts** — newly discovered notices show a 🔥 icon with a `NEW` label for 72 hours from publication (or discovery when publication time is unavailable); they appear in the Breaking marquee for 24 hours and then are removed automatically
- **⏱️ "Just In" tag + newest-first columns** — newly discovered official notices appear at the top of their respective section (Latest Punjab Jobs, All India & NVS/Central, Results & Answer Key, Admission & Courses, and the Master Table) carrying a **Just In** tag that stays for **48 hours** and is removed automatically after publication; dated recruitments leave the active lists after their deadline
- **🏛️ Department-specific vacancy names** — every published vacancy title includes the full recruiting authority plus the real post/notice subject (for example, `Punjab State Legal Services Authority (PULSA) — Clerk Recruitment`); generic action/navigation labels such as `Application for Clerk`, `Other Links`, and `Close menu` are rewritten or rejected
- **📄 Offline application forms** — the configured offline-form portals (`OFFLINE_FORM_HOSTS` in `scripts/update_jobs.py`: `onlineforms.in`, `speedjob.in`) are the **single source for offline-apply vacancies**: only vacancies whose portal page says offline-apply and whose active deadline/recruiting authority can be verified are published, under a **department-specific job name**. Online-apply vacancies come from the other discovery feeds; an offline vacancy found on a discovery feed is used only when the portal has no entry for it. Each offline job carries just two links: the **direct application-form PDF** (`wp-content/uploads/...-Application-Form-...pdf`, masked behind `redirect.html?f=<token>`) and the **official notification** — the portal-hosted notification PDF when the official website has no copy, otherwise the official website/notification link the portal page points to. The portal's URL and branding never appear on the page; the real URLs live only in `data/offline-redirects.json`
- **Last Date Reminders** — auto-populated 2 days (48 hours) before each job's `lastDate`, with a live per-second countdown timer; jobs leave the list automatically once their deadline passes (see extension handling below)
- **Last-date extension handling** — when the monitor finds an official corrigendum extending a deadline, the affected job is marked **Last Date Extended** with the old date struck through → new date and a link to the notice, instead of being removed
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
│   ├── offline-forms.json                   # Maintained offline-apply form registry (offline-form portals)
│   └── requirements.txt                    # PDF extraction dependency
├── data/
│   ├── auto-jobs.json                       # Generated jobs consumed by the page
│   ├── notification-source-links.json       # User-added websites monitored on every future run
│   ├── offline-redirects.json               # Generated token → offline-form URL map (masked)
│   └── seen-notices.json                    # Generated de-duplication state
├── redirect.html                            # Client-side token resolver for offline forms (no external URL shown)
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

### 🤖 AI Agent & Automation Guidelines (PROTECTED LAYOUT)

**The homepage layout is frozen** — the *Classic 4-Column Mega Grid* (restored in PR #17):

1. Quick Notice Banners / Highlight Grid
2. **Main 4-Column Mega Grid** — Punjab Jobs | All India & NVS/Central | Admit Card 2026 | Results & Answer Key
3. **Last Date Reminders** (red section)
4. Admission & Courses
5. Qualification Quick Finder Pills
6. Master Vacancy Table
7. Quick Resources & State Syllabus Widget

Any AI agent (or human) asked to *update* the site must change **only the instructed details** —
job entries, dates, links, text, generated `data/*.json` files — and must **not** reorder sections,
change the grid structure, or alter element `id`s/`class`es unless a layout change is explicitly
requested.

**Mandatory Link & Badge Rules for Agents and Automation:**
1. **🔗 Direct Official Links:** `pdfLink` (Official Notice/PDF) and `applyLink` (Apply Online Portal) MUST ALWAYS point to the specific advertisement notification document/page and direct registration portal — NEVER generic root homepages (like `https://sssb.punjab.gov.in` or `https://pspcl.in`).
2. **⏱️ "Just In" Tag & 48-Hour Auto-Expiry:** Whenever new job details are added or automated batches run, they MUST carry a `publishedAt`/`discoveredAt` timestamp so the frontend tags them with **"Just In"**. This badge/tag automatically expires and is removed 48 hours after publication.
3. **🆕 Newest First / Active Only:** Vacancy columns and the master table order notices by publication/discovery time (newest first), and dated applications are removed after their deadline.
4. **🏛️ Full Department + Post Title:** Every vacancy title MUST visibly name its full recruiting department and actual post/notice subject; action/navigation labels are rewritten or rejected.

Full rules: **[`AGENTS.md`](AGENTS.md)**.

This is enforced, not just documented:

- `tests/test_layout_order.py` pins the exact section order, the 4-column grid classes and unique
  anchor IDs — the GitHub Actions workflow runs it on every run, so layout-drift edits **fail CI**.
- `scripts/update_jobs.py` snapshots & restores `index.html` and `assets/` around every monitoring
  run (`PROTECTED_LAYOUT_PATHS`), so automation can only write generated data to `data/*.json`.
- Guard comments at the top of `<main>` and above the JS datasets in `index.html` repeat the rules
  inline for any agent editing the file directly.

---

### 🤖 Automatic Job Alert Setup

The ready-to-install workflow template in `automation/update-job-alerts.workflow.yml` is configured to run once every six hours (`17 */6 * * *`, in UTC) and supports manual runs. Once installed, it:

1. Downloads every enabled page/feed in `automation/sources.json`.
2. Classifies recruitment, admission, answer-key, result, and recruitment corrigendum/addendum links while excluding unrelated exam schedules, admit cards, tenders and administrative notices.
3. Reads linked HTML metadata/body text and up to the first 10 pages of linked PDFs.
4. Extracts only details it can verify (vacancies, qualifications, dates, advertisement number and age). Missing details remain “See Official Notification.”
5. De-duplicates notices using `data/seen-notices.json`, adds new records to `data/auto-jobs.json`, and commits only when data changes.
6. Recruitment, admission and recruitment-update notices use the existing vacancy cards/table/modal. Results and answer keys use the existing **Results & Answer Key** column. All new types can appear in the existing Breaking marquee.

The automation is protected at two layers. `scripts/update_jobs.py` snapshots `index.html` and `assets/` before every CLI run and automatically restores them if any parser or dependency attempts a layout change. The workflow also stages and commits only `data/auto-jobs.json` and `data/seen-notices.json`, so scheduled recruitment updates cannot alter the website layout, CSS, logo/assets, or page structure.

> **Activation required:** this repository connection cannot add a file under `.github/workflows` (it lacks the `workflows` permission). Create `.github/workflows/update-job-alerts.yml` through GitHub's web editor and copy the complete contents of `automation/update-job-alerts.workflow.yml` into it. Commit that file to the default branch, then use **GitHub → Actions → Update job alerts → Run workflow** for the first scan. Until this one-time activation is completed, alerts can be updated manually with `python3 scripts/update_jobs.py` but the six-hour schedule will not run.

The monitor currently has these official recruitment sources enabled:

1. **Punjab State Legal Services Authority (PULSA)** — `https://punjab.nalsa.gov.in/notice-category/recruitments/`
2. **AIIMS Recruitments** — `https://aiimsexams.ac.in/landingpage/courses/68dbbb27b7b096817673976e`
3. **AIIMS Academic Courses** — `https://aiimsexams.ac.in/landingpage/courses/68dbbb27b7b096817673976f`

All other boards that were previously configured (PSSSB, PPSC, Punjab Police, PSPCL, PNRC, NVS, SSC, UPSC, RRB Chandigarh, RCF Kapurthala, AIIMS Bathinda Non-Faculty/Project, PGIMER Chandigarh) are still listed in `automation/sources.json` but are switched off with `"enabled": false`, so automatic updates are published **only from PULSA and the two AIIMS Exams links**. The discovery headline feeds (HaryanaJobs / RozgarNews) are also switched off (`automation/discovery-feeds.json` has an empty `feeds` list) so no update from any other website can enter the feed. To re-enable a board, set its `enabled` flag to `true`; to re-enable discovery, restore the feed objects in `automation/discovery-feeds.json`. District court / eCourts pages are not monitored. The curated homepage currently highlights RCF Advertisement A-1/2026 for 734 Act Apprentice seats, with the official RCF portal linked for verification.

#### Discovery-only feeds (HaryanaJobs / RozgarNews)

`automation/discovery-feeds.json` lists **headline scanners only**. They are not published sources. **Currently the `feeds` list is empty, so discovery is switched off** — this keeps automatic updates limited to PULSA and the two enabled AIIMS Examinations links. If discovery is re-enabled later, this is how it behaves:

1. The monitor reads headlines from HaryanaJobs and RozgarNews.
2. It extracts the recruiting organisation name from the headline.
3. It matches that name against the approved official list (`automation/sources.json` plus `automation/official-organizations.json`).
4. On a match, it opens the **official** government recruitment page and extracts dates, vacancies, qualifications, PDFs and apply links from that page.
5. If no approved official organisation matches, the headline is skipped.
6. HaryanaJobs / RozgarNews URLs, branding and article text are never stored in `data/auto-jobs.json` and never shown on the website.

Add another official board by appending an object to `automation/official-organizations.json` (`id`, `name`, `url`, `aliases`). Do **not** put aggregator URLs in `automation/sources.json` or `data/notification-source-links.json`.

#### Add another website or RSS/Atom feed

For a website that should be monitored automatically in all future runs, add its URL to `data/notification-source-links.json`. A plain URL is enough:

```json
{
  "version": 1,
  "links": [
    "https://example.gov.in/recruitment/"
  ]
}
```

You can also provide metadata when the page needs filtering or a non-default category:

```json
{
  "url": "https://example.gov.in/recruitment/",
  "name": "Example Recruitment Board",
  "department": "Example Recruitment Board",
  "type": "central",
  "categorySlug": "central",
  "location": "All India",
  "noticeTypes": ["recruitment", "result", "corrigendum"],
  "includeKeywords": ["apprentice"]
}
```

The monitor automatically converts every valid link in this registry into a source on every run, de-duplicates links already present in `automation/sources.json`, and remembers discovered notices for future scans. No Python code change is needed after adding a link. For a permanently curated source with custom settings, you can still add an object directly to the `sources` array in `automation/sources.json`:

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

#### Last-date reminders & extension handling

The **Last Date Reminders** section and its extension handling are split across two layers:

1. **Frontend (`index.html`)** — `renderLastDateReminders()` scans `jobDatabase` for any job whose `lastDate` (`DD-MM-YYYY`, optionally `DD-MM-YYYY HH:MM`) falls within the next 48 hours and renders each one with a live countdown that ticks every second. When a job has `lastDateExtended: true` it is shown with a green **Last Date Extended** badge, the original date ~~struck through~~ and the new date alongside a “View notice” link to the official corrigendum. A job drops out of the reminders only once its *effective* `lastDate` has passed — so an extended job is never silently removed.
2. **Monitor (`scripts/update_jobs.py`)** — the browser page cannot call government sites directly (CORS), so the six-hour monitor is what actually checks official websites. `detect_extension()` recognises explicit extension corrigenda (phrases like *“last date extended”*, *“extended up to/till/until”*, *“extension of last date”*) and reads the new date; `apply_extensions()` links that corrigendum back to its original recruitment (matched by advertisement number first, then department + title overlap) and sets `originalLastDate`, `lastDate` (new), `lastDateExtended: true`, `extendedLastDate`, and `extensionNoticeUrl`. If an extension is announced but no new date can be read, deadlines are left untouched rather than guessed.

> Because extension detection relies on the scheduled scan (every six hours), a deadline extended only through an un-indexed PDF or a JS-only page may not be picked up — the same limitation that applies to the rest of the automatic alert feed.

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

- Titles, meta, OG/Twitter, H1, section cards, and table headers now read **2026**
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
