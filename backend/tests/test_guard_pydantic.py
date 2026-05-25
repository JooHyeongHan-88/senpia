"""Pydantic 기반 슬롯 가드 — 누락·형식오류 → MissingSlot 변환 검증."""

import sys
from pathlib import Path
from typing import Annotated, Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date  # noqa: E402

from agent.guard import validate_tool_args  # noqa: E402
from agent.models import ToolResult  # noqa: E402
from agent.registries.tools import (  # noqa: E402
    _reset_registry_for_tests,
    get_registered_tool,
    register_tool,
)
from tests._runner import run_tests  # noqa: E402


def _setup_demo() -> None:
    _reset_registry_for_tests()

    @register_tool(
        description="검색",
        slot_prompts={"date_from": "시작일을 YYYY-MM-DD 로 알려주세요"},
    )
    async def demo(
        date_from: Annotated[date, "시작일"],
        date_to: Annotated[date, "종료일"],
        format: Annotated[Literal["표", "차트", "요약"], "형식"],
    ) -> ToolResult:
        return ToolResult(content="ok")


def test_none_tool_passes() -> None:
    _setup_demo()
    result = validate_tool_args({}, None)
    assert result.ok is True
    assert result.missing == []


def test_all_required_missing() -> None:
    _setup_demo()
    tool = get_registered_tool("demo")
    result = validate_tool_args({}, tool)
    assert result.ok is False
    keys = {m.key for m in result.missing}
    assert keys == {"date_from", "date_to", "format"}


def test_slot_prompt_override_used() -> None:
    _setup_demo()
    tool = get_registered_tool("demo")
    result = validate_tool_args({}, tool)
    by_key = {m.key: m for m in result.missing}
    # date_from 은 override 있어야 함
    assert by_key["date_from"].question == "시작일을 YYYY-MM-DD 로 알려주세요"
    # date_to 는 override 없으면 description 기반 자동 메시지
    assert "종료일" in by_key["date_to"].question


def test_literal_enum_options_returned() -> None:
    _setup_demo()
    tool = get_registered_tool("demo")
    result = validate_tool_args(
        {"date_from": "2025-01-01", "date_to": "2025-01-02"}, tool
    )
    assert result.ok is False
    by_key = {m.key: m for m in result.missing}
    assert "format" in by_key
    assert by_key["format"].options is not None
    assert set(by_key["format"].options) == {"표", "차트", "요약"}


def test_invalid_date_format_caught() -> None:
    _setup_demo()
    tool = get_registered_tool("demo")
    result = validate_tool_args(
        {"date_from": "오늘", "date_to": "2025-01-02", "format": "표"}, tool
    )
    assert result.ok is False
    by_key = {m.key: m for m in result.missing}
    assert "date_from" in by_key
    # slot_prompts override 가 우선 적용
    assert "YYYY-MM-DD" in by_key["date_from"].question


def test_invalid_literal_caught() -> None:
    _setup_demo()
    tool = get_registered_tool("demo")
    result = validate_tool_args(
        {"date_from": "2025-01-01", "date_to": "2025-01-02", "format": "csv"}, tool
    )
    assert result.ok is False
    by_key = {m.key: m for m in result.missing}
    assert "format" in by_key


def test_all_valid_passes() -> None:
    _setup_demo()
    tool = get_registered_tool("demo")
    result = validate_tool_args(
        {"date_from": "2025-01-01", "date_to": "2025-01-02", "format": "표"}, tool
    )
    assert result.ok is True
    assert result.missing == []


def test_one_error_per_key_only() -> None:
    """같은 키에 여러 에러가 나도 MissingSlot 은 1회만 생성."""
    _setup_demo()
    tool = get_registered_tool("demo")
    # 빈 값 → missing 만 1건 — 중복 발생할 수 있는 케이스 확인
    result = validate_tool_args({"date_from": "", "date_to": "2025-01-02"}, tool)
    by_key = {m.key: m for m in result.missing}
    # 키별 1건만
    assert len(result.missing) == len(by_key)


if __name__ == "__main__":
    run_tests(globals())
