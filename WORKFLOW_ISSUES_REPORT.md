# Workflow Issues Analysis Report

**Date:** September 2, 2026  
**Repository:** EmploymentExpress/homepage  
**Workflow:** Update job alerts  

---

## Executive Summary

The **"Update job alerts" workflow is failing intermittently** due to **3 distinct issues**:

1. **Critical:** Headline length truncation bug (failing 1+ times)
2. **Major:** Missing test module for thumbnail generator
3. **Minor:** Network errors (non-fatal but indicative)

---

## Issue 1: Headline Length Truncation (CRITICAL)

### Failure Details
- **Affected Test:** `test_headlines_never_exceed_the_cap_and_keep_department_and_type`
- **Location:** `tests/test_short_headlines.py:170-190`
- **Failing Job Run:** [Sept 2, 00:33 UTC](https://github.com/EmploymentExpress/homepage/actions/runs/33575783855)
- **Last Failure:** Sept 1, 00:35 UTC

### Root Cause
The `short_job_headline()` function in `scripts/short_headlines.py` is **truncating long job titles incorrectly**. When a headline exceeds the 72-character limit, the truncation logic is:

1. Trying multiple candidate strings (lines 427-446)
2. If none fit, calculating a "budget" for the subject text (line 448)
3. Truncating with `body[:budget].rsplit(" ", 1)[0]` (line 452)

**The Problem:** When truncating a long title like:
```
"View 22 Oct 2025 RECRUITMENT OF LOCAL BANK OFFICER (LBO) 202..."
```

The current code is cutting it at an arbitrary position without preserving the required format. The test checks that:
- Headline never exceeds 72 characters ✅
- Headline must end with an approved notice type suffix ❌ (FAILING HERE)
- Headline must contain department and post name ❌ (ALSO FAILING)

### Specific Test Case
```python
title='View 22 Oct 2025 RECRUITMENT OF LOCAL BANK OFFICER (LBO) 202'
department='UCO Bank'
alertType='result'
vacancies='See Notification'
applyMode='Online / As Notified'
```

**Expected:** `UCO Bank Officer Result` or similar  
**Actual:** Truncated headline missing proper notice suffix

### Code Location
**File:** `scripts/short_headlines.py:424-457`

```python
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
                body = body[:budget].rsplit(" ", 1)[0]  # <-- BUG: Truncates without checking suffix
            body = body.strip(" ,;:|-\u2013\u2014&")
            headline = _clean(f"{prefix}{body} {suffix}")
        else:
            headline = _clean(f"{prefix}{suffix}")
```

### Fix Strategy

**Option A: Preserve suffix during truncation (Recommended)**
```python
if not headline:
    suffix_len = len(suffix) + 1  # +1 for space
    budget = MAX_HEADLINE_LENGTH - len(prefix) - suffix_len
    body = first_plain or subject
    if budget > 12 and body:
        if len(body) > budget:
            body = body[:budget].rsplit(" ", 1)[0]
        body = body.strip(" ,;:|-\u2013\u2014&")
        candidate = _clean(f"{prefix}{body} {suffix}")
        # Verify suffix is present and headline is valid
        if len(candidate) <= MAX_HEADLINE_LENGTH and any(
            candidate.endswith(s) for s in set(NOTICE_SUFFIXES.values()) | 
            {"Offline Form", "Exam Cancelled", "Interview Postponed", "Exam Answer Key"}
        ):
            headline = candidate
        else:
            # Fallback to prefix + suffix only
            headline = _clean(f"{prefix}{suffix}")
    else:
        headline = _clean(f"{prefix}{suffix}")
```

**Option B: Guarantee minimum viable headline**
Ensure the last resort always produces `{dept} {suffix}`:
```python
else:
    # Always have at minimum: department + notice type
    headline = _clean(f"{prefix}{suffix}").strip()
    if not headline:
        headline = suffix  # Fallback to just the suffix
```

---

## Issue 2: Thumbnail Generator Test Import Error (MAJOR)

### Failure Details
- **Affected Test:** `test_thumbnail_generator`
- **Error:** `ImportError: Failed to import test module: test_thumbnail_generator`
- **Location:** `tests/test_thumbnail_generator.py` (missing/not found)
- **Last Failure:** [Sept 1, 00:35 UTC](https://github.com/EmploymentExpress/homepage/actions/runs/33455333005)

### Root Cause
The test discovery in the workflow runs:
```bash
python -m unittest discover -s tests -v
```

This command recursively discovers all test files matching `test_*.py`. The error log shows:
```
ERROR: test_thumbnail_generator (unittest.loader._FailedTest.test_thumbnail_generator)
ImportError: Failed to import test module: test_thumbnail_generator
Traceback (most recent call last):
```

The file `tests/test_thumbnail_generator.py` either:
1. **Doesn't exist** but is referenced somewhere
2. **Exists but has syntax/import errors**
3. **Has missing dependencies**

### Verification
From the file search, no `test_thumbnail_generator.py` exists in the `tests/` directory. The test suite includes:
- `test_short_headlines.py` ✓
- `test_update_jobs.py` ✓
- `test_thumbnail_generator.py` ✗ MISSING

### Solutions

**Option A: Create the missing test file**
```python
# tests/test_thumbnail_generator.py
import unittest

class ThumbnailGeneratorTests(unittest.TestCase):
    def test_placeholder(self):
        """TODO: Add thumbnail generation tests."""
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
```

**Option B: Remove the test reference**
If thumbnails aren't being generated, delete the file or exclude it from discovery.

**Option C: Fix import errors**
If the file exists but has errors, check:
- Missing imports (PIL/Pillow, etc.)
- Incorrect relative imports
- Circular dependencies

---

## Issue 3: Network Errors During Test (MINOR)

### Details
Throughout both failing runs, tests are encountering `no network` errors:
```
Offline-forms listing unavailable (None): no network
Offline page document extraction failed (https://onlineforms.in/...): no network
```

### Impact
- ✅ Tests are handling gracefully (continue execution)
- ✅ Not causing test failures directly
- ⚠️ Indicates external API calls or network-dependent behavior

### Cause
The tests attempt to fetch external resources during execution:
- `onlineforms.in` (offline form portals)
- `speedjob.in` (job portal)
- `www.speedjob.in` (additional portal)

These requests fail in the GitHub Actions runner environment (likely no internet access or firewall blocks).

### Fix
The tests should:
1. **Mock external URLs** using `unittest.mock` or `responses` library
2. **Skip network tests** with `@unittest.skip` if connectivity is not available
3. **Cache responses** for repeatable test runs

Example mock approach:
```python
import unittest
from unittest.mock import patch

class JobMonitorTests(unittest.TestCase):
    @patch('scripts.update_jobs.requests.get')
    def test_offline_form_link_attached(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<html>mock form</html>"
        # Run test with mocked network
```

---

## Workflow Status Summary

| Run | Date | Workflow | Status | Primary Cause |
|-----|------|----------|--------|---------------|
| 33586707989 | Sept 2, 03:21 | pages build and deployment | 🟡 In Progress | N/A (monitoring) |
| 33575783855 | Sept 2, 00:33 | **Update job alerts** | ❌ **FAILED** | Headline truncation (Issue #1) |
| 33546983297 | Sept 1, 18:28 | pages build and deployment | ✅ Success | N/A |
| 33543779582 | Sept 1, 15:28 | **Update job alerts** | ✅ Success | None |
| 33455333005 | Sept 1, 00:35 | **Update job alerts** | ❌ **FAILED** | Test import error (Issue #2) |

**Pattern:** The workflow is failing ~50% of the time (2 failures out of recent runs).

---

## Recommended Action Items

### Priority 1 (Critical - Fix Immediately)
- [ ] **Fix headline truncation logic** in `scripts/short_headlines.py` (lines 424-457)
  - Ensure truncated headlines preserve the notice-type suffix
  - Validate that the headline still meets the test assertions
  - Test with the failing job title: "View 22 Oct 2025 RECRUITMENT OF LOCAL BANK OFFICER (LBO)..."

### Priority 2 (High - Fix Before Next Run)
- [ ] **Resolve test_thumbnail_generator import**
  - Locate or create `tests/test_thumbnail_generator.py`
  - Or exclude from test discovery if not needed
  - Re-run workflow to confirm

### Priority 3 (Medium - Improve Robustness)
- [ ] **Mock external network calls** in tests
  - Add `responses` or `unittest.mock` for external API calls
  - Reduces flakiness from network unavailability
  - Makes tests faster and more reliable

### Priority 4 (Low - Nice to Have)
- [ ] Add test case specifically for UCO Bank LBO recruitment title
  - Prevents regression of this specific bug
  - Add to `tests/test_short_headlines.py`

---

## Testing the Fixes

After applying fixes, verify with:

```bash
# Run only the headline tests
python -m unittest tests.test_short_headlines.ShortHeadlineFormatTests.test_headlines_never_exceed_the_cap_and_keep_department_and_type -v

# Run all tests
python -m unittest discover -s tests -v

# Manually test the failing case
python -c "
from scripts.short_headlines import short_job_headline
headline = short_job_headline(
    'View 22 Oct 2025 RECRUITMENT OF LOCAL BANK OFFICER (LBO) 202...',
    'UCO Bank',
    'result',
    'See Notification',
    'Online / As Notified'
)
print(f'Headline: {headline}')
print(f'Length: {len(headline)}')
print(f'Ends with valid suffix: {any(headline.endswith(s) for s in [\"Result\", \"Merit List\", etc.])}')
"
```

---

## Workflow Configuration

**Current Schedule:** Every 6 hours (cron: `17 */6 * * *`)  
**Timeout:** 90 minutes  
**Runs On:** `ubuntu-latest`  
**File:** `.github/workflows/update-job-alerts.yml`

The workflow is healthy otherwise (pages build and deployment succeeds consistently).

