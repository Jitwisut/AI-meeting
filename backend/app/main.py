"""FastAPI entry point for the AI Meeting Minutes backend."""
from __future__ import annotations

import logging
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import me, meetings, sharepoint, teams
from app.config import get_settings
from app.db import init_db
from app.errors import AppError, app_error_handler


class RedactSecrets(logging.Filter):
    """Keep bearer tokens and API keys out of logs (plan §9)."""

    _pattern = re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.]+|((?:api-key|key|secret)=)[^&\s]+", re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._pattern.sub(lambda m: (m.group(1) or m.group(2)) + "***", record.msg)
        return True


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactSecrets())
    if s.environment == "production" and "mock" in (s.auth_mode, s.graph_mode):
        raise RuntimeError("Mock auth/graph must not be used in production")

    app = FastAPI(title="AI Meeting Minutes API", version="0.1.0",
                  docs_url="/api/docs" if s.environment != "production" else None,
                  openapi_url="/api/openapi.json" if s.environment != "production" else None)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "PUT"],
                       allow_headers=["Authorization", "Content-Type", "X-Mock-User"],
                       expose_headers=["Retry-After", "Content-Disposition"])
    app.add_exception_handler(AppError, app_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        msgs = [str(e.get("msg", "")).removeprefix("Value error, ") for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {
            "code": "validation_error", "message": "ข้อมูลไม่ถูกต้อง: " + "; ".join(msgs[:3]),
            "detail": {"fields": [".".join(str(p) for p in e.get("loc", [])) for e in exc.errors()][:10]}}})

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("api").exception("unhandled error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": {
            "code": "internal_error", "message": "เกิดข้อผิดพลาดภายในระบบ กรุณาลองใหม่อีกครั้ง"}})

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # noqa: ANN001, ANN202
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "modes": {"auth": s.auth_mode, "graph": s.graph_mode,
                                          "stt": s.stt_provider, "summarizer": s.summarizer}}

    for r in (me.router, sharepoint.router, teams.router, meetings.router):
        app.include_router(r)

    init_db()
    return app


app = create_app()
