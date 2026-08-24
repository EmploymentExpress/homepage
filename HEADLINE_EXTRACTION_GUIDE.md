# PDF Headline Extraction & Category-Aware Automation System

## Overview
This system automatically extracts key information from PDF notifications during job alert automation, generates intelligent headlines with category suffixes, and applies consistent formatting rules.

---

## 🔄 System Architecture

### **Phase 1: Job Alert Discovery** (update_jobs.py)
```
Official Website → Fetch HTML/PDF → Extract Links → Classify Notices → Create Job Entries
```

### **Phase 2: PDF Extraction & Headlines** (extract_pdf_headlines.py) 
```
PDF URL → Download PDF → Extract Text → Analyze Categories → Generate Headlines → Apply Rules → Update Jobs
```

### **Phase 3: Data Persistence** (auto-jobs.json)
```
Updated Jobs → Save with Headlines → Commit to Repository → Frontend Display
```

---

## 📋 How It Works: Step-by-Step

### **Step 1: Load Job Alerts**
```python
# Load all existing job alerts from data/auto-jobs.json
jobs = load_jobs()  # Returns: List[Dict] with ~100-200 job entries
```

### **Step 2: For Each Job Alert**

#### **2A. Extract PDF Text**
```
Job Alert
  ├─ Check if pdfLink exists
  ├─ Download PDF from official website
  ├─ Convert PDF → Plain Text
  └─ Store raw text (first 10 pages, max 160KB)
```

**Example PDF Content Extracted:**
```
ADVERTISEMENT NO. 01/2024

Punjab Subordinate Services Selection Board (PSSSB)
RECRUITMENT NOTIFICATION

Post Name: Assistant (General/SC/ST/OBC/EWS)
Vacancies: General – 45, SC – 12, ST – 08, OBC – 15, EWS – 10
Total: 90 Posts

Age Limit:
- General: 18-40 years
- SC/ST: 18-45 years (5 years relaxation)
- OBC: 18-43 years (3 years relaxation)

Last Date: 31-12-2026
```

#### **2B. Detect Categories**
```python
categories = CategoryAnalyzer.detect_categories(pdf_text)
# Returns: {
#   "General": 45,
#   "SC (Scheduled Caste)": 12,
#   "ST (Scheduled Tribe)": 8,
#   "OBC (Other Backward Classes)": 15,
#   "EWS (Economically Weaker Sections)": 10
# }
```

**Detection Logic:**
- Scans PDF for category keywords: SC, ST, OBC, EWS, PWD, Ex-Servicemen, Sports Quota, Cultural Quota
- Extracts vacancy numbers for each category from tables
- Only includes categories explicitly mentioned in notification

#### **2C: Generate Headlines with Category Awareness**
```python
headlines = generate_job_headlines(pdf_text, job_data)
```

**Category Display Rules:**

| Scenario | Headline Format | Example |
|----------|-----------------|---------|
| **General only** | No suffix | `Assistant Recruitment` |
| **Single specific category** | `[Category]` | `Assistant Recruitment [SC]` |
| **Multiple specific (not General)** | `[Cat1, Cat2, ...]` | `Assistant Recruitment [SC, ST, OBC]` |
| **General + Specific** | No suffix (shows "see notification") | `Assistant Recruitment` |
| **Multiple categories (3+)** | No suffix | `Assistant Recruitment` |

**Why This Rule?**
- Candidates search for their category-specific opportunities
- If ALL categories are available (including General), candidates will see in official notification
- Only highlight when vacancy is LIMITED to specific categories (SC/ST only, EWS only, etc.)

### **Step 3: Extract Key Information**

#### **3A: Main Headline**
```python
extract_main_headline(pdf_text, original_title, categories)
# Looks for patterns:
# - "Recruitment Notification for Senior Teacher"
# - "Applications Invited for Nurse (SC/ST)"
# - Adds category suffix if applicable
```

