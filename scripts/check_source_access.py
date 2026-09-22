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
    entries += official + monitor.additional_link_sources()
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

    def attempt(method, target, fetch):
        if time.monotonic() >= deadline:
            result["attempts"].append({"method": method, "status": "deferred", "reason": "Run budget exhausted"})
            return False
        try:
            payload = fetch()
            verdict = assess(payload, source)
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
             f"{'complete' if report.get('complete') else 'partial / still running or interrupted'}", "",
             "Read-only: no alerts, source registries or publication fingerprints were changed.",
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
    deadline = time.monotonic() + options["budgetSeconds"]
    report = {"checkedAt": datetime.now(timezone.utc).isoformat(),
              "runner": os.environ.get("RUNNER_ENVIRONMENT", "local"),
              "targetCount": len(sources), "complete": False, "sources": []}
    sources = list(sources)
    if sources:
        shift = (rotation * options["workers"]) % len(sources)
        sources = sources[shift:] + sources[:shift]
    pending_sources = iter(sources)

    def save():
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        (output / "report.md").write_text(markdown_report(report))

    save()  # partial evidence survives a later timeout/cancellation
    with concurrent.futures.ThreadPoolExecutor(max_workers=options["workers"]) as pool:
        running = {}
        def submit():
            if time.monotonic() >= deadline:
                return
            source = next(pending_sources, None)
            if source is not None:
                running[pool.submit(probe, source, options, output, deadline, rotation)] = source
        for _ in range(options["workers"]):
            submit()
        while running:
            done, _ = concurrent.futures.wait(running, return_when=concurrent.futures.FIRST_COMPLETED)
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
    for source in pending_sources:
        report["sources"].append({"id": source["id"], "status": "deferred", "reason": "Run budget exhausted"})
    report["complete"] = True
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
    print(f"Read-only diagnostic complete: {len(report['sources'])} sources, {unresolved} unresolved. Artifacts: {output}")
    # External failures belong in the report, not a fake all-clear or a failed publish.
    if unresolved and os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::{unresolved} sources remain unresolved; see source-access diagnostic artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
