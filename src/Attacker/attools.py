import subprocess

from langchain_core.tools import tool

from config import Target_url

# Only these sqlmap injection techniques may be requested by the agent.
# B=Boolean, E=Error, U=Union, S=Stacked, T=Time, Q=inline Query.
_ALLOWED_TECHNIQUES = set("BEUSTQ")


@tool
def sqlmap(
    level: int = 1,
    risk: int = 1,
    crawl: int = 0,
    forms: bool = False,
    technique: str | None = None,
    dbms: str | None = None,
    timeout: float = 30.0,
) -> str:
    """Scan the configured target for SQL injection with sqlmap.

    The target URL is fixed (config.Target_url) and cannot be chosen here, by
    design. You decide only HOW to scan. Recommended methodology: start at
    level=1, risk=1 with no crawl to confirm an injection fast; only escalate
    level/risk or enable crawl/forms if nothing is found; pass dbms once recon
    tells you the backend.

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

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        return "sqlmap is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        return "sqlmap scan timed out after 1800 seconds."

    # TODO: NEED TO GRAB CSV FILE CREATED BY SQLMAP AND FEED IT AS THE RESULT (?)
    return result.stdout or result.stderr