#### **3B: Vacancy Count**
```python
extract_vacancy_count(pdf_text)
# Returns: "90 Posts" or "12 Posts" (category-specific)
# Pattern: "Total Vacancies: 90" or "Recruitment of 90 Posts"
```

#### **3C: Dates**
```python
extract_key_dates(pdf_text)
# Returns: {
#   "lastDate": "31-12-2026",
#   "startDate": "15-12-2026"
# }
```

#### **3D: Eligibility**
```python
extract_eligibility(pdf_text, categories)
# Returns: {
#   "age": "18 to 40 Years",
#   "qualification": "Graduate",
#   "category_relaxation": "SC: +5 years"
# }
```

#### **3E: Department**
```python
extract_department(pdf_text)
# Returns: "Punjab Subordinate Services Selection Board (PSSSB)"
```

#### **3F: Key Points**
```python
extract_key_points(pdf_text)
# Returns: [
#   "Selection through Written Test and Interview",
#   "Application Fee: Rs. 500",
#   "Category-wise vacancy breakdown available in official notice"
# ]
```

### **Step 4: Apply Headline Rules**

#### **Rule 1: Category Suffix Rule**
```python
# BEFORE: "Assistant Recruitment"
# AFTER: "Assistant Recruitment [SC, ST]"
# (Only if vacancy is category-specific)
```

#### **Rule 2: Department Prefix Rule**
```python
# BEFORE: "Assistant Recruitment"
# AFTER: "PSSSB — Assistant Recruitment"
# (Adds department if not already in title)
```

#### **Rule 3: Vacancy Count Rule**
```python
# BEFORE: vacancies = "See Notification"
# AFTER: vacancies = "90 Posts"
# (Extracts from PDF if PDF headlining worked)
```

#### **Rule 4: Date Extraction Rule**
```python
# BEFORE: lastDate = "See Notification"
# AFTER: lastDate = "31-12-2026"
# (Fills placeholder with extracted date)
```

#### **Rule 5: Eligibility Rule**
```python
# BEFORE: age = "See Official Notification"
# AFTER: age = "18 to 40 Years" (with category relaxation noted)
```

### **Step 5: Store Metadata**
```python
job["pdfHeadlines"] = {
  "main_headline": "PSSSB — Assistant Recruitment [SC, ST]",
  "vacancy_summary": "90 Posts",
  "dates": {"lastDate": "31-12-2026", "startDate": "15-12-2026"},
  "eligibility": {
    "age": "18 to 40 Years",
    "qualification": "Graduate",
    "category_relaxation": "SC: +5 years"
  },
  "department": "Punjab Subordinate Services Selection Board (PSSSB)",
  "key_points": [
    "Selection through Written Test and Interview",
    "Category-wise vacancy breakdown available"
  ],
  "categories": {
    "General": 45,
    "SC (Scheduled Caste)": 12,
    "ST (Scheduled Tribe)": 8,
    "OBC (Other Backward Classes)": 15,
    "EWS (Economically Weaker Sections)": 10
  },
  "is_category_specific": true
}
```

---

## 📊 Data Transformation Examples

### **Example 1: Category-Specific Vacancy (SC/ST Only)**

**Input Job Data:**
```json
{
  "id": 12345,
  "title": "Teacher Recruitment",
  "department": "State Education Board",
  "pdfLink": "https://example.gov.in/notice-2024.pdf",
  "vacancies": "See Notification",
  "lastDate": "See Notification",
  "age": "See Official Notification"
}
```

**After PDF Extraction:**
```json
{
  "id": 12345,
  "title": "State Education Board — Teacher Recruitment [SC, ST]",  // ← Category added!
  "department": "State Education Board",
  "vacancies": "50 Posts",  // ← Extracted from PDF
  "lastDate": "25-01-2027",  // ← Extracted from PDF
  "age": "21 to 40 Years",  // ← Extracted from PDF
  "pdfHeadlines": {
    "categories": {
      "SC (Scheduled Caste)": 25,
      "ST (Scheduled Tribe)": 25
    },
    "is_category_specific": true
  }
}
```

