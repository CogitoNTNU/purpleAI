"""Central configuration for PurpleAI.

Loads .env once, checks that every required value is present and
sensible, and extracts the scan host from the target URL. All other
modules read configuration through get_config(); environment variables
are never read anywhere else.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when the PurpleAI configuration is missing or malformed."""


@dataclass(frozen=True)
class Config:
    target_url: str
    target_host: str
    idun_base_url: str
    idun_api_key: str
    idun_model: str
    nmap_timeout: int


def _parse_target_host(target_url: str) -> str:
    """Extract the host from a target URL like http://192.168.50.10:8080.

    Nmap scans hosts, not URLs, so the URL must be a plain scheme://host
    (with optional port) and nothing else.
    """
    parsed = urlparse(target_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ConfigError(
            f"TARGET_URL '{target_url}' is malformed. "
            "Expected a URL like http://192.168.50.10:8080"
        )
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ConfigError(
            f"TARGET_URL '{target_url}' contains a path. "
            "Nmap scans a host, so the URL must be a plain host, e.g. http://192.168.50.10:8080"
        )
    if parsed.username or parsed.password:
        raise ConfigError(f"TARGET_URL '{target_url}' must not contain credentials.")
    return parsed.hostname


def load_config(env_file: str = ".env") -> Config:
    """Load .env and return a validated Config."""
    # load_dotenv() reads the file and sets its values as environment
    # variables. It only fills variables that are not already set, so a
    # value exported in the shell still wins over .env.
    load_dotenv(env_file)

    required = {}
    for name in ("TARGET_URL", "IDUN_BASE_URL", "IDUN_API_KEY", "IDUN_MODEL"):
        value = os.environ.get(name, "").strip()
        if not value:
            raise ConfigError(f"Missing '{name}' in .env. Copy .env.example to .env and fill it in.")
        required[name] = value

    if not required["IDUN_BASE_URL"].startswith(("http://", "https://")):
        raise ConfigError(
            f"IDUN_BASE_URL '{required['IDUN_BASE_URL']}' is malformed. "
            "Expected https://llm.hpc.ntnu.no/v1"
        )

    target_host = _parse_target_host(required["TARGET_URL"])

    return Config(
        target_url=required["TARGET_URL"],
        target_host=target_host,
        idun_base_url=required["IDUN_BASE_URL"].rstrip("/"),
        idun_api_key=required["IDUN_API_KEY"],
        idun_model=required["IDUN_MODEL"],
        nmap_timeout=120,
    )


_config: Config | None = None


def get_config() -> Config:
    """Return the Config, loading it from .env exactly once."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
