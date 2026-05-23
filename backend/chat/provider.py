"""LLM Provider 추상화.

provider 는 messages + tools 를 받아 비동기 StreamEvent 시퀀스를 흘려보낸다.
harness 는 이벤트 종류(delta/tool_call/done/error)만 보고 동작하므로
mock 이든 vLLM 이든 같은 코드로 다룰 수 있다.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Protocol

from chat.models import (
    DeltaEvent,
    DoneEvent,
    Message,
    StreamEvent,
    ToolCall,
    ToolCallEvent,
    ToolSpec,
)

# MockProvider 가 토큰 1개를 흘려보낼 때 사이에 두는 지연(초).
_MOCK_TOKEN_DELAY = 0.02

# MockProvider 가 "now" 도구를 가짜로 호출하게 만드는 트리거 문자열.
_NOW_TOOL_TRIGGERS = (
    "몇 시",
    "지금 시간",
    "현재 시각",
    "what time",
    "current time",
    "now()",
)


class LLMProvider(Protocol):
    async def astream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AsyncIterator[StreamEvent]:
        """messages 와 tools 를 기반으로 응답 이벤트를 흘려보낸다.

        반드시 DoneEvent 로 종료해야 한다. tool_call 을 발행했을 경우 harness 가
        tool 실행 후 messages 에 결과를 붙여 다시 astream 을 호출한다.
        """
        ...


class MockProvider:
    """LLM 없이 인터페이스를 검증하기 위한 가짜 provider.

    동작:
        - 마지막 user 메시지에 _NOW_TOOL_TRIGGERS 가 포함되어 있고
          아직 같은 턴에서 tool 결과를 보지 못했다면, 'now' tool_call 을 1회 발행한다.
        - 그 외에는 마지막 user 메시지를 글자 단위로 잘라 delta 로 흘려보낸다.
    """

    async def astream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AsyncIterator[StreamEvent]:
        last_user = _find_last_user(messages)
        already_called_now = any(
            m.role == "tool" and (m.tool_call_id or "").startswith("mock-now-")
            for m in messages
        )

        if (
            last_user is not None
            and _should_call_now(last_user.content)
            and not already_called_now
        ):
            yield ToolCallEvent(
                call=ToolCall(
                    id=f"mock-now-{uuid.uuid4().hex[:8]}",
                    name="now",
                    arguments={},
                )
            )
            yield DoneEvent()
            return

        reply = _compose_reply(last_user, messages)
        for ch in reply:
            await asyncio.sleep(_MOCK_TOKEN_DELAY)
            yield DeltaEvent(content=ch)

        yield DoneEvent()


def _find_last_user(messages: list[Message]) -> Message | None:
    for m in reversed(messages):
        if m.role == "user":
            return m
    return None


def _should_call_now(text: str) -> bool:
    lowered = text.lower()
    return any(trigger.lower() in lowered for trigger in _NOW_TOOL_TRIGGERS)


def _compose_reply(last_user: Message | None, messages: list[Message]) -> str:
    """mock 응답 본문. tool 결과가 직전에 있으면 그 값을 활용해 답한다."""
    if messages and messages[-1].role == "tool":
        return f"현재 시각은 {messages[-1].content} 입니다."

    if last_user is None:
        return "안녕하세요. 무엇을 도와드릴까요?"

    return f"[mock] '{last_user.content}' 라고 하셨네요. 실제 LLM 이 연결되면 이 자리에 답변이 옵니다."


def get_provider() -> LLMProvider:
    """config.LLM_PROVIDER 값에 따라 provider 구현체를 반환.

    현재는 mock 만 지원. vLLM provider 추가 시 여기 분기 추가.
    """
    from config import LLM_PROVIDER

    if LLM_PROVIDER == "mock":
        return MockProvider()

    raise ValueError(f"unsupported LLM_PROVIDER: {LLM_PROVIDER}")