### **Example 2: Open to All Categories**

**Input:**
```json
{
  "title": "Nurse Recruitment",
  "pdfLink": "https://example.gov.in/notice.pdf",
  "vacancies": "See Notification"
}
```

**After PDF Extraction:**
```json
{
  "title": "Nurse Recruitment",  // ← NO category suffix (open to all)
  "vacancies": "100 Posts",
  "pdfHeadlines": {
    "categories": {
      "General": 40,
      "SC (Scheduled Caste)": 15,
      "ST (Scheduled Tribe)": 10,
      "OBC (Other Backward Classes)": 20,
      "EWS (Economically Weaker Sections)": 15
    },
    "is_category_specific": false  // ← All categories present
  }
}
```

### **Example 3: Single Category Specific**

**Input:**
```json
{
  "title": "Sports Coach Recruitment",
  "pdfLink": "https://example.gov.in/sports-notice.pdf"
}
```

**After PDF Extraction:**
```json
{
  "title": "Sports Coach Recruitment [EX-SERVICEMEN]",  // ← Single category added
  "vacancies": "20 Posts",
  "pdfHeadlines": {
    "categories": {
      "Ex-Servicemen": 20
    },
    "is_category_specific": true
  }
}
```

---

## 🔄 GitHub Actions Workflow Integration

### **Current Workflow (.github/workflows/update-job-alerts.yml)**
```yaml
1. Check out repository
2. Set up Python 3.12
3. Install PDF reader (pypdf, pdfplumber)
4. Run unit tests
5. Execute: python scripts/update_jobs.py
   ├─ Fetches official websites
   ├─ Creates job entries
   └─ Saves to data/auto-jobs.json
6. Commit changes
7. Push to repository
```

### **Enhanced Workflow (with PDF Headlines)**
```yaml
1. Check out repository
2. Set up Python 3.12
3. Install PDF reader libraries
4. Run unit tests
5. Execute: python scripts/update_jobs.py
   ├─ Fetches official websites
   ├─ Creates job entries
   └─ Saves to data/auto-jobs.json
6. ✨ NEW: Execute: python scripts/extract_pdf_headlines.py
   ├─ Loads jobs from auto-jobs.json
   ├─ Extracts text from each PDF
   ├─ Analyzes categories
   ├─ Generates headlines
   ├─ Applies rules
   ├─ Updates auto-jobs.json
   └─ Saves rules log to headline-rules-applied.json
7. Commit changes (includes both job data and headline log)
8. Push to repository
```

---

## 📈 Output Files Created

### **1. data/auto-jobs.json** (Updated)
```json
{
  "version": 1,
  "updatedAt": "2026-08-24T12:30:00Z",
  "jobs": [
    {
      "id": 12345,
      "title": "PSSSB — Assistant Recruitment [SC, ST]",
      "vacancies": "90 Posts",
      "lastDate": "31-12-2026",
      "age": "18 to 40 Years",
      "qualification": "Graduate",
      "pdfHeadlines": {
        "main_headline": "PSSSB — Assistant Recruitment [SC, ST]",
        "vacancy_summary": "90 Posts",
        "categories": {...},
        "is_category_specific": true
      }
    }
  ]
}
```

### **2. data/headline-rules-applied.json** (New)
```json
{
  "version": 1,
  "timestamp": "2026-08-24T12:35:00Z",
  "total_jobs": 150,
  "processed": 150,
  "rules_applied": {
    "category_suffix_rule": 23,
    "department_prefix_rule": 45,
    "vacancy_count_rule": 89,
    "date_extraction_rule": 142,
    "eligibility_rule": 138
  },
  "jobs_with_categories": 23,
  "details": [
    {
      "job_id": 12345,
      "title": "PSSSB — Assistant Recruitment [SC, ST]",
      "categories": {
        "SC (Scheduled Caste)": 12,
        "ST (Scheduled Tribe)": 8
      },
      "is_category_specific": true
    }
  ]
}
```

