"""Shared polite HTTP client: disk cache, per-host rate limit, retries, provenance log.

Usage:
    from chase.common.http import fetch, fetch_json, fetch_to_file
    r = fetch("https://example.org/x")        # r.content, r.text, r.status, r.retrieved_at, r.from_cache
    data = fetch_json("https://...")

Rules implemented here (CLAUDE.md section 3, rule 4):
- at least 1 second between requests per host (SEC hosts: 0.5 s, well under their 10 req/s cap)
- exponential backoff on 429/5xx and network errors
- descriptive User-Agent with contact email from .env (CONTACT_EMAIL)
- every network fetch is appended to data/manifests/http_log.jsonl (url, status, sha256, retrieved_at)
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

CACHE_DIR = ROOT / "data" / "cache" / "http"
LOG_PATH = ROOT / "data" / "manifests" / "http_log.jsonl"
CONTACT = os.environ.get("CONTACT_EMAIL") or "mo@example.com"
USER_AGENT = f"ChaseIndex research (contact: {CONTACT})"

# seconds between requests per host
DEFAULT_DELAY = 1.0
HOST_DELAY = {
    "data.sec.gov": 0.5,
    "www.sec.gov": 0.5,
    "query.wikidata.org": 2.0,
}

_lock = threading.Lock()
_host_locks: dict[str, threading.Lock] = {}
_last_hit: dict[str, float] = {}
_client: httpx.Client | None = None


@dataclass
class Response:
    url: str
    status: int
    content: bytes
    retrieved_at: str
    from_cache: bool
    sha256: str
    content_type: str = ""

    @property
    def text(self) -> str:
        for enc in ("utf-8", "latin-1"):
            try:
                return self.content.decode(enc)
            except UnicodeDecodeError:
                continue
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, connect=20.0),
        )
    return _client


def _key(url: str, params: dict | None) -> str:
    raw = url + ("?" + json.dumps(params, sort_keys=True) if params else "")
    return hashlib.sha256(raw.encode()).hexdigest()


def _throttle(host: str) -> None:
    with _lock:
        hl = _host_locks.setdefault(host, threading.Lock())
    with hl:
        delay = HOST_DELAY.get(host, DEFAULT_DELAY)
        wait = _last_hit.get(host, 0) + delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_hit[host] = time.monotonic()


def _log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")


def fetch(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    use_cache: bool = True,
    max_age_days: float | None = None,
    retries: int = 4,
    ok_statuses: tuple[int, ...] = (200,),
) -> Response:
    """GET with cache, rate limit and retries. Raises httpx.HTTPStatusError on final failure."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _key(url, params)
    body_p = CACHE_DIR / f"{key}.bin"
    meta_p = CACHE_DIR / f"{key}.json"
    if use_cache and body_p.exists() and meta_p.exists():
        meta = json.loads(meta_p.read_text())
        fresh = True
        if max_age_days is not None:
            age = time.time() - meta_p.stat().st_mtime
            fresh = age < max_age_days * 86400
        if fresh:
            return Response(url, meta["status"], body_p.read_bytes(), meta["retrieved_at"], True,
                            meta["sha256"], meta.get("content_type", ""))

    host = urlparse(url).netloc
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        _throttle(host)
        try:
            r = _get_client().get(url, params=params, headers=headers)
            if r.status_code in ok_statuses:
                content = r.content
                sha = hashlib.sha256(content).hexdigest()
                ts = now_iso()
                meta = {"url": url, "params": params, "status": r.status_code, "retrieved_at": ts,
                        "sha256": sha, "content_type": r.headers.get("content-type", ""),
                        "final_url": str(r.url), "bytes": len(content)}
                body_p.write_bytes(content)
                meta_p.write_text(json.dumps(meta))
                _log(meta)
                return Response(url, r.status_code, content, ts, False, sha, meta["content_type"])
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                ra = r.headers.get("retry-after")
                time.sleep(float(ra) if ra and ra.isdigit() else min(60, 2 ** (attempt + 1)))
                continue
            _log({"url": url, "params": params, "status": r.status_code, "retrieved_at": now_iso(), "error": True})
            r.raise_for_status()
            raise httpx.HTTPStatusError(f"unexpected status {r.status_code}", request=r.request, response=r)
        except (httpx.TransportError,) as e:  # network errors
            last_exc = e
            if attempt < retries:
                time.sleep(min(60, 2 ** (attempt + 1)))
                continue
            _log({"url": url, "params": params, "status": None, "retrieved_at": now_iso(), "error": str(e)})
            raise
    raise RuntimeError(f"fetch failed: {url}: {last_exc}")


def fetch_json(url: str, **kw):
    return fetch(url, **kw).json()


def fetch_to_file(url: str, dest: Path | str, **kw) -> dict:
    """Download to dest (under data/raw) and return a manifest entry."""
    r = fetch(url, **kw)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return {"source_url": url, "path": str(dest.relative_to(ROOT)) if dest.is_relative_to(ROOT) else str(dest),
            "sha256": r.sha256, "bytes": len(r.content), "retrieved_at": r.retrieved_at,
            "content_type": r.content_type}


def write_manifest(name: str, entries: list[dict] | dict) -> Path:
    p = ROOT / "data" / "manifests" / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
    return p
