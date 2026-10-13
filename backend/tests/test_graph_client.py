from __future__ import annotations

import httpx
import pytest

from app.errors import GraphError
from app.services.graph_client import GraphClient, GraphTimeout


def _client(handler) -> GraphClient:
    return GraphClient("t", transport=httpx.MockTransport(handler))


def test_pagination_follows_next_link():
    def handler(req: httpx.Request) -> httpx.Response:
        if "page2" in str(req.url):
            return httpx.Response(200, json={"value": [{"id": "c"}]})
        return httpx.Response(200, json={"value": [{"id": "a"}, {"id": "b"}],
                                         "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/chats?page2=1"})

    assert [x["id"] for x in _client(handler).get_paged("/me/chats")] == ["a", "b", "c"]


def test_get_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).get("/x") == {"ok": True} and calls["n"] == 3


@pytest.mark.parametrize("status,code", [(401, "graph_unauthorized"), (403, "graph_forbidden"),
                                         (404, "graph_not_found"), (500, "graph_unavailable")])
def test_errors_are_mapped(status, code, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(GraphError) as exc:
        _client(lambda req: httpx.Response(status, json={"error": {"code": "x"}})).get("/x")
    assert exc.value.code == code


def test_post_is_never_retried_and_timeout_is_flagged():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        raise httpx.ReadTimeout("slow")

    with pytest.raises(GraphTimeout):
        _client(handler).post_json("/chats/1/messages", {})
    assert calls["n"] == 1
