import os
import re
from pathlib import Path

from config import Target_url
from event_logging import run_logged_tool
from langchain_core.tools import tool

# Absolute path to the stdlib recon crawler shipped next to this module, so the
# web_recon tool resolves it regardless of the server's working directory.
_RECON_CRAWLER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recon_crawl.py")

# Only these sqlmap injection techniques may be requested by the agent.
# B=Boolean, E=Error, U=Union, S=Stacked, T=Time, Q=inline Query.
_ALLOWED_TECHNIQUES = set("BEUSTQ")

# Database/table/column identifiers the agent may name for extraction. Kept to a
# conservative charset so these values stay plain identifiers and can never be
# anything but a single argv token (they are passed via create_subprocess_exec,
# so there is no shell, but this still rejects obviously malformed input).
_IDENT_RE = re.compile(r"^[A-Za-z0-9_,. ]+$")

# A custom extraction query must be a single, read-only SELECT: it must start
# with SELECT and contain no ';' (which would allow stacked/destructive queries).
_READONLY_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


@tool
async def sqlmap(
    level: int = 1,
    risk: int = 1,
    crawl: int = 0,
    forms: bool = False,
    technique: str | None = None,
    dbms: str | None = None,
    timeout: float = 30.0,
    dump: bool = False,
    db: str | None = None,
    table: str | None = None,
    columns: str | None = None,
    sql_query: str | None = None,
) -> str:
    """Scan the configured target for SQL injection with sqlmap, and optionally
    extract data once an injection is confirmed.

    The target URL is fixed (config.Target_url) and cannot be chosen here, by
    design. You decide only HOW to scan and WHAT to read. Recommended
    methodology: start at level=1, risk=1 with no crawl to confirm an injection
    fast; only escalate level/risk or enable crawl/forms if nothing is found;
    pass dbms once recon tells you the backend. Once an injection is CONFIRMED,
    extract the data that proves it and reveals planted flags: prefer a targeted
    read (e.g. sql_query="SELECT flag_name, flag_value FROM flags", or
    table="flags" with dump=True) over dumping the whole database.

    Args:
        level: how many places to test (1-5): higher also tests cookies/headers.
        risk: payload aggressiveness (1-3): higher is heavier and noisier.
        crawl: crawl depth (0 = don't crawl, just test the target URL).
        forms: also parse and test HTML forms on the page.
        technique: subset of "BEUSTQ" to restrict injection techniques
            (B=Boolean, E=Error, U=Union, S=Stacked, T=Time, Q=inline Query);
            None lets sqlmap try all.
        dbms: backend hint, e.g. "mysql" / "postgresql", to skip guessing;
            None lets sqlmap detect it.
        timeout: per-request timeout in seconds (sqlmap --timeout).
        dump: dump the selected data (sqlmap --dump). Scope it with db/table/
            columns; with none set it dumps everything found, which is slow.
        db: restrict extraction to this database/schema (sqlmap -D).
        table: restrict extraction to this table, e.g. "flags" (sqlmap -T).
        columns: restrict extraction to these columns, comma-separated (-C).
        sql_query: run one read-only SELECT via the injection and return its
            result (sqlmap --sql-query). Must start with SELECT and contain no
            ';'. The most surgical way to read a specific value such as a flag.

    Returns:
        sqlmap's stdout (or stderr if stdout is empty).
    """
    # Clamp the numeric knobs to sqlmap's valid ranges so a bad plan can't
    # produce an invalid command.
    level = max(1, min(5, int(level)))
    risk = max(1, min(3, int(risk)))
    crawl = max(0, int(crawl))

    ##sqlmap --batch --crawl=3 --output-dir=<your_path> -u <testwebsite.com>
    cmd = [
        "sqlmap",
        "--output-dir=" + str(Path(__file__).resolve().parents[2] / "startup/tool-state/sqlmap"),
        "-u",
        Target_url,  # target is fixed, never agent-supplied
        f"--level={level}",
        f"--risk={risk}",
        f"--timeout={int(timeout)}",
        "--batch",
    ]
    if crawl > 0:
        cmd.append(f"--crawl={crawl}")
    if forms:
        cmd.append("--forms")
    if technique:
        chosen = "".join(c for c in technique.upper() if c in _ALLOWED_TECHNIQUES)
        if chosen:
            cmd.append(f"--technique={chosen}")
    if dbms:
        # Pass as one argument; sqlmap validates the value itself.
        cmd.append(f"--dbms={dbms}")

    # --- Data extraction (only after an injection is confirmed) ---------------
    # A custom read-only SELECT is the most targeted extraction; it takes
    # precedence over a table dump when both are given.
    if sql_query and _READONLY_SELECT_RE.match(sql_query) and ";" not in sql_query:
        cmd.append(f"--sql-query={sql_query.strip()}")
    else:
        # Scope a dump with any valid identifiers the agent named.
        if db and _IDENT_RE.match(db):
            cmd += ["-D", db.strip()]
        if table and _IDENT_RE.match(table):
            cmd += ["-T", table.strip()]
        if columns and _IDENT_RE.match(columns):
            cmd += ["-C", columns.strip()]
        if dump or db or table or columns:
            cmd.append("--dump")

    return await run_logged_tool(cmd, target=Target_url)

