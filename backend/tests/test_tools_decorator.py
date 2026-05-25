"""`@register_tool` 데코레이터 — 등록·스키마 자동 생성 검증."""

import sys
from pathlib import Path
from typing import Annotated, Literal

# 백엔드 루트를 sys.path 에 추가해 `agent.*` import 가능하게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date  # noqa: E402

from agent.models import ToolResult  # noqa: E402
from agent.registries.tools import (  # noqa: E402
    _reset_registry_for_tests,
    all_registered_tools,
    get_registered_tool,
    register_tool,
)
from tests._runner import run_tests  # noqa: E402


def _setup() -> None:
    _reset_registry_for_tests()


def test_minimal_function_registers() -> None:
    _setup()

    @register_tool(description="간단 도구")
    async def my_simple_tool() -> str:
        return "ok"

    rt = get_registered_tool("my_simple_tool")
    assert rt is not None, "도구가 등록되지 않음"
    assert rt.name == "my_simple_tool"
    assert rt.description == "간단 도구"
    assert rt.parameters["type"] == "object"
    assert rt.parameters["properties"] == {}
    assert rt.parameters["required"] == []
    assert rt.sentinel is False


def test_description_falls_back_to_docstring() -> None:
    _setup()

    @register_tool()
    async def docstring_tool() -> str:
        """첫 줄 설명.

        두 번째 줄은 무시되어야 한다.
        """
        return "ok"

    rt = get_registered_tool("docstring_tool")
    assert rt is not None
    assert rt.description == "첫 줄 설명."


def test_annotated_params_become_schema_properties() -> None:
    _setup()

    @register_tool(description="기간 검색")
    async def date_range(
        date_from: Annotated[date, "시작일"],
        date_to: Annotated[date, "종료일"],
        format: Annotated[Literal["표", "차트"], "출력 형식"] = "표",
    ) -> ToolResult:
        return ToolResult(content="ok")

    rt = get_registered_tool("date_range")
    assert rt is not None
    props = rt.parameters["properties"]
    assert "date_from" in props
    assert "date_to" in props
    assert "format" in props
    assert props["date_from"]["description"] == "시작일"
    assert props["date_from"]["format"] == "date"
    # Literal 은 enum 으로 변환된다.
    assert set(props["format"]["enum"]) == {"표", "차트"}
    # default 없는 두 필드만 required.
    assert set(rt.parameters["required"]) == {"date_from", "date_to"}


def test_sentinel_tool_registered_without_calling_fn() -> None:
    _setup()

    @register_tool(description="sentinel", sentinel=True)
    async def my_sentinel(payload: Annotated[str, "임의"]) -> str:
        raise RuntimeError("must not be called")

    rt = get_registered_tool("my_sentinel")
    assert rt is not None
    assert rt.sentinel is True
    # 함수 자체 호출 시에는 RuntimeError. 등록만으로는 실행되지 않음 — 등록 단계에서 예외 없음을 확인.
    assert rt.fn is my_sentinel


def test_duplicate_registration_overwrites() -> None:
    _setup()

    @register_tool(description="v1")
    async def dup_tool() -> str:
        return "v1"

    @register_tool(description="v2")
    async def dup_tool() -> str:  # noqa: F811 — 의도된 재등록
        return "v2"

    rt = get_registered_tool("dup_tool")
    assert rt is not None
    assert rt.description == "v2"


def test_timeout_falls_back_to_default() -> None:
    _setup()
    from agent.config import TOOL_DEFAULT_TIMEOUT

    @register_tool(description="기본 timeout")
    async def t1() -> str:
        return "ok"

    @register_tool(description="명시 timeout", timeout_seconds=2.5)
    async def t2() -> str:
        return "ok"

    assert get_registered_tool("t1").timeout_seconds == TOOL_DEFAULT_TIMEOUT
    assert get_registered_tool("t2").timeout_seconds == 2.5


def test_non_async_function_rejected() -> None:
    _setup()
    raised = False
    try:

        @register_tool(description="동기 함수")
        def sync_tool() -> str:  # type: ignore[misc]
            return "no"

    except TypeError:
        raised = True
    assert raised, "동기 함수는 TypeError 로 거부되어야 함"


def test_all_registered_lists_everything() -> None:
    _setup()

    @register_tool(description="a")
    async def a_tool() -> str:
        return "a"

    @register_tool(description="b")
    async def b_tool() -> str:
        return "b"

    names = {rt.name for rt in all_registered_tools()}
    assert names == {"a_tool", "b_tool"}


if __name__ == "__main__":
    run_tests(globals())
