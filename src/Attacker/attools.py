def sqlmap(url: str, timeout: float = 10.0) -> str:
    """Map all the vulnerable injection possibilities in a webpage. Higher level(1-5) means more capability.
    
    Args:
        url: URL to attack
        timeout: request timout in seconds

    Returns:
        markdown file i think.
    """
    sqlmap --batch --crawl=3 --output-dir=<your_path> -u <testwebsite.com>
