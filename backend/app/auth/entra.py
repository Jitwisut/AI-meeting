"""Microsoft Entra ID token validation and On-Behalf-Of (OBO) exchange.

Flow (plan §3/§4.3):
  Browser (MSAL, Auth Code + PKCE) -> access token for *this API*
  Backend validates the token, then exchanges it via OBO for a delegated
  Microsoft Graph token with only the scopes a given call needs.
Tokens are never persisted (plan §6); MSAL keeps a short-lived in-memory cache.
"""
from __future__ import annotations

import threading
from functools import lru_cache

import jwt
import msal

from app.config import get_settings
from app.errors import AppError


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    tenant = get_settings().entra_tenant_id
    return jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
                           cache_keys=True, lifespan=3600)


def validate_access_token(token: str) -> dict:
    s = get_settings()
    if not s.entra_tenant_id or not s.entra_api_client_id:
        raise AppError(500, "auth_not_configured", "ระบบยังไม่ได้ตั้งค่า Microsoft Entra ID")
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=[s.api_audience, s.entra_api_client_id],
            issuer=f"https://login.microsoftonline.com/{s.entra_tenant_id}/v2.0",
            options={"require": ["exp", "iat", "aud", "iss", "oid"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "token_expired", "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่") from exc
    except jwt.PyJWTError as exc:
        raise AppError(401, "invalid_token", "ไม่สามารถยืนยันตัวตนได้ กรุณาเข้าสู่ระบบใหม่") from exc
    if claims.get("tid") != s.entra_tenant_id:
        raise AppError(401, "wrong_tenant", "บัญชีนี้ไม่ได้อยู่ในองค์กรที่ได้รับอนุญาต")
    if "access_as_user" not in str(claims.get("scp", "")).split():
        raise AppError(403, "missing_scope", "Token ไม่มีสิทธิ์ access_as_user สำหรับระบบนี้")
    return claims


_msal_lock = threading.Lock()
_msal_app: msal.ConfidentialClientApplication | None = None


def _confidential_app() -> msal.ConfidentialClientApplication:
    global _msal_app
    with _msal_lock:
        if _msal_app is None:
            s = get_settings()
            if not s.entra_api_client_secret:
                raise AppError(500, "obo_not_configured", "ระบบยังไม่ได้ตั้งค่า client secret สำหรับ On-Behalf-Of")
            _msal_app = msal.ConfidentialClientApplication(
                s.entra_api_client_id,
                authority=f"https://login.microsoftonline.com/{s.entra_tenant_id}",
                client_credential=s.entra_api_client_secret,
            )
        return _msal_app


def acquire_graph_token_obo(user_assertion: str, scopes: list[str]) -> str:
    result = _confidential_app().acquire_token_on_behalf_of(user_assertion, scopes=scopes)
    if "access_token" in result:
        return result["access_token"]
    error = result.get("error", "")
    if error in ("invalid_grant", "interaction_required", "consent_required"):
        raise AppError(403, "graph_consent_required",
                       "ยังไม่ได้รับอนุญาต (consent) สำหรับสิทธิ์ Microsoft Graph ที่ต้องใช้ กรุณาติดต่อทีม IT",
                       detail={"scopes": scopes})
    raise AppError(502, "obo_failed", "ไม่สามารถขอสิทธิ์ Microsoft Graph ได้", detail={"error": error})
