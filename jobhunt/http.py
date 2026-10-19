from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 rtl-jobhunt/1.0"
)
TIMEOUT = 25


class SourceError(Exception):
    """A source could not be fetched or parsed. The run continues without it."""


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def get_json(session, url: str, **kw):
    try:
        r = session.get(url, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise SourceError(f"request failed: {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise SourceError(f"HTTP {r.status_code} from {url}")
    try:
        return r.json()
    except ValueError as e:
        raise SourceError(f"non-JSON response from {url}") from e


def post_json(session, url: str, payload: dict, **kw):
    try:
        r = session.post(url, json=payload, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise SourceError(f"request failed: {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise SourceError(f"HTTP {r.status_code} from {url}")
    try:
        return r.json()
    except ValueError as e:
        raise SourceError(f"non-JSON response from {url}") from e
