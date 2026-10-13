from __future__ import annotations

from conftest import AS_OTHER, PROJECT_CHAT, approved_meeting, processed_meeting

from app.services import teams


def _summary_body(client, mid):
    data = client.get(f"/api/meetings/{mid}/summary").json()
    s = data["summary"]
    edit = {
        "meeting_title": s["meeting_title"], "summary": s["summary"],
        "topics": [{"id": t["id"], "title": t["title"], "source": t["source"], "status": t["status"],
                    "resolution": t["resolution"], "evidence": [{"segment_id": e["segment_id"]} for e in t["evidence"]],
                    "verified": False} for t in s["topics"]],
        "decisions": [{"id": d["id"], "text": d["text"], "evidence": [{"segment_id": e["segment_id"]} for e in d["evidence"]]}
                      for d in s["decisions"]],
        "action_items": [{"id": a["id"], "task": a["task"], "owner": a["owner"], "due_date": a["due_date"],
                          "status": a["status"], "evidence": [{"segment_id": e["segment_id"]} for e in a["evidence"]]}
                         for a in s["action_items"]],
        "open_questions": [],
    }
    return data["report"]["version"], edit


def test_publish_requires_approval(client):
    m = processed_meeting(client)
    r = client.post(f"/api/meetings/{m['id']}/publish", json={"chat_id": PROJECT_CHAT, "confirm_recipients": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_approved"
    r = client.post(f"/api/meetings/{m['id']}/export")
    assert r.status_code == 409


def test_edit_and_approve_then_publish_once(client):
    m = processed_meeting(client)
    version, edit = _summary_body(client, m["id"])
    edit["action_items"].append({"task": "สรุปงบประมาณเพิ่มเติม", "owner": "คุณมาลี", "due_date": None,
                                 "status": "open", "evidence": [{"segment_id": 999}]})
    r = client.patch(f"/api/meetings/{m['id']}/summary", json={"version": version, "summary": edit})
    assert r.status_code == 200, r.text
    new_version = r.json()["report"]["version"]
    assert new_version == version + 1
    added = r.json()["summary"]["action_items"][-1]
    assert added["evidence"] == []  # fabricated segment id from the client is dropped

    # approving a stale version fails
    assert client.post(f"/api/meetings/{m['id']}/approve", json={"version": version}).status_code == 409
    assert client.post(f"/api/meetings/{m['id']}/approve", json={"version": new_version}).status_code == 200

    body = {"chat_id": PROJECT_CHAT, "confirm_recipients": True}
    r1 = client.post(f"/api/meetings/{m['id']}/publish", json=body)
    r2 = client.post(f"/api/meetings/{m['id']}/publish", json=body)  # double click
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert r1.json()["duplicate"] is False and r2.json()["duplicate"] is True
    assert r1.json()["publication"]["message_id"] == r2.json()["publication"]["message_id"]
    sent = teams.mock_sent_messages("mock-dev-user")
    assert len(sent) == 1
    assert "คุณสมชาย" in sent[0]["body"] and "SharePoint" in sent[0]["body"]

    detail = client.get(f"/api/meetings/{m['id']}").json()
    assert detail["status"] == "published"
    assert detail["report"]["exported_version"] == new_version  # auto-exported before publishing
    assert len(detail["publications"]) == 1


def test_editing_after_approval_requires_reapproval(client):
    m = approved_meeting(client)
    version, edit = _summary_body(client, m["id"])
    edit["summary"] = "แก้ไขบทสรุป"
    client.patch(f"/api/meetings/{m['id']}/summary", json={"version": version, "summary": edit})
    r = client.post(f"/api/meetings/{m['id']}/publish", json={"chat_id": PROJECT_CHAT, "confirm_recipients": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_approved"


def test_resolved_topic_requires_resolution_in_review(client):
    m = processed_meeting(client)
    version, edit = _summary_body(client, m["id"])
    edit["topics"][1]["status"] = "resolved"
    edit["topics"][1]["resolution"] = None
    r = client.patch(f"/api/meetings/{m['id']}/summary", json={"version": version, "summary": edit})
    assert r.status_code == 422


def test_foreign_chat_is_rejected(client):
    m = approved_meeting(client)
    for chat_id in ("19:mock-group-secret@thread.v2", "19:mock-oneonone@unq.gbl.spaces", "made-up"):
        r = client.post(f"/api/meetings/{m['id']}/publish", json={"chat_id": chat_id, "confirm_recipients": True})
        assert r.status_code == 403, chat_id
        assert r.json()["error"]["code"] == "chat_not_allowed"
    assert teams.mock_sent_messages("mock-dev-user") == []


def test_group_chat_list_only_group_chats(client):
    chats = client.get("/api/teams/group-chats").json()["chats"]
    ids = {c["id"] for c in chats}
    assert PROJECT_CHAT in ids
    assert "19:mock-oneonone@unq.gbl.spaces" not in ids
    assert "19:mock-group-secret@thread.v2" not in ids
    other = client.get("/api/teams/group-chats", headers=AS_OTHER).json()["chats"]
    assert {c["id"] for c in other} == {"19:mock-group-secret@thread.v2"}


def test_confirm_recipients_required(client):
    m = approved_meeting(client)
    r = client.post(f"/api/meetings/{m['id']}/publish", json={"chat_id": PROJECT_CHAT})
    assert r.status_code == 422


def test_timeout_after_send_is_not_duplicated_on_retry(client, monkeypatch):
    m = approved_meeting(client)
    body = {"chat_id": PROJECT_CHAT, "confirm_recipients": True}
    monkeypatch.setattr(teams, "MOCK_FAILURE", "timeout_after_send")
    r1 = client.post(f"/api/meetings/{m['id']}/publish", json=body)
    assert r1.status_code == 504 and r1.json()["error"]["code"] == "send_timeout"
    pubs = client.get(f"/api/meetings/{m['id']}/publications").json()["publications"]
    assert pubs[0]["status"] == "unknown"

    monkeypatch.setattr(teams, "MOCK_FAILURE", None)
    r2 = client.post(f"/api/meetings/{m['id']}/publish", json=body)
    assert r2.status_code == 200 and r2.json()["duplicate"] is True
    assert r2.json()["publication"]["status"] == "sent"
    assert len(teams.mock_sent_messages("mock-dev-user")) == 1


def test_timeout_before_send_retries_and_sends(client, monkeypatch):
    m = approved_meeting(client)
    body = {"chat_id": PROJECT_CHAT, "confirm_recipients": True}
    monkeypatch.setattr(teams, "MOCK_FAILURE", "timeout_before_send")
    assert client.post(f"/api/meetings/{m['id']}/publish", json=body).status_code == 504
    monkeypatch.setattr(teams, "MOCK_FAILURE", None)
    r = client.post(f"/api/meetings/{m['id']}/publish", json=body)
    assert r.status_code == 200 and r.json()["duplicate"] is False
    assert r.json()["publication"]["attempts"] == 2
    assert len(teams.mock_sent_messages("mock-dev-user")) == 1


def test_throttled_send_returns_retry_after(client, monkeypatch):
    m = approved_meeting(client)
    monkeypatch.setattr(teams, "MOCK_FAILURE", "throttle")
    r = client.post(f"/api/meetings/{m['id']}/publish", json={"chat_id": PROJECT_CHAT, "confirm_recipients": True})
    assert r.status_code == 429 and r.headers["Retry-After"] == "30"
    assert r.json()["error"]["code"] == "graph_throttled"


def test_export_docx_has_thai_complex_script_font(client):
    import io
    import zipfile

    m = approved_meeting(client)
    r = client.post(f"/api/meetings/{m['id']}/export")
    assert r.status_code == 200, r.text
    assert r.json()["sharepoint_web_url"].startswith("https://contoso.sharepoint.com/")
    docx = client.get(f"/api/meetings/{m['id']}/export/docx")
    assert docx.status_code == 200
    xml = zipfile.ZipFile(io.BytesIO(docx.content)).read("word/document.xml").decode("utf-8")
    assert 'w:cs="Tahoma"' in xml and "w:szCs" in xml
    assert "มติที่ประชุม" in xml and "PostgreSQL" in xml


def test_publish_preview(client):
    m = approved_meeting(client)
    r = client.get(f"/api/meetings/{m['id']}/publish/preview", params={"chat_id": PROJECT_CHAT})
    assert r.status_code == 200
    assert r.json()["members"] and "สรุปการประชุม" in r.json()["html"]


def test_chat_mapping_is_suggested_after_publish(client):
    m = approved_meeting(client)
    client.post(f"/api/meetings/{m['id']}/publish", json={"chat_id": PROJECT_CHAT, "confirm_recipients": True})
    r = client.get("/api/teams/group-chats", params={"meeting_id": m["id"]})
    assert r.json()["suggested_chat_id"] == PROJECT_CHAT


def test_long_thai_message_fits_graph_limit():
    from types import SimpleNamespace

    from app.services.teams import render_message

    summary = {
        "meeting_title": "ประชุมยาวมาก", "summary": "สรุป" * 3000,
        "decisions": [{"text": f"มติที่ {i} " + "รายละเอียดภาษาไทย" * 5} for i in range(200)],
        "action_items": [{"task": f"งานที่ {i} " + "ภาษาไทย" * 10, "owner": "คุณสมชาย", "due_date": "วันศุกร์นี้"}
                         for i in range(300)],
        "topics": [{"title": f"หัวข้อ {i}", "status": "mentioned"} for i in range(100)],
    }
    report = SimpleNamespace(summary_json=summary, version=3, sharepoint_web_url="https://x.sharepoint.com/r.docx")
    body = render_message(SimpleNamespace(title="t"), report, "MOM-ABC")
    assert len(body.encode("utf-8")) < 28_000
    assert body.endswith("</small></p>") and "MOM-ABC" in body and "ดูรายงานฉบับเต็ม" in body
    assert body.count("<ul>") == body.count("</ul>")
