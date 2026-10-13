from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import User


@dataclass
class CurrentUser:
    user: User
    access_token: str | None  # incoming API token, used only as the OBO assertion
    roles: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.user.id

    def graph_token(self, scope_setting: str) -> str | None:
        """Delegated Graph token for the given scope group (None in mock mode)."""
        s = get_settings()
        if s.graph_mode == "mock":
            return None
        if not self.access_token:
            raise AppError(401, "not_signed_in", "กรุณาเข้าสู่ระบบด้วยบัญชี Microsoft 365")
        from app.auth.entra import acquire_graph_token_obo

        return acquire_graph_token_obo(self.access_token, getattr(s, scope_setting).split())


def _upsert_user(db: Session, oid: str, name: str, email: str | None) -> User:
    user = db.scalar(select(User).where(User.entra_oid == oid))
    if user is None:
        user = User(entra_oid=oid, display_name=name, email=email, preferences={})
        db.add(user)
        db.commit()
    elif user.display_name != name or user.email != email:
        user.display_name, user.email = name, email
        db.commit()
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_mock_user: str | None = Header(default=None),
) -> CurrentUser:
    s = get_settings()
    if s.auth_mode == "mock":
        if s.environment == "production":
            raise AppError(500, "mock_auth_in_production", "ห้ามใช้ AUTH_MODE=mock ใน production")
        name = x_mock_user or "dev-user"
        if name not in s.dev_mock_users:
            raise AppError(401, "unknown_mock_user", "ไม่รู้จักผู้ใช้ทดสอบนี้")
        user = _upsert_user(db, f"mock-{name}", "ผู้ใช้ทดสอบ" if name == "dev-user" else name,
                            f"{name}@example.test")
        return CurrentUser(user=user, access_token=None, roles=["MoM.Approver"])

    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(401, "not_signed_in", "กรุณาเข้าสู่ระบบด้วยบัญชี Microsoft 365")
    token = authorization.split(" ", 1)[1].strip()
    from app.auth.entra import validate_access_token

    claims = validate_access_token(token)
    user = _upsert_user(db, claims["oid"], claims.get("name") or claims.get("preferred_username", ""),
                        claims.get("preferred_username"))
    request.state.user_id = user.id
    return CurrentUser(user=user, access_token=token, roles=list(claims.get("roles", [])))
