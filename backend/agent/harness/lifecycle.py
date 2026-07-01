"""루프 생애주기 헬퍼 — 예산 임박 wind-down 주입(R7) + 반복 상한 fallback(F6).

``_run_agent_turn`` 전용. 실패 없이 진행 중이어도 예산(반복 상한·turn budget)만
소진돼 사용자 노출 단계(display_*)가 hard-cut 되는 것을 막는 두 갈래를 담는다:

- ``_maybe_inject_wind_down`` — 남은 호출이 임계 이하로 떨어지는 시점에 마무리
  지시문을 ``messages`` 에만 1회 주입(히스토리 비영속).
- ``_emit_max_iterations_fallback`` — 반복 상한 소진 시 도구 없는 최종 요약 라운드.

두 함수 모두 ``prompt/`` 의 '순수 문자열 함수' 불변식과 달리 ``ctx.messages`` 를
변형하거나 ``provider.astream`` 을 호출하고 ``StreamEvent`` 를 yield 하므로,
프롬프트 조립 서브패키지가 아니라 루프 생애주기 모듈에 둔다.
"""

import logging
from collections.abc import AsyncIterator

from agent.models import ErrorEvent, Message, StreamEvent

from agent.debug import trace
from agent.harness.call_handlers import TurnContext
from agent.harness.constants import (
    MAX_ITERATIONS_FALLBACK_INSTRUCTION,
    WIND_DOWN_REMAINING_CALLS,
)
from agent.harness.prompt.wind_down import _build_wind_down_message
from agent.harness.state.todo import _all_todos_terminal

logger = logging.getLogger(__name__)


def _maybe_inject_wind_down(
    ctx: TurnContext, iteration: int, already_notified: bool
) -> bool:
    """남은 호출 여유가 임계 이하면 [System] 마무리 지시문을 messages 에 1회 주입한다 (R7).

    진행은 성공 중인데 예산(반복 상한·turn budget)만 소진돼 사용자 노출 단계(display_*)가
    잘리는 시나리오를 방지한다. 히스토리에는 영속하지 않는다 (messages 한정).

    Returns:
        갱신된 notified 플래그 — 한 번 주입되면 이후 iteration 에서 재주입하지 않는다.
    """
    if already_notified:
        return True
    remaining_calls = min(
        ctx.max_iterations - iteration, ctx.budget.max_calls - ctx.budget.used
    )
    if not 0 < remaining_calls <= WIND_DOWN_REMAINING_CALLS:
        return False
    ctx.messages.append(
        Message(role="user", content=_build_wind_down_message(remaining_calls))
    )
    trace.record("wind_down", remaining_calls=remaining_calls)
    logger.info(
        "agent %s wind-down notified (remaining_calls=%d)",
        ctx.agent_id,
        remaining_calls,
    )
    return True


async def _emit_max_iterations_fallback(
    ctx: TurnContext,
) -> AsyncIterator[StreamEvent]:
    """반복 상한 소진 시 도구 없는 최종 요약 라운드를 돌린다 (F6).

    모든 todo 가 terminal 이면 '복구'(작업 완료·예산 소진)로 판정해 초록 점선,
    아니면 '미완료'로 빨강 점선으로 프론트가 스타일링하도록 is_recovered 플래그를 싣는다.
    """
    is_recovered = (
        ctx.state is not None
        and bool(ctx.state.todo_list)
        and _all_todos_terminal(ctx.state)
    )
    if is_recovered:
        msg = (
            f"[max_iterations] {ctx.agent_id}: 반복 상한({ctx.max_iterations}회)에 "
            "도달했으나 모든 작업이 완료 상태입니다."
        )
    else:
        msg = (
            f"[max_iterations] {ctx.agent_id}: {ctx.max_iterations}회 반복 상한에 "
            "도달했습니다. 작업이 완전히 완료되지 않았을 수 있습니다."
        )
    trace.record(
        "max_iter_fallback",
        max_iterations=ctx.max_iterations,
        is_recovered=is_recovered,
    )
    logger.warning(
        "agent harness reached max_iterations=%d (agent=%s, recovered=%s)",
        ctx.max_iterations,
        ctx.agent_id,
        is_recovered,
    )
    ctx.messages.append(
        Message(role="user", content=MAX_ITERATIONS_FALLBACK_INSTRUCTION)
    )

    buffer: list[str] = []
    async for event in ctx.provider.astream(ctx.messages, []):
        if event.type == "delta":
            buffer.append(event.content)
            yield event
        elif event.type == "done":
            break

    assistant_text = "".join(buffer)
    if assistant_text:
        fallback_response = Message(role="assistant", content=assistant_text)
        ctx.messages.append(fallback_response)
        if ctx.turn_messages is not None:
            ctx.turn_messages.append(fallback_response)
        # 자연어 응답이 생성됐으므로 ErrorEvent 는 프론트에 노출하지 않는다.
        # is_fallback=True 플래그만 보내 UI 가 마지막 메시지를 스타일링하도록 신호.
        yield ErrorEvent(message=msg, is_fallback=True, is_recovered=is_recovered)
    else:
        # fallback LLM 호출 자체가 실패한 경우 — 일반 에러로 노출.
        yield ErrorEvent(message=msg)
