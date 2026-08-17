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
- **Master Vacancy Table (2026)** — 10 active recruitments with `NEW JOB ALERT` & `Hot Post` badges, posts count, last date (Sep–Oct 2026), and `Apply/Info` modal
- **Job Detail Modal** — vacancy, location, apply mode, last date, dates & fees, age/eligibility, how-to-apply, PDF + Apply links, Web Share API
- **Admit Card & Results columns** — direct “Get” / “NEW” pulses with toast feedback including NVS Chandigarh & JNVST lists
- **Syllabus & Official Portals widgets** + direct links to Navodaya Vidyalaya Samiti RO Chandigarh (`https://navodaya.gov.in/nvs/ro/Chandigarh/en/home/`)
- **Floating Telegram/WhatsApp/YouTube buttons** + footer disclaimer (YouTube with headline “Subscribe YouTube Channel”)
- **SEO:** canonical, Open Graph, Twitter Card, Organization + WebSite JSON-LD, `robots.txt` + `sitemap.xml` (lastmod 2026-08-17)
- **A11y & Performance:** semantic headings (`sr-only` H1), ARIA, keyboard `Esc` to close modal, focus rings, custom scrollbar, `preconnect` hints

---

### 📁 Structure

```
/
├── index.html      # Single-page homepage (Tailwind CDN + Font Awesome + data-driven JS)
├── assets/
│   └── logo.png    # Favicon / brand logo (238 KB)
├── sitemap.xml     # Daily changefreq, priority 1.0
├── robots.txt      # Allow: / + sitemap
└── README.md
```

---

### 🛠 Tech

- **Tailwind CSS CDN** (plus `tailwind.config` brand palette: `brand-50 → 900`, accent)
- **Font Awesome 6.4**, **Plus Jakarta Sans + Tiro Gurmukhi** (Google Fonts)
- **Vanilla JS** — `jobDatabase` (10 entries, `type: punjab|central`, `categorySlug`), `admitCards`, `resultsList`, renderers (`renderPunjabColumn`, `renderCentralColumn`, etc.), filters (`filterJobs`, `filterByQual`, `filterByCategory`), modal & toast

To add / edit a vacancy, edit `jobDatabase` in `index.html`:

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
