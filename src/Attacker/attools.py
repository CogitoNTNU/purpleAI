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

def nmap(url: str, timeout: float = 10.0) -> str:
    """Discover hosts, open ports, and running services on a target via nmap.

    Args:
        target: host, IP, or CIDR range to scan (e.g. "10.0.0.0/24")
        req_timeout: per-host timeout in seconds (nmap --host-timeout)

    Returns:
        nmap's stdout as a string.
    """
    cmd = [
        "nmap", 
        "-O",
        "-sV",
        "-Pn",
        "-v",
        "--host-timeout", f"{timeout}s",
        url
        #"-S", kan ha -S for spoofing, men reply vil bli sent til den falske IP-adressen, og vi vil ikke få info tilbake.
        ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout
    