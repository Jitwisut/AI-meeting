# Security, Privacy & Compliance Checklist (plan §9)

Legend: ✅ implemented · 🟡 partial / needs org decision · ⬜ organisational task

| # | Requirement | Status | Where / note |
|---|---|---|---|
| 1 | Consent before recording / AI processing | ✅ | Consent checkbox required by API (`consent_required`); extra recording consent for browser recording; timestamp stored |
| 2 | Data classification & DPA before sending audio to Azure AI | ⬜ | IT/legal; Gemini free tier restricted to synthetic data |
| 3 | Least privilege (SharePoint sites, Teams chats) | ✅/🟡 | Delegated OBO tokens; site allow-list; only own group chats; `Sites.Selected` option documented |
| 4 | No keys/tokens/transcripts in browser logs | ✅ | Graph & AI keys server-side only; MSAL cache in sessionStorage; log filter redacts bearer/api keys; audit log stores ids only |
| 5 | HTTPS | 🟡 | Terminate TLS at App Service / Container Apps ingress |
| 6 | Secret manager (Key Vault) | 🟡 | `.env` for dev; map env vars to Key Vault references in deployment |
| 7 | Encryption at rest | 🟡 | Azure Database for PostgreSQL / storage encryption by default — confirm with IT |
| 8 | Audit trail | ✅ | `audit_logs`: create, process, edit, approve, export, publish |
| 9 | File type / size limits | ✅ | ffprobe content sniffing, MP3/WAV for upload, size & duration limits |
| 10 | Malware scanning | 🟡 | Hook `audio.scan_for_malware()` — plug in org scanner |
| 11 | Rate limit & timeouts | ✅/🟡 | Per-user in-process limiter; HTTP timeouts on Graph/STT/LLM. Use gateway/Redis limiter for multi-replica |
| 12 | Delete temporary audio | ✅ | `TEMP_AUDIO_RETENTION_HOURS`; cleanup on every job and `python -m app.workers.pipeline` |
| 13 | Retry Teams without duplicates | ✅ | Unique idempotency key, `unknown` state, reference-code lookup before retry; tests cover timeout-after-send |
| 14 | 401/403/404/429/5xx handling | ✅ | `GraphError` mapping with Thai messages; `Retry-After` honoured (GET auto-retry, POST never auto-retried) |
| 15 | Authorization on every endpoint | ✅ | Owner check (404 for others), approver role option, chat membership re-validated server-side |
| 16 | Input validation | ✅ | Pydantic models with length limits; client evidence rebuilt from stored transcript |
| 17 | Human review before publish | ✅ | Approval bound to report version; edits invalidate approval |
| 18 | Mock auth disabled in production | ✅ | Startup fails if `ENVIRONMENT=production` with mock auth/graph |
| 19 | Security headers | ✅ | nosniff, no-referrer, frame deny, microphone limited to self |
| 20 | Transcript/report retention policy | ⬜ | Decide durations (plan §14 Q7) then add scheduled purge |
| 21 | SharePoint link access for chat members | 🟡 | Preview lists recipients; user must confirm access. Automated permission comparison needs group expansion — future work |