@tool
async def xsser(payload: str, timeout: float = 1800.0) -> str:
    """Test the configured VulnShop search endpoint for reflected XSS.

    The target URL is fixed (config.Target_url) and cannot be chosen here, by
    design. You decide only which payload (script) to inject.

    Args:
        payload: the XSS script/payload to test (passed to xsser --Fp).
        timeout: per-request timeout in seconds (xsser --timeout).

    Returns:
        xsser's stdout (or stderr if stdout is empty).
    """
    base_url = Target_url.rstrip("/")
    injection_point = "/search?q=XSS"
    cmd = [
        "xsser",
        "-u",
        base_url,
        "-g",
        injection_point,
        f"--timeout={int(timeout)}",
        "--Fp",
        str(payload),  # one argv token (no shell), so payload is never parsed as flags
    ]
    return await run_logged_tool(cmd, target=f"{base_url}{injection_point}")


@tool
async def ssti_scanner(
    payload: str,
    endpoint: str = "/greet",
    parameter: str = "name",
    timeout: float = 30.0,
) -> str:
    """Test the configured target for Server-Side Template Injection using curl.

    The target URL is fixed (config.Target_url) and cannot be chosen here, by
    design. You decide which payload to inject and where to inject it.

    Args:
        payload: the SSTI payload to test.
        endpoint: the endpoint to test (default: "/greet").
        parameter: which parameter to inject the payload into.
        timeout: request timeout in seconds.

    Returns:
        The HTTP response showing whether the template was evaluated.
    """
    base_url = Target_url.rstrip("/")
    full_url = f"{base_url}{endpoint}"

    cmd = [
        "curl",
        "-X", "POST",
        "-d", f"{parameter}={payload}",
        "--max-time", str(int(timeout)),
        "-i",  # include HTTP headers in output
        full_url,
    ]

    return await run_logged_tool(cmd, target=full_url)

@tool
async def xxe_scanner(
    payload: str,
    endpoint: str = "/upload",
    parameter: str = "file",
    timeout: float = 30.0,
) -> str:
    """Test the configured target for XML External Entity (XXE) injection using curl.

    The target URL is fixed (config.Target_url) and cannot be chosen here, by
    design. You decide which payload to inject and where to inject it.

    Args:
        payload: the XXE payload to test.
        endpoint: the endpoint to test (default: "/upload").
        parameter: which parameter to inject the payload into.
        timeout: request timeout in seconds.

    Returns:
        The HTTP response showing whether the XML was processed.
    """
    base_url = Target_url.rstrip("/")
    full_url = f"{base_url}{endpoint}"

    cmd = [
        "curl",
        "-X", "POST",
        "-d", f"{parameter}={payload}",
        "--max-time", str(int(timeout)),
        "-i",  # include HTTP headers in output
        full_url,
    ]

    return await run_logged_tool(cmd, target=full_url)

