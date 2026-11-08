#!/usr/bin/env python3
"""Dependency-free web recon crawler for the authorized target.

Run as a subprocess by the ``web_recon`` tool (see attools.py). It crawls the
fixed target, enumerates reachable endpoints, their query parameters and HTML
forms, and probes each GET parameter with a canary to see whether user input is
reflected in the response (the signal that distinguishes an XSS/SSTI lead from a
likely-SQLi numeric id). It prints a compact, human/LLM-readable map to stdout
so the Boss can hand each specialist a concrete endpoint + parameter.

It exploits nothing: it only reads pages and reflects a harmless canary. Uses
the standard library only, so it needs no install on the Kali host.

Usage: recon_crawl.py <base_url> [depth] [max_pages]
"""
from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from html.parser import HTMLParser

CANARY = "paiRX97qz"  # distinctive, unlikely to occur naturally in a response
UA = "PurpleAI-Recon/1.0 (authorized lab scan)"
REQ_TIMEOUT = 8.0          # per-request seconds
MAX_REFLECT_PROBES = 40    # cap canary requests so recon stays fast + quiet


class _Harvester(HTMLParser):
    """Pull links and forms (action/method + input names) out of one page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.forms: list[dict] = []
        self._form: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "form":
            self._form = {
                "action": a.get("action", ""),
                "method": (a.get("method") or "GET").upper(),
                "inputs": [],
            }
        elif tag in ("input", "select", "textarea") and self._form is not None:
            name = a.get("name")
            if name:
                self._form["inputs"].append(name)

    def handle_endtag(self, tag):
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None


def _fetch(url: str, data: bytes | None = None):
    """GET/POST a URL; return (status, body_text) or (None, '') on failure."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as r:
            body = r.read(500_000)  # cap body to keep memory bounded
            return r.status, body.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read(200_000).decode("utf-8", "replace")
        except Exception:
            return e.code, ""
    except Exception:
        return None, ""


def _same_origin(a: urllib.parse.ParseResult, b: urllib.parse.ParseResult) -> bool:
    return (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port)


def crawl(base: str, depth: int, max_pages: int):
    """BFS same-origin crawl. Returns (pages, endpoints, forms).

    endpoints maps path -> {param: set(sample values)}; forms is a list of
    {action, method, inputs} with absolute actions.
    """
    origin = urllib.parse.urlparse(base)
    seen: set[str] = set()
    endpoints: dict[str, dict[str, set]] = {}
    forms: list[dict] = []
    q: deque[tuple[str, int]] = deque([(base, 0)])
    pages = 0

    while q and pages < max_pages:
        url, d = q.popleft()
        norm = url.split("#", 1)[0]
        if norm in seen:
            continue
        seen.add(norm)
        status, body = _fetch(norm)
        if status is None:
            continue
        pages += 1

        # record any query parameters carried by this URL
        pu = urllib.parse.urlparse(norm)
        if pu.query:
            bucket = endpoints.setdefault(pu.path or "/", {})
            for k, vals in urllib.parse.parse_qs(pu.query).items():
                bucket.setdefault(k, set()).update(vals)

        h = _Harvester()
        try:
            h.feed(body)
        except Exception:
            pass

        for form in h.forms:
            action = urllib.parse.urljoin(norm, form["action"] or norm)
            au = urllib.parse.urlparse(action)
            if _same_origin(origin, au):
                forms.append({"action": action, "method": form["method"],
                              "inputs": form["inputs"]})

        if d >= depth:
            continue
        for href in h.links:
            nxt = urllib.parse.urljoin(norm, href)
            nu = urllib.parse.urlparse(nxt)
            if nu.scheme not in ("http", "https") or not _same_origin(origin, nu):
                continue
            if nu.query:  # remember param-bearing links even if we don't crawl deeper
                bucket = endpoints.setdefault(nu.path or "/", {})
                for k, vals in urllib.parse.parse_qs(nu.query).items():
                    bucket.setdefault(k, set()).update(vals)
            if nxt.split("#", 1)[0] not in seen:
                q.append((nxt, d + 1))

    return pages, endpoints, forms


def _reflects(path_qs: str, base: str) -> str:
    """Request path_qs (with one param set to the canary) and classify reflection."""
    url = urllib.parse.urljoin(base, path_qs)
    _status, body = _fetch(url)
    if not body:
        return "no-response"
    if CANARY in body:
        return "reflected-raw"       # unescaped -> strong XSS/SSTI candidate
    if urllib.parse.quote(CANARY) in body or CANARY.replace("", "") in body:
        return "reflected-encoded"
    return "not-reflected"


def _lead_hint(reflect: str, sample: str) -> str:
    numeric = sample.isdigit()
    if reflect == "reflected-raw":
        return "reflects input UNESCAPED -> prime XSS + SSTI lead"
    if reflect == "reflected-encoded":
        return "reflects input (escaped) -> possible XSS; worth SSTI probe"
    if numeric:
        return "numeric id, not reflected -> SQLi lead"
    return "not reflected -> try SQLi / other"


