"""도구 실행 + tool 응답 메시지 누적 헬퍼.

``_run_agent_turn`` 이 tool_call 분기에서 사용하는, 등록된 도구를 timeout 안에서
실행해 ``ToolResult`` 로 표준화하고 LLM 컨텍스트·영구 히스토리에 응답을 누적하는
저수준 유틸리티.
"""

import asyncio
import logging

from agent.models import Message, ToolCall, ToolResult
from agent.registries.tools import ToolRegistry

logger = logging.getLogger(__name__)


def _append_tool_result(
    messages: list[Message],
    turn_messages: list[Message] | None,
    call: ToolCall,
    result_text: str,
) -> None:
    """LLM 컨텍스트와 영구 히스토리 양쪽에 tool 응답을 동일하게 누적한다.

    서브 에이전트 호출 시 turn_messages=None — 격리 보장.
    """
    tool_msg = Message(
        role="tool",
        content=result_text,
        tool_call_id=call.id,
    )
    messages.append(tool_msg)
    if turn_messages is not None:
        turn_messages.append(tool_msg)


async def _execute_tool(call: ToolCall, registry: ToolRegistry) -> ToolResult:
    """등록된 도구를 timeout 안에서 실행해 ToolResult 로 표준화한다.

    반환 규약:
        - 도구가 str 반환 → ToolResult(content=str)
        - 도구가 ToolResult 반환 → 그대로
        - timeout / ValueError / KeyError / TypeError → is_error=True ToolResult
        - sentinel 도구가 여기까지 흘러온 경우 (harness 분기 누락) → 명시적 에러
    """
    tool = registry.get(call.name)
    if tool is None:
        return ToolResult(content=f"[error] unknown tool: {call.name}", is_error=True)

    if tool.sentinel:
        # harness 분기가 누락된 프로그래밍 버그 — 조용히 통과하지 말 것.
        return ToolResult(
            content=f"[error] sentinel tool '{call.name}' bypassed harness intercept",
            is_error=True,
        )

    # LLM 이 보낸 raw 문자열 인자를 Pydantic 으로 강제 변환 (str → date 등).
    # validate_tool_args 가 통과시킨 후에도 실제 호출 직전에 한 번 더 coerce 해
    # 도구 함수 본체에서 타입 불일치 에러가 발생하는 경우를 사전 차단한다.
    try:
        parsed = tool.input_model.model_validate(call.arguments or {})
        # model_dump() 는 중첩 Pydantic 모델(ImageItem 등)을 dict 로 직렬화해
        # 도구 함수가 기대하는 타입과 불일치가 생긴다. getattr 로 실제 Python
        # 객체(model 인스턴스 포함)를 그대로 추출한다.
        coerced_args = {
            name: getattr(parsed, name) for name in type(parsed).model_fields
        }
    except Exception as exc:
        logger.warning("tool '%s' argument coercion failed: %s", call.name, exc)
        return ToolResult(
            content=f"[error] 인자 변환 실패: {type(exc).__name__}: {exc}",
            is_error=True,
        )

    try:
        result = await asyncio.wait_for(
            tool.fn(**coerced_args), timeout=tool.timeout_seconds
        )
    except asyncio.TimeoutError:
        result = ToolResult(
            content=f"[timeout] {call.name} exceeded {tool.timeout_seconds}s",
            is_error=True,
        )
    except Exception as exc:
        # 도구가 던질 수 있는 예외 범위를 사전에 열거하기 어려우므로 광역 catch 유지.
        # 단, 스택트레이스를 보존해 운영 중 원인 추적이 가능하도록 한다.
        logger.exception("tool '%s' raised an unexpected exception", call.name)
        result = ToolResult(
            content=f"[error] {type(exc).__name__}: {exc}", is_error=True
        )

    if isinstance(result, str):
        result = ToolResult(content=result)
    elif not isinstance(result, ToolResult):
        # 도구가 dict 등 임의 객체를 돌려주면 문자열화해 LLM 컨텍스트에 안전 전달.
        result = ToolResult(
            content=str(result),
            data={"raw": result} if isinstance(result, dict) else None,
        )

    if result.is_error:
        result.content += "\n\n[System] 작업이 실패했습니다. 에러 로그를 읽고 원인을 분석(Root Cause Analysis)한 뒤 최대 1회 더 재시도하세요."

    return result
