"""Polite HTTP: one request per second, real User-Agent, disk cache, retry with backoff.

Every network read in the project goes through `get()`. It never raises: on failure it
logs and returns None so the caller can skip that one item (fail soft).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("radar.net")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "substack-radar/1.1 (personal reading digest; read-only)"
)
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
MIN_INTERVAL = 1.0      # seconds between requests (~1 req/sec)
RETRIES = 3             # attempts after the first one
TIMEOUT = 20

_last_request = 0.0


def _throttle() -> None:
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _cache_path(url: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".bin")


def get(url: str, ttl: int = 3600) -> bytes | None:
    """GET url, serving from cache if younger than ttl seconds. None on failure."""
    path = _cache_path(url)
    if ttl > 0 and path.exists() and time.time() - path.stat().st_mtime < ttl:
        return path.read_bytes()

    for attempt in range(RETRIES + 1):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read()
            if ttl > 0:
                CACHE_DIR.mkdir(exist_ok=True)
                path.write_bytes(body)
            return body
        except urllib.error.HTTPError as e:
            if e.code not in (408, 429) and e.code < 500:
                log.warning("GET %s -> HTTP %s (not retrying)", url, e.code)
                return None
            retry_after = e.headers.get("Retry-After", "")
            delay = float(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1)
            log.warning("GET %s -> HTTP %s, retry in %.0fs", url, e.code, delay)
        except Exception as e:  # timeouts, DNS, connection resets
            delay = 2 ** (attempt + 1)
            log.warning("GET %s failed (%s), retry in %.0fs", url, e, delay)
        if attempt < RETRIES:
            time.sleep(delay)
    log.error("GET %s gave up after %d attempts", url, RETRIES + 1)
    return None


def get_json(url: str, ttl: int = 3600) -> Any:
    body = get(url, ttl)
    if body is None:
        return None
    try:
        return json.loads(body)
    except ValueError:
        log.warning("GET %s returned non-JSON", url)
        return None
