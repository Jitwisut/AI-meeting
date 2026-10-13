# API Contract

Base URL `http://localhost:8000`. Interactive docs: `/api/docs` (disabled when `ENVIRONMENT=production`).

Authentication: `Authorization: Bearer <token for api://<client-id>/access_as_user>`.
In mock mode, `X-Mock-User: dev-user | other-user` selects the test user.

Errors always look like:

```json
{ "error": { "code": "not_approved", "message": "ต้องอนุมัติรายงานฉบับล่าสุดก่อนส่งเข้า Teams", "detail": {} } }
```

`429` responses carry `Retry-After`. Graph errors map to `graph_unauthorized` (401), `graph_forbidden` (403),
`graph_not_found` (404), `graph_throttled` (429), `graph_unavailable` (5xx → 502).

## Endpoints from plan §7

| Method | Path | Body / query | Notes |
|---|---|---|---|
| GET | `/api/me` | – | user, roles, `can_approve`, Graph capability check, preferences, provider modes |
| GET | `/api/sharepoint/files` | `drive_id`, `item_id?`, `q?` | audio files + folders the user can access |
| POST | `/api/meetings` | `{drive_id, item_id, title?, language, agenda[], consent_ai_processing}` | 403 if the user cannot open the file |
| POST | `/api/meetings/upload` | multipart `file, title, language, agenda (JSON list), source=upload\|recording, consent_ai_processing, consent_recording` | real type sniffed with ffprobe; upload = MP3/WAV, recording = WebM/Ogg/MP4 |
| POST | `/api/meetings/{id}/process` | – | 202; downloads from SharePoint (delegated) then enqueues. Allowed from `pending`/`failed` |
| GET | `/api/meetings/{id}` | – | status, stage rows, report meta, publications |
| GET | `/api/meetings/{id}/transcript` | – | `{segments:[{id,start_ms,end_ms,text}]}` |
| GET | `/api/meetings/{id}/summary` | – | `{summary, report}` |
| PATCH | `/api/meetings/{id}/summary` | `{version, summary}` | optimistic concurrency (409 on stale version); evidence is given as `segment_id`s and rebuilt server-side; bumps version and clears approval |
| POST | `/api/meetings/{id}/approve` | `{version}` | must equal current version |
| GET | `/api/teams/group-chats` | `meeting_id?` | `chatType == group` only; `suggested_chat_id` from confirmed mapping |
| POST | `/api/meetings/{id}/publish` | `{chat_id, confirm_recipients: true}` | requires approval; validates chat membership; idempotent (`duplicate: true` on repeat); 504 `send_timeout` = outcome unknown, safe to retry |
| POST | `/api/meetings/{id}/export` | – | DOCX → SharePoint `MeetingReports/`; requires approval |

## Additional endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + provider modes |
| GET | `/api/dashboard` | counts per status + recent meetings |
| GET | `/api/meetings` | list (`status`, `q`, `limit`) |
| GET | `/api/meetings/{id}/audio` | normalised WAV for the player (410 after retention) |
| GET | `/api/meetings/{id}/export/docx` | download latest DOCX |
| GET | `/api/meetings/{id}/publish/preview` | `chat_id` → rendered Teams HTML + member list |
| GET | `/api/meetings/{id}/publications` | send history |
| GET | `/api/sharepoint/sites`, `/api/sharepoint/drives` | site/library pickers (allow-listed) |
| GET | `/api/settings`, PUT `/api/me/preferences` | policy view, per-user defaults |

## Summary JSON (stored in `meeting_reports.summary_json`)

```json
{
  "meeting_title": "ประชุมติดตามโครงการ",
  "summary": "...",
  "topics": [{"id": "a1", "title": "ออกแบบฐานข้อมูล", "source": "agenda", "status": "resolved",
              "resolution": "ใช้ PostgreSQL", "verified_by": null,
              "evidence": [{"segment_id": 3, "start_ms": 9000, "end_ms": 16000, "text": "..."}]}],
  "decisions": [{"id": "b1", "text": "...", "evidence": [...]}],
  "action_items": [{"id": "c1", "task": "...", "owner": null, "due_date": null, "status": "open", "evidence": [...]}],
  "open_questions": [{"id": "d1", "text": "...", "evidence": [...]}],
  "validation_warnings": ["..."],
  "generated_by": "azure_openai",
  "generated_at": "2026-10-14T02:00:00Z"
}
```

Topic status: `not_mentioned | mentioned | resolved | unclear`. `resolved` always has a non-empty `resolution`.