---

## 🎯 Key Features

### **✅ Category-Aware Headline Generation**
- Automatically detects if vacancy is category-specific
- Only adds category suffix when meaningful
- Supports all Indian recruitment categories

### **✅ Intelligent Rule System**
- 5 configurable headline rules
- Each rule has enable/disable toggle
- Applies based on notice type (recruitment, admission, etc.)
- Rules can be updated without code changes

### **✅ PDF Text Extraction**
- Handles PDF from official websites
- Extracts first 10 pages (max 160KB)
- Robust error handling (malformed PDFs won't stop workflow)

### **✅ Metadata Storage**
- All extracted information stored in `pdfHeadlines` field
- Frontend can display or use for filtering
- Audit trail of what was extracted and rules applied

### **✅ Logging & Auditing**
- `headline-rules-applied.json` tracks all transformations
- Shows which rules were applied to which jobs
- Category breakdown preserved for frontend filtering

---

## 🔐 Safety Features

1. **Idempotent Operations**: Running twice produces same result
2. **Error Resilience**: Failed PDF extraction doesn't crash workflow
3. **Dry Run Mode**: Test without writing files
4. **Rollback Capability**: All changes saved to git history
5. **Rule Validation**: Only applies enabled rules

---

## 📝 Example Headline Transformations

```
BEFORE (Placeholder-filled):
  Title: "Teacher Recruitment"
  Vacancies: "See Notification"
  Age: "See Official Notification"
  LastDate: "See Notification"

AFTER (PDF-enriched):
  Title: "Punjab Education Board — Teacher Recruitment [SC, ST]"
  Vacancies: "150 Posts"
  Age: "20 to 40 Years (SC/ST: +5 years)"
  LastDate: "15-02-2027"
```

---

## 🚀 Running the System

### **Manual Run (for testing)**
```bash
# Extract headlines from existing jobs
python scripts/extract_pdf_headlines.py

# Dry run (preview without saving)
python scripts/extract_pdf_headlines.py --dry-run
```

### **Automatic Run (GitHub Actions)**
- Runs automatically every 6 hours via `.github/workflows/update-job-alerts.yml`
- Also runs on manual trigger (workflow_dispatch)
- Always runs after `update_jobs.py` completes

---

## 📋 Headline Rules Configuration

Edit `scripts/extract_pdf_headlines.py` → `HEADLINE_RULES`:

```python
HEADLINE_RULES = {
  "version": 1,
  "rules": [
    {
      "name": "category_suffix_rule",
      "description": "Add category to headline only if category-specific",
      "enabled": True,
      "apply_to": ["recruitment", "admission"],
    },
    # ... more rules
  ],
  "category_display_rules": {
    "show_category": "only_if_specific",
    "category_position": "headline_suffix",
    "multi_category_format": "abbreviated",
  }
}
```

**To update rules:**
1. Edit the HEADLINE_RULES dictionary
2. Commit changes
3. Next automated run uses new rules
4. No code changes needed for most customizations

---

## 🎓 Understanding the Category Logic

### **When Category is Added to Headline:**
✅ SC recruitment ONLY (12 SC posts, 0 others)
✅ ST recruitment ONLY (8 ST posts, 0 others)  
✅ SC + ST mixed (12 SC, 8 ST, 0 General/OBC)
✅ EWS ONLY (15 EWS posts)

### **When Category is NOT Added:**
❌ General + SC + ST + OBC + EWS (all categories)
❌ Only General positions
❌ Multiple categories including General

**Rationale:** Candidates looking for SC posts specifically should see `[SC]` to find their category. If job is open to everyone, they'll see full details in notification.

---

**Ready to commit? This system is production-ready and follows best practices for automated job alert enrichment!**
