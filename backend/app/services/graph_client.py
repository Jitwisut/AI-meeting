"""Thin Microsoft Graph HTTP client with pagination and safe retries.

Only idempotent requests (GET) are retried automatically on 429/5xx.
POST of chat messages is never retried here: duplicate prevention is handled
by the publication history in services/teams.py (plan §9).
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import httpx

from app.errors import AppError, GraphError

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_GET_RETRIES = 3
MAX_RETRY_WAIT_SECONDS = 10


class GraphTimeout(Exception):
    """The request may or may not have reached Graph."""


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    code, message = "", ""
    try:
        err = resp.json().get("error", {})
        code, message = err.get("code", ""), err.get("message", "")
    except ValueError:
        pass
    retry_after = None
    if "Retry-After" in resp.headers:
        try:
            retry_after = int(resp.headers["Retry-After"])
        except ValueError:
            retry_after = 30
    raise GraphError(resp.status_code, code, message, retry_after)


class GraphClient:
    def __init__(self, token: str, *, timeout: float = 30.0, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url=GRAPH_BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GraphClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(self, path: str, params: dict | None = None) -> dict:
        for attempt in range(MAX_GET_RETRIES + 1):
            resp = self._client.get(path, params=params)
            if resp.status_code in (429, 502, 503, 504) and attempt < MAX_GET_RETRIES:
                wait = min(int(resp.headers.get("Retry-After", 2 ** attempt)), MAX_RETRY_WAIT_SECONDS)
                time.sleep(wait)
                continue
            _raise_for(resp)
            return resp.json()
        raise AssertionError("unreachable")

    def get_paged(self, path: str, params: dict | None = None, max_pages: int = 20) -> Iterator[dict]:
        page = self.get(path, params)
        for _ in range(max_pages):
            yield from page.get("value", [])
            next_link = page.get("@odata.nextLink")
            if not next_link:
                return
            page = self.get(next_link)

    def download(self, path: str, dest: Path, max_bytes: int) -> int:
        written = 0
        with self._client.stream("GET", path) as resp:
            if resp.status_code >= 400:
                resp.read()
                _raise_for(resp)
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes(1024 * 256):
                    written += len(chunk)
                    if written > max_bytes:
                        raise AppError(413, "file_too_large", "ไฟล์เสียงมีขนาดเกินกำหนด")
                    fh.write(chunk)
        return written

    def put_content(self, path: str, data: bytes, content_type: str) -> dict:
        resp = self._client.put(path, content=data, headers={"Content-Type": content_type})
        _raise_for(resp)
        return resp.json()

    def post_json(self, path: str, body: dict) -> dict:
        try:
            resp = self._client.post(path, json=body)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GraphTimeout(str(exc)) from exc
        _raise_for(resp)
        return resp.json()
