"""순차 서브 에이전트 디스패치 — ``_dispatch_sub_agent``.

오케스트레이터의 call_sub_agent 위임 1건을 격리된 컨텍스트에서 실행하고, 내부
이벤트를 AgentSwitch → AgentProgress×N → AgentReturn 으로 래핑해 yield 한다. 부모
``_run_agent_turn`` 이 AgentReturnEvent.summary 를 캡처해 tool_result 로 변환한다.
"""

from collections.abc import AsyncIterator
from typing import Literal

from agent.config import MAX_AGENT_DEPTH
from agent.models import (
    AgentProgressEvent,
    AgentReturnEvent,
    AgentState,
    AgentSwitchEvent,
    AskUserEvent,
    DeltaEvent,
    ErrorEvent,
    Message,
    ReasoningEvent,
    SkillActiveEvent,
    SkillCompleteEvent,
    StreamEvent,
    ToolCall,
    ToolCallEvent,
    ToolResultEvent,
    TodoUpdateEvent,
)
from agent.registries.agents import AgentRegistry
from agent.registries.prompts import PromptRegistry
from agent.registries.skills import SkillRegistry
from agent.registries.tools import ASK_USER, COMPLETE_SUB_AGENT, ToolRegistry

from agent.harness.budget import TurnBudget
from agent.harness.dispatch.result_format import _extract_task_summary
from agent.harness.dispatch.spec_filter import (
    _filter_specs_for_sub_agent,
    _resolve_agent_skills,
)
from agent.harness.prompt.compose import _compose_sub_agent_system_prompt


