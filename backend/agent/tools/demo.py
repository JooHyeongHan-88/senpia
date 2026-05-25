"""슬롯 가드 / Pydantic 검증 흐름을 시연하는 데모 도구."""

from datetime import date
from typing import Annotated, Literal

from agent.models import ToolResult
from agent.registries.tools import register_tool


@register_tool(
    description=(
        "지정한 기간과 형식으로 데이터를 검색한다. "
        "date_from, date_to, format 세 인자가 모두 필요하다."
    ),
    slot_prompts={
        "date_from": "검색 시작일을 알려 주세요 (예: 2025-01-01)",
        "date_to": "검색 종료일을 알려 주세요 (예: 2025-01-31)",
        "format": "결과를 어떤 형식으로 볼까요? (표 / 차트 / 요약)",
    },
)
async def demo_search(
    date_from: Annotated[date, "검색 시작일 (YYYY-MM-DD)"],
    date_to: Annotated[date, "검색 종료일 (YYYY-MM-DD)"],
    format: Annotated[Literal["표", "차트", "요약"], "출력 형식"],
) -> ToolResult:
    """가짜 검색 결과를 ToolResult 로 반환 — 구조화 응답 패턴 데모."""
    return ToolResult(
        content=(
            f"[demo] {date_from} ~ {date_to} 기간의 데이터를 '{format}' 형식으로 검색했습니다."
        ),
        data={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "format": format,
            "row_count": 0,
        },
    )