# Field/path name -> (vulnerability class, rank, reason). Lower rank = probe first.
def _classify_form(path: str, inputs: list[str], method: str, reflect: str) -> tuple[int, str]:
    names = " ".join(inputs).lower() + " " + path.lower()
    if reflect == "reflected-raw":
        return 0, "input reflected UNESCAPED -> prime XSS + SSTI lead"
    if any(w in names for w in ("upload", "file", "filename", "xml", "import", "doc")):
        return 1, "file/XML input -> XXE and file-upload lead (xxe_agent)"
    if any(w in names for w in ("download", "path", "read", "include")):
        return 1, "file path input -> path-traversal / LFI lead"
    if any(w in names for w in ("body", "content", "template", "message", "comment",
                                "bio", "description", "render")):
        return 2, "free-text field rendered back -> SSTI lead (ssti_agent)"
    if any(w in names for w in ("search", "query", "/q", " q", "keyword")):
        return 2, "search field -> XSS / SSTI lead (reflects results)"
    if any(w in names for w in ("login", "register", "user", "password", "email",
                                "auth", "signin")):
        return 3, "auth form -> SQL injection lead (sql_injection_agent)"
    if any(w in names for w in ("price", "product", "amount", "qty", "checkout")):
        return 3, "commerce field -> SQLi / business-logic lead"
    return 4, "untyped input -> try SQLi then XSS"


def main() -> int:
    if len(sys.argv) < 2:
        print("recon_crawl: missing base_url", file=sys.stderr)
        return 2
    base = sys.argv[1]
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    if not base.endswith("/") and "?" not in base:
        base += "/"

    pages, endpoints, forms = crawl(base, max(1, min(4, depth)), max(1, max_pages))

    out: list[str] = []
    out.append(f"=== RECON MAP for {base} ===")
    out.append(f"pages crawled: {pages}   endpoints w/ params: {len(endpoints)}   "
               f"forms: {len(forms)}")

    # Probe each discovered GET parameter for reflection (bounded).
    leads: list[tuple[str, str, str, str]] = []  # (path, param, reflect, hint)
    probes = 0
    out.append("\n-- endpoints & parameters --")
    if not endpoints:
        out.append("  (none found — target may be a single page or JS-driven)")
    for path in sorted(endpoints):
        params = endpoints[path]
        pretty = ", ".join(sorted(params))
        out.append(f"  [GET] {path}   params: {pretty}")
        for param in sorted(params):
            sample = next(iter(params[param]), "")
            reflect = "unprobed"
            if probes < MAX_REFLECT_PROBES:
                # keep sibling params at their samples, set this one to the canary
                qs = {k: (CANARY if k == param else next(iter(v), ""))
                      for k, v in params.items()}
                reflect = _reflects(path + "?" + urllib.parse.urlencode(qs), base)
                probes += 1
            hint = _lead_hint(reflect, sample)
            leads.append((path, param, reflect, hint))
            out.append(f"       - {param}={sample or '∅'}  [{reflect}]  {hint}")

    # Unified lead list the Boss can route from (query params + forms).
    all_leads: list[tuple[int, str, str]] = []  # (rank, target, hint)
    for path, param, reflect, hint in leads:
        r = {"reflected-raw": 0, "reflected-encoded": 1}.get(reflect, 2)
        all_leads.append((r, f"[GET] {path}?{param}=", hint))

    # Dedupe forms (the same form appears on every page that renders it).
    out.append("\n-- forms --")
    seen_forms: set = set()
    uniq_forms = []
    for f in forms:
        pu = urllib.parse.urlparse(f["action"])
        key = (f["method"], pu.path, tuple(f["inputs"]))
        if key in seen_forms:
            continue
        seen_forms.add(key)
        uniq_forms.append((pu.path, f))
    if not uniq_forms:
        out.append("  (none found)")
    for pth, f in sorted(uniq_forms):
        # Reflection-probe GET forms by submitting the canary in each input.
        reflect = "n/a (POST)"
        if f["method"] == "GET" and f["inputs"] and probes < MAX_REFLECT_PROBES:
            qs = {inp: CANARY for inp in f["inputs"]}
            reflect = _reflects(pth + "?" + urllib.parse.urlencode(qs), base)
            probes += 1
        rnk, hint = _classify_form(pth, f["inputs"], f["method"], reflect)
        out.append(f"  [{f['method']}] {pth}   inputs: "
                   f"{', '.join(f['inputs']) or '(none named)'}   [{reflect}]")
        tgt = f"[{f['method']}] {pth} ({', '.join(f['inputs']) or 'body'})"
        all_leads.append((rnk, tgt, hint))

    out.append("\n-- ranked leads (hand these to the specialists) --")
    ranked = sorted(all_leads, key=lambda t: (t[0], t[1]))
    if not ranked:
        out.append("  (no leads found; try a deeper crawl)")
    for _rnk, tgt, hint in ranked[:10]:
        out.append(f"  {tgt}  ->  {hint}")

    # Tech fingerprint is added by the web_recon tool (whatweb), not here.
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
