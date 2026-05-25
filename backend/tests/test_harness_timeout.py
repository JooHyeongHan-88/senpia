"""Harness `_execute_tool` — timeout·sentinel·ToolResult 변환 검증."""

import asyncio
import sys
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.harness import _execute_tool  # noqa: E402
from agent.models import ToolCall, ToolResult  # noqa: E402
from agent.registries.tools import (  # noqa: E402
    ToolRegistry,
    _reset_registry_for_tests,
    register_tool,
)
from tests._runner import run_tests  # noqa: E402


def _setup() -> ToolRegistry:
    _reset_registry_for_tests()
    return ToolRegistry()


async def test_str_return_wraps_in_tool_result() -> None:
    reg = _setup()

    @register_tool(description="에코", timeout_seconds=5)
    async def echo(msg: Annotated[str, "본문"]) -> str:
        return f"echo:{msg}"

    call = ToolCall(id="x", name="echo", arguments={"msg": "hi"})
    result = await _execute_tool(call, reg)
    assert isinstance(result, ToolResult)
    assert result.content == "echo:hi"
    assert result.is_error is False
    assert result.data is None


async def test_tool_result_passes_through() -> None:
    reg = _setup()

    @register_tool(description="구조화 응답")
    async def structured() -> ToolResult:
        return ToolResult(content="ok", data={"a": 1})

    call = ToolCall(id="x", name="structured", arguments={})
    result = await _execute_tool(call, reg)
    assert result.content == "ok"
    assert result.data == {"a": 1}
    assert result.is_error is False


async def test_unknown_tool_returns_error() -> None:
    reg = _setup()
    call = ToolCall(id="x", name="does_not_exist", arguments={})
    result = await _execute_tool(call, reg)
    assert result.is_error is True
    assert "unknown tool" in result.content


async def test_sentinel_bypass_returns_error() -> None:
    reg = _setup()

    @register_tool(description="sentinel", sentinel=True)
    async def my_sent() -> str:
        raise RuntimeError("never")

    call = ToolCall(id="x", name="my_sent", arguments={})
    result = await _execute_tool(call, reg)
    assert result.is_error is True
    assert "sentinel" in result.content.lower()


async def test_timeout_fires() -> None:
    reg = _setup()

    @register_tool(description="느린 도구", timeout_seconds=0.2)
    async def slow() -> str:
        await asyncio.sleep(2.0)
        return "should not return"

    call = ToolCall(id="x", name="slow", arguments={})
    result = await _execute_tool(call, reg)
    assert result.is_error is True
    assert "timeout" in result.content.lower()


async def test_value_error_captured() -> None:
    reg = _setup()

    @register_tool(description="에러 도구")
    async def boom() -> str:
        raise ValueError("bad arg")

    call = ToolCall(id="x", name="boom", arguments={})
    result = await _execute_tool(call, reg)
    assert result.is_error is True
    assert "ValueError" in result.content
    assert "bad arg" in result.content


if __name__ == "__main__":
    run_tests(globals())
