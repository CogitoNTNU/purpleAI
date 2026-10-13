import subprocess

from langchain_core.tools import tool

@tool
def sqlmap(url: str, depth: int, timeout: float = 30.0) -> str:
    """Map vulnerable SQL injection points in a web app via sqlmap.

    Args:
        url: target URL to scan
        depth: crawl depth (higher = crawls more pages, slower)
        timeout: per-request timeout in seconds (sqlmap --timeout)

    Returns:
        sqlmap's stdout as a string.
    """
    ##sqlmap --batch --crawl=3 --output-dir=<your_path> -u <testwebsite.com>
    cmd = [
        "sqlmap",
        "-u",
        url,
        f"--crawl={depth}",
        f"--timeout={int(timeout)}",
        "--forms",
        "--batch",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        return "sqlmap is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        return "sqlmap scan timed out after 1800 seconds."

    # TODO: NEED TO GRAB CSV FILE CREATED BY SQLMAP AND FEED IT AS THE RESULT (?)
    return result.stdout or result.stderr
