#!/usr/bin/env python3
"""Read-only source diagnostics: direct -> Chromium -> mirrors -> observed alternatives.

Never writes job data, source registries, fingerprints or publication health.
Browser/API evidence is diagnostic only, not an automatic publication input.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

try:
    from scripts import update_jobs as monitor
except ModuleNotFoundError:  # python scripts/check_source_access.py
    import update_jobs as monitor

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2 * 1024 * 1024
HTML_ARTIFACT_BYTES = 512 * 1024

# ---------------------------------------------------------------------------
# Run wall-clock budget: the read-only diagnostic always finishes.
#
# The registry now holds 200+ official sources and every probe may spend two
# direct attempts, one Chromium render, two mirrors and two observed
# alternative links. A single network call can also block far past its own
# socket timeout (slow-drip response body, resolver retry storm, wedged
# Chromium IPC channel), so a per-call timeout alone does not bound the step.
# On 2026-10-20 the scheduled run was killed by the 18-minute
# "Check direct access, browser rendering, mirrors and official alternatives"
# step cap: the 15-minute soft budget had expired, yet probes in flight (and
# the ThreadPoolExecutor shutdown that waits for them) kept the step alive
# until GitHub cancelled it, so the run counted as a workflow failure.
#
# Three bounds keep that from happening again:
#   * ``budgetSeconds``          - soft stop: no new source probe is started.
#   * ``probeSeconds``           - hard stop for one source's attempt sequence.
#   * ``attemptSeconds``         - hard stop for one fetch + assessment; the
#                                  call runs in a daemon thread that is
#                                  abandoned and reported as an unavailable
#                                  attempt when it overruns.
# The run then stops at ``budgetSeconds + overrunGraceSeconds`` and publishes
# the evidence it has (``complete: false`` = partial report, unfinished
# targets are ``deferred``, never healthy). Source order rotates every run, so
# a partial pass does not starve the tail of the registry.
# ``budgetSeconds + overrunGraceSeconds + attemptSeconds`` must stay below the
# workflow step's ``timeout-minutes`` — guard-tested in
# tests/test_source_access.py (DiagnosticBudgetTests).
DEFAULT_BUDGET_SECONDS = 13 * 60
DEFAULT_OVERRUN_GRACE_SECONDS = 90
DEFAULT_PROBE_SECONDS = 90
DEFAULT_ATTEMPT_SECONDS = 40
DEFAULT_WORKERS = 4
BLOCK_MARKERS = (
    "verify you are human", "captcha challenge", "access denied", "403 forbidden",
    "there is no row at position 0", "server error in '/' application",
    "checking your browser", "just a moment...",
)
LINK_TERMS = re.compile(r"(?i)\b(?:recruitment|careers?|vacanc(?:y|ies)|advertisements?|notices?|openings?)\b")


@dataclass
class Payload:
    url: str
    status: int
    content_type: str
    data: bytes
    error: str = ""


def host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.")


def public_url(url: str) -> bool:
    """Reject local endpoints and embedded credentials before any network call."""
    try:
        parts = urllib.parse.urlsplit(url)
        hostname = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme not in {"https", "http"} or parts.username or parts.password:
            return False
        if not hostname or hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            return False
        if parts.port not in {None, 80, 443, 8080, 8443}:
            return False
        try:
            return ipaddress.ip_address(hostname).is_global
        except ValueError:
            return "." in hostname
    except ValueError:
        return False


@lru_cache(maxsize=2048)
def public_dns(hostname: str) -> bool:
    try:
        addresses = socket.getaddrinfo(hostname, None)
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (OSError, ValueError):
        return False


def require_public(url: str) -> None:
    if not public_url(url) or not public_dns(urllib.parse.urlsplit(url).hostname or ""):
        raise ValueError("URL is not a resolvable public endpoint")


def run_bounded(callback, seconds: float):
    """Run ``callback`` in a daemon worker and give up once ``seconds`` pass.

    ``socket`` and Playwright calls can block well past their own timeouts, so a
    timeout passed *into* them is not a bound on the caller. Running the work in
    a daemon thread makes the abandonment real: the probe records the attempt as
    unavailable and returns to the run budget, and a still-wedged worker cannot
    keep the process (and therefore the workflow step) alive.
    """
    outcome: dict[str, object] = {}

    def target():
        try:
            outcome["value"] = callback()
        except BaseException as exc:  # reported to the caller as an attempt error
            outcome["error"] = exc

    worker = threading.Thread(target=target, name="source-access-attempt", daemon=True)
    worker.start()
    worker.join(max(0.0, float(seconds)))
    if worker.is_alive():
        raise TimeoutError(f"Attempt abandoned after {float(seconds):.0f}s")
    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    return outcome.get("value")


def redact_url(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
        # Keep only parameter names; tokens and session IDs must not be logged.
        query = urllib.parse.urlencode([(key, "REDACTED") for key, _ in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)])
        netloc = parts.netloc.rsplit("@", 1)[-1]
        return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, query, ""))
    except ValueError:
        return "[invalid URL]"


def redact_text(text: str) -> str:
    return re.sub(r"https?://[^\s<>\"']+", lambda m: redact_url(m.group()), str(text))


def sanitized_html(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<script\b[^>]*>.*?</script\s*>", "<!-- script omitted -->", text)
    text = re.sub(r"(?is)<input\b[^>]*>|<textarea\b[^>]*>.*?</textarea\s*>", "<!-- form value omitted -->", text)
    text = re.sub(r"(?is)<meta\b[^>]*(?:csrf|token)[^>]*>", "<!-- token metadata omitted -->", text)
    # Cover relative as well as absolute query-bearing href/src values.
    text = re.sub(r'''(?i)((?:href|src|action)\s*=\s*)(["'])(.*?)\2''',
                  lambda m: m[1] + m[2] + redact_url(m[3]) + m[2], text)
    return redact_text(text).encode("utf-8")[:HTML_ARTIFACT_BYTES].decode("utf-8", errors="ignore")


class PublicRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_host: str | None):
        self.allowed_host = allowed_host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        require_public(target)
        if self.allowed_host and host(target) != self.allowed_host:
            raise ValueError("Cross-host redirect needs manual review: " + redact_url(target))
        if urllib.parse.urlsplit(req.full_url).scheme == "https" and urllib.parse.urlsplit(target).scheme != "https":
            raise ValueError("Refusing HTTPS downgrade redirect")
        return super().redirect_request(req, fp, code, msg, headers, target)


def http_fetch(url: str, timeout: int, *, same_host: bool = True) -> Payload:
    require_public(url)
    opener = urllib.request.build_opener(PublicRedirects(host(url) if same_host else None))
    request = urllib.request.Request(url, headers={
        "User-Agent": monitor.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-IN,en;q=0.8", "X-Return-Format": "html",
    })
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc  # capture the HTTP error page for diagnosis, never as success
    with response:
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Response exceeds diagnostic download limit")
        return Payload(response.geturl(), response.code, response.headers.get_content_type(), data)


def browser_request_allowed(url: str, method: str, *, navigation: bool, origin: str) -> bool:
    if method not in {"GET", "HEAD"} or not public_url(url):
        return False
    if navigation and host(url) != host(origin):
        return False
    if navigation and origin.startswith("https:") and not url.startswith("https:"):
        return False
    return public_dns(urllib.parse.urlsplit(url).hostname or "")


def browser_fetch(url: str, timeout: int, wait_ms: int, directory: Path) -> Payload:
    """Fresh unauthenticated browser; no form submissions, API replay or CAPTCHA solving."""
    require_public(url)
    from playwright.sync_api import sync_playwright  # optional outside diagnostic workflow

    api: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 720},
                                          accept_downloads=False, service_workers="block")
            page = context.new_page()

            def route_request(route):
                request = route.request
                allowed = browser_request_allowed(request.url, request.method,
                    navigation=request.is_navigation_request(), origin=url)
                if allowed:
                    route.continue_()
                else:
                    route.abort()

            context.route("**/*", route_request)
            # Prevent WebSockets from reaching internal services on self-hosted runners.
            if hasattr(context, "route_web_socket"):
                context.route_web_socket("**/*", lambda ws: ws.close())

            def observe(response):
                request = response.request
                if request.resource_type not in {"fetch", "xhr"} or len(api) >= 100:
                    return
                if host(response.url) != host(url) and not host(response.url).endswith("." + host(url)):
                    return
                api.append({"url": redact_url(response.url), "method": request.method,
                            "status": response.status, "type": request.resource_type})

            page.on("response", observe)
            status, error = 0, ""
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                status = response.status if response else 0
                page.wait_for_timeout(wait_ms)
            except Exception as exc:
                error = redact_text(str(exc))[:500]
            content = page.content().encode("utf-8")
            try:
                page.screenshot(path=str(directory / "browser.png"), full_page=False, timeout=5000)
            except Exception:
                pass  # rendering failure is already reported; screenshot is best effort
            (directory / "api-requests.json").write_text(json.dumps(api, indent=2) + "\n")
            return Payload(page.url, status, "text/html", content[:MAX_BYTES], error)
        finally:
            browser.close()


def assess(payload: Payload, source: dict) -> dict:
    if payload.error:
        return {"status": "unavailable", "reason": redact_text(payload.error)}
    if not 200 <= payload.status < 300:
        return {"status": "blocked" if payload.status in {401, 403, 429} else "unavailable",
                "reason": f"HTTP {payload.status}"}
    text = payload.data.decode("utf-8", errors="replace")
    if any(marker in text.lower() for marker in BLOCK_MARKERS) or monitor.is_error_stub(text):
        return {"status": "blocked", "reason": "Access challenge or server error page; manual review required"}
    if not payload.data.strip():
        return {"status": "unavailable", "reason": "Empty response"}
    if payload.data.startswith(b"%PDF-"):
        return {"status": "reachable-pdf", "reason": "PDF bytes received; contents/deadline still require verification"}
    download = monitor.Download(payload.url, payload.content_type, payload.data)
    if source.get("discovery"):
        candidates = [c for c in monitor.discovery_candidates(download) if monitor.looks_like_discovery_headline(c)]
    else:
        candidates = monitor.deduplicate_candidates(
            list(monitor.source_candidates(download)) + list(monitor.page_source_candidates(download, source)))
        candidates = [c for c in candidates if monitor.looks_like_notice(c, source)
                      and not monitor.is_discovery_host(c.url) and not monitor.is_offline_form_url(c.url)]
    if candidates:
        return {"status": "reachable-feed" if source.get("discovery") else "reachable-notices",
                "candidateCount": len(candidates),
                "examples": [{"title": c.title[:180], "url": redact_url(c.url)} for c in candidates[:5]],
                "reason": "Candidate links found, not a verified/published job"}
    return {"status": "reachable-no-notices", "reason": "Page loaded but no supported notice links found"}


def alternative_links(payload: Payload, source: dict, limit: int) -> list[str]:
    if source.get("discovery") or not 200 <= payload.status < 300:
        return []
    if assess(payload, source)["status"] == "blocked":
        return []
    _, parser = monitor.parse_html(payload.data.decode("utf-8", errors="replace"), payload.url)
    links = []
    for url, label in parser.raw_links:
        if not LINK_TERMS.search(label):
            continue
        url = monitor.canonical_url(url)
        if not public_url(url) or host(url) != host(source["url"]):
            continue
        if source["url"].startswith("https:") and not url.startswith("https:"):
            continue
        if url == monitor.canonical_url(source["url"]) or url in links:
            continue
        links.append(url)
        if len(links) >= limit:
            break
    return links


def mirror_payload(url: str, template: str, timeout: int) -> Payload:
    require_public(url)
    mirror_url = template.format(quoted=urllib.parse.quote(url, safe=""), url=url)
    payload = http_fetch(mirror_url, timeout, same_host=False)
    data, content_type = payload.data, payload.content_type
    if payload.status == 200 and ("json" in content_type or data.startswith(b"{")):
        try:
            contents = json.loads(data).get("contents")
            if isinstance(contents, str):
                data, content_type = contents.encode("utf-8")[:MAX_BYTES], "text/html"
        except (ValueError, AttributeError):
            pass
    # Mirrors are transport, never an authority or the base for relative links.
    return Payload(url, payload.status, content_type, data, payload.error)


def load_sources() -> list[dict]:
    config = monitor.read_json(monitor.DEFAULT_CONFIG, {}).get("sources", [])
    official = monitor.read_json(monitor.DEFAULT_OFFICIAL_ORGS, {}).get("organizations", [])
    entries = [s for s in config if s.get("enabled", True) and not s.get("role")]
    entries += [s for s in official + monitor.additional_link_sources() if s.get("enabled", True)]
    entries += [dict(feed, discovery=True) for feed in monitor.load_discovery_feeds()]
    unique = {}
    for source in entries:
        url = monitor.canonical_url(source.get("url", ""))
        if not url:
            continue
        discovery = monitor.is_discovery_host(url) or monitor.is_offline_form_url(url)
        if discovery and not source.get("discovery"):
            continue
        if url in unique:
            unique[url]["proxyFallback"] = unique[url].get("proxyFallback", False) or source.get("proxyFallback", False)
            unique[url]["aliases"].append(source["id"])
            continue
        unique[url] = dict(source, url=url, aliases=[source["id"]], discovery=discovery)
    return list(unique.values())


def probe(source: dict, options: dict, output: Path, deadline: float, rotation: int = 0) -> dict:
    url = source["url"]
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    directory = output / key
    directory.mkdir(parents=True, exist_ok=True)
    result = {"id": source["id"], "url": redact_url(url), "kind": "discovery" if source.get("discovery") else "official",
              "status": "unavailable", "attempts": [], "artifacts": key}
    alternatives: list[str] = []
    documents: dict[str, Payload] = {}
    # A single source may never hold a worker (or the workflow step) open past
    # its own probe budget, even when every transport misbehaves. ``deadline``
    # is the run budget; ``stop_at`` adds the per-source cap.
    stop_at = min(deadline, time.monotonic() + float(options.get("probeSeconds", DEFAULT_PROBE_SECONDS)))
    attempt_seconds = float(options.get("attemptSeconds", DEFAULT_ATTEMPT_SECONDS))

    def attempt(method, target, fetch):
        remaining = stop_at - time.monotonic()
        if remaining <= 0:
            reason = ("Run budget exhausted" if time.monotonic() >= deadline
                      else "Source probe budget exhausted")
            result["attempts"].append({"method": method, "status": "deferred", "reason": reason})
            return False
        try:
            def fetch_and_assess():
                payload = fetch()
                return payload, assess(payload, source)
            payload, verdict = run_bounded(fetch_and_assess, min(remaining, attempt_seconds))
            documents[method] = payload
            if not payload.data.startswith(b"%PDF-"):
                (directory / (method + ".html.txt")).write_text(sanitized_html(payload.data))
            for link in alternative_links(payload, source, options["maxAlternatives"]):
                if link not in alternatives:
                    alternatives.append(link)
            entry = dict(verdict, method=method, url=redact_url(target), finalUrl=redact_url(payload.url), httpStatus=payload.status)
        except Exception as exc:
            entry = {"method": method, "url": redact_url(target), "status": "unavailable", "reason": redact_text(str(exc))[:500]}
        result["attempts"].append(entry)
        if entry["status"] in {"reachable-notices", "reachable-feed", "reachable-pdf"}:
            result.update(status=entry["status"], method=method)
            return True
        return False

    for index in range(options["directAttempts"]):
        if attempt(f"direct-{index + 1}", url, lambda: http_fetch(url, options["timeoutSeconds"])):
            return result
        last = result["attempts"][-1]
        # Don't retry a stable HTTP rejection/404 or a successful empty JS shell.
        if last.get("httpStatus") not in {None, 408, 429, 500, 502, 503, 504}:
            break
        if index + 1 < options["directAttempts"] and time.monotonic() < deadline:
            time.sleep(1)

    direct = next(iter(documents.values()), None)
    gone = direct is not None and direct.status in {404, 410}
    if options["browser"] and not gone:
        if attempt("browser", url, lambda: browser_fetch(url, options["browserTimeoutSeconds"], options["browserWaitMs"], directory)):
            return result

    if source.get("proxyFallback") and not gone:
        mirrors = list(monitor.SOURCE_MIRRORS)
        shift = rotation % len(mirrors) if mirrors else 0
        mirrors = mirrors[shift:] + mirrors[:shift]
        for index, template in enumerate(mirrors[:options["maxMirrors"]]):
            if attempt(f"mirror-{index + 1}", url, lambda template=template: mirror_payload(url, template, options["timeoutSeconds"])):
                return result

    result["alternativeLinks"] = [redact_url(link) for link in alternatives[:options["maxAlternatives"]]]
    for index, link in enumerate(alternatives[:options["maxAlternatives"]]):
        if attempt(f"alternative-{index + 1}", link, lambda link=link: http_fetch(link, options["timeoutSeconds"])):
            result["status"] = "alternative-found"
            result["reason"] = "Observed same-host official link works; registry unchanged pending review"
            return result
    statuses = [item["status"] for item in result["attempts"]]
    result["status"] = ("deferred" if "deferred" in statuses else "blocked" if "blocked" in statuses
                        else "reachable-no-notices" if "reachable-no-notices" in statuses else "unavailable")
    return result


def markdown_report(report: dict) -> str:
    lines = ["## Official-source access diagnostic", "",
             f"Checked at {report['checkedAt']} · runner: {report['runner']}",
             f"Progress: {len(report['sources'])}/{report.get('targetCount', len(report['sources']))} targets · "
             f"{'complete' if report.get('complete') else 'partial / still running or interrupted'}", ""]
    if not report.get("complete"):
        lines += [f"Partial run: {report.get('reason') or 'run budget exhausted'}. "
                  "Unfinished targets are `deferred`, not healthy; source order rotates on the next run.", ""]
    lines += ["Read-only: no alerts, source registries or publication fingerprints were changed.",
              "Candidate links/API observations are not verified vacancies. Mirrors may be stale.", "",
              "| Source | Outcome | Transport |", "| --- | --- | --- |"]
    for item in report["sources"]:
        sid = str(item["id"]).replace("|", "/").replace("\n", " ")
        lines.append(f"| `{sid}` | {item['status']} | {item.get('method', 'See artifact logs')} |")
    lines += ["", "Download the source-access artifact for sanitized HTML, browser screenshots,",
              "same-origin XHR/fetch metadata and per-attempt errors. No API headers, cookies or response bodies are saved.",
              "Private/local URLs, credentialed URLs, form submissions and CAPTCHA solving are prohibited.",
              "India egress requires a configured India-hosted self-hosted runner; location is not inferred from a label.", ""]
    return "\n".join(lines)


def run_checks(sources: list[dict], options: dict, output: Path, rotation: int = 0) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    budget_seconds = float(options.get("budgetSeconds", DEFAULT_BUDGET_SECONDS))
    grace_seconds = float(options.get("overrunGraceSeconds", DEFAULT_OVERRUN_GRACE_SECONDS))
    workers = max(1, int(options.get("workers", DEFAULT_WORKERS)))
    deadline = started + budget_seconds
    hard_deadline = deadline + grace_seconds
    report = {"checkedAt": datetime.now(timezone.utc).isoformat(),
              "runner": os.environ.get("RUNNER_ENVIRONMENT", "local"),
              "targetCount": len(sources),
              "budgetSeconds": budget_seconds,
              "overrunGraceSeconds": grace_seconds,
              "complete": False, "reason": "", "sources": []}
    sources = list(sources)
    if sources:
        shift = (rotation * workers) % len(sources)
        sources = sources[shift:] + sources[:shift]
    pending_sources = iter(sources)

    def save():
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        (output / "report.md").write_text(markdown_report(report))

    def deferred(source: dict, reason: str) -> dict:
        return {"id": source["id"], "url": redact_url(source["url"]),
                "kind": "discovery" if source.get("discovery") else "official",
                "status": "deferred", "attempts": [], "reason": reason}

    save()  # partial evidence survives a later timeout/cancellation
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="source-probe")
    running: dict = {}
    try:
        def submit():
            if time.monotonic() >= deadline:
                return
            source = next(pending_sources, None)
            if source is not None:
                running[pool.submit(probe, source, options, output, deadline, rotation)] = source

        for _ in range(workers):
            submit()
        while running:
            now = time.monotonic()
            if now >= hard_deadline:
                # Backstop: never hold the workflow step open until GitHub
                # cancels it (the 2026-10-20 failure). Publish what we have;
                # every unfinished target is deferred, and the next run resumes
                # at a rotated order.
                report["reason"] = "Hard run deadline reached before every source was probed"
                break
            done, _ = concurrent.futures.wait(running, timeout=max(0.02, min(1.0, hard_deadline - now)),
                                              return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                source = running.pop(future)
                try:
                    item = future.result()
                except Exception as exc:
                    item = {"id": source["id"], "status": "unavailable", "reason": redact_text(str(exc))[:500]}
                report["sources"].append(item)
                print(f"{source['id']}: {item['status']}", flush=True)
                save()
                submit()
    finally:
        # Never wait on an in-flight probe here: each attempt is already bounded
        # by attemptSeconds, and the report must say the pass was partial.
        pool.shutdown(wait=False, cancel_futures=True)
    for source in list(running.values()):
        report["sources"].append(deferred(source, "Run deadline reached while this source was being probed"))
    for source in pending_sources:
        report["sources"].append(deferred(source, "Run budget exhausted"))
    report["complete"] = not report["reason"]
    save()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache" / "source-access")
    parser.add_argument("--source-ids", default="", help="Optional comma-separated IDs; empty checks all registries")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    # Never let an invocation overwrite published content or Git internals.
    if output == ROOT or any(output == ROOT / name or ROOT / name in output.parents
                             for name in ("data", "assets", "share", ".git", "automation", "scripts", "tests")):
        parser.error("Output must be a separate diagnostic artifact directory")
    options = json.loads((ROOT / "automation/source-access.json").read_text())
    sources = load_sources()
    if args.source_ids:
        wanted = {value.strip() for value in args.source_ids.split(",") if value.strip()}
        sources = [s for s in sources if wanted.intersection(s["aliases"])]
        unknown = wanted - {alias for s in sources for alias in s["aliases"]}
        if unknown:
            parser.error("Unknown source IDs: " + ", ".join(sorted(unknown)))
    if not sources:
        parser.error("No sources selected")
    if args.no_browser:
        options["browser"] = False
    report = run_checks(sources, options, output, int(os.environ.get("GITHUB_RUN_NUMBER", "0")))
    unresolved = sum(item["status"] in {"blocked", "unavailable", "reachable-no-notices", "deferred"} for item in report["sources"])
    state = "complete" if report["complete"] else "partial (run deadline reached)"
    print(f"Read-only diagnostic {state}: {len(report['sources'])} sources, {unresolved} unresolved. Artifacts: {output}")
    # External failures belong in the report, not a fake all-clear or a failed publish.
    if unresolved and os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::{unresolved} sources remain unresolved; see source-access diagnostic artifact")
    if not report["complete"] and os.environ.get("GITHUB_ACTIONS"):
        # A partial report is evidence, not a workflow failure: finish the step
        # inside its timeout instead of being cancelled at the cap.
        print("::warning::Diagnostic stopped at its run budget; the report is partial "
              "and the next run continues with a rotated source order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
