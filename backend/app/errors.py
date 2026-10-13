"""Application errors with Thai, user-facing messages (plan §9)."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, *, retry_after: int | None = None,
                 detail: dict | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after
        self.detail = detail or {}


GRAPH_STATUS_MESSAGES = {
    401: ("graph_unauthorized", "เซสชัน Microsoft 365 หมดอายุ กรุณาเข้าสู่ระบบใหม่"),
    403: ("graph_forbidden", "คุณไม่มีสิทธิ์เข้าถึงรายการนี้ใน Microsoft 365 กรุณาติดต่อเจ้าของไฟล์หรือทีม IT"),
    404: ("graph_not_found", "ไม่พบไฟล์หรือแชทที่เลือก อาจถูกลบหรือย้ายไปแล้ว"),
    429: ("graph_throttled", "Microsoft 365 จำกัดจำนวนคำขอชั่วคราว กรุณาลองใหม่ภายหลัง"),
}


class GraphError(AppError):
    """Error returned by Microsoft Graph, mapped to a friendly message."""

    def __init__(self, status: int, graph_code: str = "", graph_message: str = "",
                 retry_after: int | None = None) -> None:
        if status in GRAPH_STATUS_MESSAGES:
            code, message = GRAPH_STATUS_MESSAGES[status]
        elif status >= 500:
            code, message = "graph_unavailable", "บริการ Microsoft 365 ขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้ง"
        else:
            code, message = "graph_error", "เกิดข้อผิดพลาดในการเชื่อมต่อ Microsoft 365"
        api_status = status if status in (401, 403, 404, 429) else 502
        super().__init__(api_status, code, message, retry_after=retry_after,
                         detail={"graph_status": status, "graph_code": graph_code})
        self.graph_status = status
        self.graph_message = graph_message


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message, **({"detail": exc.detail} if exc.detail else {})}},
        headers=headers,
    )
