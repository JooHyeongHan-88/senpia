"""앱 버전 + 자동 업데이트 라우터."""

from fastapi import APIRouter, Depends

from api.deps import require_local_origin
from core import updater
from core.version import APP_VERSION

router = APIRouter(prefix="/api", dependencies=[Depends(require_local_origin)])


@router.get("/version")
async def version():
    return {"version": APP_VERSION}


@router.get("/update/check")
async def update_check():
    return updater.check_latest()


@router.post("/update/apply")
async def update_apply():
    return updater.apply_update()


@router.get("/update/status")
async def update_status():
    return updater.get_state()
