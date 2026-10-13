from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.services.sharepoint import get_sharepoint

router = APIRouter(prefix="/api/sharepoint", tags=["sharepoint"])


@router.get("/sites")
def sites(current: CurrentUser = Depends(get_current_user)) -> dict:
    return {"sites": get_sharepoint(current).list_sites()}


@router.get("/drives")
def drives(site_id: str = Query(min_length=1, max_length=300),
           current: CurrentUser = Depends(get_current_user)) -> dict:
    return {"drives": get_sharepoint(current).list_drives(site_id)}


@router.get("/files")
def files(drive_id: str = Query(min_length=1, max_length=300),
          item_id: str | None = Query(default=None, max_length=300),
          q: str | None = Query(default=None, max_length=100),
          current: CurrentUser = Depends(get_current_user)) -> dict:
    """Audio files and folders the signed-in user can access in a document library."""
    entries = get_sharepoint(current).list_children(drive_id, item_id, q)
    return {"items": [e.to_dict() for e in entries]}