async def _dispatch_sub_agent(
    *,
    call: ToolCall,
    parent_agent_id: str,
    agent_registry: AgentRegistry,
    skill_registry: SkillRegistry,
    prompt_registry: PromptRegistry,
    registry: ToolRegistry,
    provider,
    budget: TurnBudget,
    depth: int,
    max_iterations: int,
    orchestrator_state: AgentState | None = None,
    dispatch_id: str | None = None,
    ask_user_mode: Literal["surface", "abort"] = "surface",
    skip_consecutive_guard: bool = False,
) -> AsyncIterator[StreamEvent]:
    """서브 에이전트 turn 을 격리된 컨텍스트에서 실행.

    AgentSwitch → AgentProgress×N → AgentReturn 순으로 yield. 부모 _run_agent_turn
    이 AgentReturnEvent.summary 를 캡처해 tool_result 로 변환한다.

    Args:
        dispatch_id: 이 디스패치의 고유 상관키. emit 하는 모든 agent:* 이벤트에
            실어 프론트가 동시 실행(특히 같은 이름 에이전트)을 구분하게 한다.
        ask_user_mode: AskUserEvent 처리 정책.
            - "surface"(기본, 순차): orchestrator_state 에 pending_sub_agent 저장 후
              AskUserEvent 를 직접 yield — AgentReturnEvent 없이 종료. 부모가
              AskUserEvent 를 감지해 해당 턴을 interrupted 처리한다.
            - "abort"(병렬): 사용자에게 묻지 않고 이 작업만 '입력 필요' 에러 요약의
              AgentReturnEvent 로 변환해 종료. orchestrator_state 는 건드리지 않는다.
        skip_consecutive_guard: True 면 같은-에이전트-연속-호출 가드를 건너뛴다
            (병렬 배치는 의도된 동시성이라 오탐 방지).
    """
    agent_name = (call.arguments or {}).get("agent_name", "")
    task = (call.arguments or {}).get("task", "")

    # 깊이 가드 (J-1): 서브 에이전트가 또 위임을 시도하는 경우 차단.
    if depth > MAX_AGENT_DEPTH:
        yield AgentReturnEvent(
            from_agent=agent_name or "?",
            summary=f"[depth-guard] depth={depth} 초과로 위임 거부",
            dispatch_id=dispatch_id,
        )
        return

    if not skip_consecutive_guard:
        block_reason = budget.check_dispatch(agent_name)
        if block_reason:
            yield AgentReturnEvent(
                from_agent=agent_name, summary=block_reason, dispatch_id=dispatch_id
            )
            return

    agent = agent_registry.get_by_name(agent_name)
    if agent is None:
        yield AgentReturnEvent(
            from_agent=agent_name or "?",
            summary=f"[error] unknown agent: '{agent_name}'",
            dispatch_id=dispatch_id,
        )
        return

    yield AgentSwitchEvent(
        from_agent=parent_agent_id,
        to_agent=agent.meta.name,
        reason=task[:80],
        dispatch_id=dispatch_id,
    )

    def _progress(ev: StreamEvent) -> AgentProgressEvent:
        """서브 raw 이벤트를 dispatch_id 를 실은 AgentProgressEvent 로 래핑한다."""
        return AgentProgressEvent(
            agent_id=agent.meta.name,
            inner_type=ev.type,
            inner_payload=ev.model_dump(exclude={"type"}),
            dispatch_id=dispatch_id,
        )

    # 서브 에이전트가 가지고 진입한 SKILL 목록을 progress 채널로 노출.
    # — UI 가 sub-agent 슬롯 안에 어떤 SKILL 이 활성화됐는지 뱃지로 보여줄 수 있다.
    skill_bodies = _resolve_agent_skills(agent, skill_registry)
    if skill_bodies:
        yield AgentProgressEvent(
            agent_id=agent.meta.name,
            inner_type="skill_active",
            inner_payload={"skills": [s.meta.name for s in skill_bodies]},
            dispatch_id=dispatch_id,
        )

    # 격리된 system prompt — base + safety + agent body + 학습 SKILL body.
    sub_system = _compose_sub_agent_system_prompt(
        base=prompt_registry.compose(fallback="", include_orchestrator=False),
        agent=agent_registry._ensure_body(agent),
        skill_bodies=skill_bodies,
    )
    sub_messages: list[Message] = [
        Message(role="system", content=sub_system),
        Message(role="user", content=task),
    ]
    sub_specs = _filter_specs_for_sub_agent(registry.specs(), agent, skill_bodies)

    # 서브 에이전트 전용 로컬 상태 — PLANNER 도구 지원용. 디스크에 영속화하지 않음.
    sub_state = AgentState()

    # 상호재귀 경계: loop ↔ sequential 순환 import 를 피하려 함수 본문에서 late import.
    # (run_turn 의 set_session_context late import 와 동일한 코드베이스 관례.)
    from agent.harness.loop import _run_agent_turn

    complete_subagent_summary: str | None = None
    last_assistant_text: list[str] = []
    tool_calls_count = 0
    error_count_tracker = 0
    async for ev in _run_agent_turn(
        agent_id=agent.meta.name,
        messages=sub_messages,
        turn_messages=None,
        provider=provider,
        registry=registry,
        sub_specs=sub_specs,
        agent_registry=None,  # sub-agent 는 중첩 dispatch 불가 (L0 방어선)
        prompt_registry=prompt_registry,
        skill_registry=skill_registry,
        budget=budget,
        depth=depth,
        state=sub_state,
        max_iterations=max_iterations,
    ):
        if isinstance(ev, DeltaEvent):
            last_assistant_text.append(ev.content)
            yield _progress(ev)
            continue

        if isinstance(ev, ToolResultEvent) and ev.name == COMPLETE_SUB_AGENT:
            # complete_subagent 호출 결과 캡처 — text parsing 대체.
            complete_subagent_summary = ev.result
            yield _progress(ev)
            continue

        if isinstance(ev, ToolResultEvent):
            # complete_subagent 외 일반 도구 실행 통계 누적.
            tool_calls_count += 1
            if ev.is_error:
                error_count_tracker += 1
            yield _progress(ev)
            continue

        if isinstance(ev, (ToolCallEvent, ReasoningEvent)):
            yield _progress(ev)
            continue

        if isinstance(ev, (TodoUpdateEvent, SkillCompleteEvent, SkillActiveEvent)):
            # 서브 에이전트의 PLANNER 상태 변화 / SKILL 활성·완료 신호를 프론트에 전달.
            # SkillActiveEvent 는 provider 가 sub-agent context 에서 직접 yield 한 경우
            # — mock 의 복합 시연 시나리오가 이 경로로 sub-skill 뱃지를 갱신한다.
            yield _progress(ev)
            continue

        if isinstance(ev, AskUserEvent):
            if ask_user_mode == "abort":
                # 병렬 실행 중 — 사용자에게 직접 묻지 않고 이 작업만 종료한다.
                q = (ev.question or "").strip()
                yield AgentReturnEvent(
                    from_agent=agent.meta.name,
                    summary=(
                        f"[중단] '{agent.meta.name}' 가 사용자 입력이 필요해 완료하지 "
                        "못했습니다"
                        + (f": {q}" if q else "")
                        + ". 이 작업은 call_sub_agent 로 순차 재위임해 사용자에게 "
                        "질문하세요."
                    ),
                    todo_log=list(sub_state.todo_list),
                    tool_calls_count=tool_calls_count,
                    error_count=error_count_tracker,
                    dispatch_id=dispatch_id,
                )
                return
            # 슬롯 부족 또는 ask_user 능동 호출 — orchestrator 에 pending 저장 후 사용자에게 직접 질문.
            if orchestrator_state is not None:
                orchestrator_state.pending_sub_agent = agent.meta.name
                orchestrator_state.pending_sub_task = task
                orchestrator_state.missing_slots = {ev.slot_key: ev.question}
                orchestrator_state.pending_tool = None
                orchestrator_state.pending_args = {}
                # 서브 에이전트가 ask_user sentinel 을 직접 호출한 경우 질문 본문도 기록.
                if ev.tool_name == ASK_USER:
                    orchestrator_state.pending_question = ev.question
            yield ev  # 사용자에게 직접 노출
            return  # AgentReturnEvent 없이 종료 — 부모가 AskUserEvent 를 감지

        if isinstance(ev, ErrorEvent):
            yield AgentReturnEvent(
                from_agent=agent.meta.name,
                summary=f"[error] {agent.meta.name}: {ev.message}",
                dispatch_id=dispatch_id,
            )
            return

        # 그 외 이벤트는 silent drop.

    summary = complete_subagent_summary or _extract_task_summary(
        "".join(last_assistant_text).strip(), agent.meta.name
    )
    yield AgentReturnEvent(
        from_agent=agent.meta.name,
        summary=summary,
        todo_log=list(sub_state.todo_list),
        tool_calls_count=tool_calls_count,
        error_count=error_count_tracker,
        dispatch_id=dispatch_id,
    )
