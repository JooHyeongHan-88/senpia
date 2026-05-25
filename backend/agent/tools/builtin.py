"""기본 내장 도구 — 실시간 정보 조회."""

from datetime import datetime

from agent.registries.tools import register_tool


@register_tool(
    description="현재 시각(로컬 타임존)을 ISO 8601 문자열로 반환한다.",
    timeout_seconds=5,
)
async def now() -> str:
    """사용자가 시각을 물을 때 호출하는 데모 도구."""
    return datetime.now().isoformat(timespec="seconds")