@tool
async def ssrf_scanner(
    payload: str,
    endpoint: str = "/fetch",
    parameter: str = "url",
    method: str = "GET",
    timeout: float = 30.0,
) -> str:
    """Test the configured target for Server-Side Request Forgery (SSRF) using curl.

    The target URL is fixed (config.Target_url) and cannot be chosen here, by
    design. You decide the SSRF payload (the URL you want the server to be
    tricked into fetching -- e.g. an internal service or a cloud metadata
    endpoint), which endpoint accepts a user-supplied URL, and which parameter
    carries it.

    Args:
        payload: the URL the server should be made to fetch, e.g.
            "http://169.254.169.254/latest/meta-data/" or "http://localhost/admin".
        endpoint: the endpoint that fetches a user-supplied URL (default: "/fetch").
        parameter: which parameter carries the URL (default: "url").
        method: "GET" to send the URL in the query string, or "POST" for a form body.
        timeout: request timeout in seconds.

    Returns:
        The HTTP response showing whether the server fetched the internal
        resource (look for metadata, internal pages, or FLAG{...} in the body).
    """
    base_url = Target_url.rstrip("/")
    full_url = f"{base_url}{endpoint}"

    if method.upper() == "POST":
        cmd = [
            "curl",
            "-X", "POST",
            "-d", f"{parameter}={payload}",
            "--max-time", str(int(timeout)),
            "-i",
            full_url,
        ]
    else:
        # -G + --data-urlencode appends the URL-encoded payload as the query
        # string, so an SSRF URL (with its own :// and ?params) stays intact.
        cmd = [
            "curl",
            "-G",
            "--data-urlencode", f"{parameter}={payload}",
            "--max-time", str(int(timeout)),
            "-i",
            full_url,
        ]

    return await run_logged_tool(cmd, target=full_url)

@tool
async def web_recon(depth: int = 2, max_pages: int = 20, fingerprint: bool = True) -> str:
    """Map the authorized target's attack surface for the other specialists.

    Crawls the fixed target (config.Target_url) to enumerate reachable
    endpoints, their query parameters, and HTML forms, and probes each GET
    parameter with a harmless canary to see whether input is reflected
    unescaped. Reflected-raw params are prime XSS/SSTI leads; numeric,
    non-reflected ids are SQLi leads. Optionally fingerprints the backend
    stack with whatweb. The target is fixed by design — you choose only HOW
    far to crawl. This tool exploits NOTHING; hand its map to the Boss so each
    specialist gets a concrete endpoint + parameter instead of guessing.

    Args:
        depth: crawl depth (1-4). Start at 2; go deeper only if the map is thin.
        max_pages: safety cap on pages fetched (default 40).
        fingerprint: also run whatweb to identify the server/framework/engine.

    Returns:
        A readable recon map: endpoints, parameters (with reflection verdict),
        forms, ranked leads, and (optionally) the tech fingerprint.
    """
    depth = max(1, min(4, int(depth)))
    max_pages = max(1, min(200, int(max_pages)))
    cmd = ["python3", _RECON_CRAWLER, Target_url, str(depth), str(max_pages)]
    # Log under "recon" rather than the bare "python3" interpreter name.
    report = await run_logged_tool(cmd, target=Target_url, timeout=300, tool_name="recon")

    if fingerprint:
        fp = await run_logged_tool(
            ["whatweb", "-a", "1", "--color=never", Target_url],
            target=Target_url, timeout=120, tool_name="whatweb",
        )
        report += "\n\n=== tech fingerprint (whatweb) ===\n" + fp
    return report
