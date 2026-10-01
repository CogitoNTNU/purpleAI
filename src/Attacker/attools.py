import subprocess

def sqlmap(url: str, depth:int, timeout: float = 10.0) -> str:
    """Map vulnerable SQL injection points in a web app via sqlmap.

    Args:
        url: target URL to scan
        depth: crawl depth (higher = crawls more pages, slower)
        req_timeout: per-request timeout in seconds (sqlmap --timeout)

    Returns:
        sqlmap's stdout as a string.
    """
    ##sqlmap --batch --crawl=3 --output-dir=<your_path> -u <testwebsite.com>
    cmd = [
        "sqlmap",
        "-u",
        url,
        f"--crawl={depth}",
        "--forms",
        "--batch"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # TODO: NEED TO GRAB CSV FILE CREATED BY SQLMAP AND FEED IT AS THE RESULT (?)
    return result.stdout

