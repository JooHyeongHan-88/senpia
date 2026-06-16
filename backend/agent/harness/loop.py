"""Agent harness 코어 머신 — provider 와 도구 사이의 turn 실행 루프.

run_turn 한 번 = 사용자 입력 1건에 대한 응답 1턴.

흐름:
    1. state_store 에서 AgentState (todo/missing_slots) 를 로드.
    2. PromptRegistry(base+safety+orchestrator) + SkillRegistry.select() 결과 + AGENTS 카탈로그
       + state 요약을 합쳐 오케스트레이터 system prompt 를 동적 조립.
    3. _run_agent_turn (공통 provider→tool 루프) 을 depth=0 으로 호출.
       - delta / tool_call / done 이벤트를 그대로 흘려보냄.
       - tool_call 분기:
           * add_todo / complete_todo → harness 가 직접 AgentState 갱신.
           * call_sub_agent (오케스트레이터 전용) → _dispatch_sub_agent 로 격리 실행.
           * 그 외 도구 → 슬롯 가드 → 통과 시 _execute_tool, 누락 시 AskUserEvent.
    4. 서브 에이전트는 격리된 messages 와 specs(call_sub_agent 제외) 로 자체 turn 을
       수행하고, 모든 raw 이벤트를 AgentProgressEvent 로 래핑해 yield. 마지막 응답에서
       "Task Summary:" 헤더를 추출해 AgentReturnEvent.summary 로 반환.
    5. 턴 종료 시 store.append + state_store.set + DoneEvent.

불변 계약:
    - provider.astream 의 delta/tool_call/done 이벤트 흐름
    - AsyncIterator[StreamEvent] 시그니처
    - 마지막에 DoneEvent yield, 예외는 ErrorEvent 로 변환
    - 서브 에이전트의 상세 메시지는 ConversationStore 에 영속화하지 않음 (컨텍스트 격리)

세부 책임은 같은 패키지의 형제 모듈로 분리됨 — system prompt 조립(``prompt``),
상태 변형·히스토리·루프가드(``state``), 디스패치(``dispatch``), 도구 실행(``tool_exec``),
호출 예산(``budget``). 본 모듈은 그 조각들을 엮는 루프 골격만 보유한다.
"""

import logging
from collections.abc import AsyncIterator, Callable

from agent.config import MAX_PARALLEL_SUBAGENTS
from agent.guard import SlotCheckResult, validate_tool_args
from agent.models import (
    MALFORMED_TOOL_ARGS_KEY,
    AgentReturnEvent,
    AgentState,
    AskUserEvent,
    DoneEvent,
    ErrorEvent,
    Message,
    SkillActiveEvent,
    StreamEvent,
    TodoUpdateEvent,
    ToolCall,
    ToolResultEvent,
    ToolSpec,
)
from agent.registries.agents import AgentRegistry
from agent.registries.prompts import PromptRegistry
from agent.registries.skills import Skill, SkillRegistry
from agent.registries.tools import (
    ACTIVATE_SKILL,
    ASK_USER,
    COMPLETE_SUB_AGENT,
    PLANNER_ADD_TODO,
    PLANNER_COMPLETE_TODO,
    SUB_AGENT_DISPATCH,
    SUB_AGENTS_PARALLEL_DISPATCH,
    ToolRegistry,
)
from agent.stores.agent_state import AgentStateStore
from agent.stores.conversation import ConversationStore

from agent.harness.budget import TurnBudget, _WIND_DOWN_REMAINING_CALLS
from agent.harness.dispatch.parallel import _dispatch_parallel_sub_agents
from agent.harness.dispatch.result_format import _format_sub_agent_result
from agent.harness.dispatch.sequential import _dispatch_sub_agent
from agent.harness.dispatch.spec_filter import (
    _inject_runtime_tools,
    _skills_require_runtime_tools,
)
from agent.harness.prompt.compose import (
    _compose_orchestrator_system_prompt,
    _compose_system_prompt,
)
from agent.harness.prompt.wind_down import _build_wind_down_message
from agent.harness.state.balancing import (
    _balance_all_unresolved,
    _balance_unresolved_tool_calls,
)
from agent.harness.state.loop_guard import (
    _LOOP_GUARD_MESSAGE,
    _call_signature,
    _record_invalid_call,
)
from agent.harness.state.todo import (
    _TERMINAL_STATUSES,
    _all_todos_terminal,
    _build_skill_complete_event,
    _handle_add_todo,
    _handle_complete_todo,
    _mark_running_todo_done,
)
from agent.harness.tool_exec import _append_tool_result, _execute_tool

logger = logging.getLogger(__name__)

ORCHESTRATOR_ID = "orchestrator"


# ---------------------------------------------------------------------------
# 루프 내부 중복 제거 헬퍼 — 여러 sentinel 분기가 공유하는 검증된 공통 로직
# ---------------------------------------------------------------------------


def _emit_missing_slot(
    state: AgentState | None, call: ToolCall, guard: SlotCheckResult
) -> tuple[str, AskUserEvent]:
    """필수 슬롯 누락을 state 에 기록하고 사용자에게 재질문할 AskUserEvent 를 만든다.

    call_sub_agent / call_sub_agents_parallel / 일반 도구 세 분기에 동일하게 중복돼
    있던 블록을 일원화한다. 제어흐름(interrupted=True; break)은 호출부 인라인 유지.

    Returns:
        (tool_result placeholder 텍스트, 사용자에게 보낼 AskUserEvent).
    """
    first = guard.missing[0]
    if state is not None:
        state.missing_slots = {m.key: m.question for m in guard.missing}
        state.pending_tool = call.name
        state.pending_args = dict(call.arguments)
    placeholder = f"[guard] missing required slots: {[m.key for m in guard.missing]}"
    event = AskUserEvent(
        question=first.question,
        slot_key=first.key,
        options=first.options,
        tool_name=call.name,
        input_type="both" if first.options else "text",
    )
    return placeholder, event


def _invalid_call_message(
    call: ToolCall, history_calls: set[tuple[str, str, str]], fallback: str
) -> str:
    """반복된 형식오류 호출이면 루프가드 메시지, 아니면 fallback 을 반환한다.

    malformed args(F3)와 형식오류 분기(invalid_message)의 '루프가드-or-에러' 결정을
    일원화한다. `_record_invalid_call` 이 history_calls 에 시그니처를 기록하는
    부수효과를 그대로 수행한다 (정상↔형식오류 루프 동시 감지).
    """
    if _record_invalid_call(call, history_calls):
        return _LOOP_GUARD_MESSAGE
    return fallback


# ---------------------------------------------------------------------------
# 진입점 — run_turn (오케스트레이터)
# ---------------------------------------------------------------------------


async def run_turn(
    client_id: str,
    user_message: str,
    *,
    store: ConversationStore,
    state_store: AgentStateStore,
    skill_registry: SkillRegistry,
    prompt_registry: PromptRegistry,
    registry: ToolRegistry,
    provider,
    max_iterations: int,
    agent_registry: AgentRegistry | None = None,
    max_agent_calls: int = 10,
    force_skills: list[str] | None = None,
    session_title: str = "",
    user_prompt: str = "",
) -> AsyncIterator[StreamEvent]:
    """사용자 메시지 1건에 대한 응답 이벤트 스트림을 생성한다.

    Args:
        client_id: 세션 식별자 — store / state_store 키.
        user_message: 사용자 입력 본문.
        store: 대화 히스토리 인메모리 저장소.
        state_store: 디스크 영속 AgentState 저장소.
        skill_registry: SKILLS/*.md 트리거 라우터.
        prompt_registry: PROMPTS/*.md 베이스 합성기.
        registry: ToolRegistry — provider 노출 + 실행.
        provider: astream(messages, tools) 를 구현한 LLM 어댑터.
        max_iterations: 한 에이전트 turn 내 provider→tool→provider 반복 상한.
        agent_registry: AGENTS/*.md 카탈로그. None 이거나 비어 있으면 단층 동작
            (기존 SKILLS 직접 라우팅) — 하위호환.
        max_agent_calls: 한 사용자 turn 전체에서 허용하는 provider 호출 합계.
        force_skills: 슬래시 커맨드로 명시된 skill 이름들. 지정 시 trigger 매칭
            대신 이 목록을 그대로 활성화한다.

    Yields:
        StreamEvent: delta / tool_call / tool_result / ask_user / todo_update
            / skill_active / reasoning / agent:switch / agent:progress
            / agent:return / done / error.
    """
    # 세션 컨텍스트를 contextvars 에 저장 — 도구·프로바이더가 산출물 경로 해소 시 참조.
    from core.result_store import set_session_context

    set_session_context(client_id, session_title)

    history = store.get_history(client_id)
    state = state_store.get(client_id)
    # 직전 턴 plan 이 전부 끝났으면 새 턴은 빈 plan 으로 시작한다 — 완료된 todo 가
    # 새 메시지 UI 에 누적 표시되고 '# 현재 To-do' 프롬프트를 매 턴 오염시키는 것을
    # 방지. 비-terminal todo 가 남아 있으면 유지 (AskUser 등 턴 경계를 넘는 plan).
    if state.todo_list and all(
        item.status in _TERMINAL_STATUSES for item in state.todo_list
    ):
        state.todo_list = []
    user_msg = Message(role="user", content=user_message)
    turn_messages: list[Message] = [user_msg]
    # 성공 경로의 append 이후 예외 시 except 가 재-append 해 턴이 중복 영속되는 것을
    # 막는 플래그 (append 성공 ↔ state flush 실패 사이의 좁은 창).
    turn_persisted = False

    try:
        if force_skills:
            skills = skill_registry.get_by_names(force_skills)
        else:
            skills = skill_registry.select(
                user_message, available_tools=registry.names()
            )
        state.active_skills = [s.meta.name for s in skills]

        has_agents = agent_registry is not None and len(agent_registry.list_meta()) > 0

        # 사용자가 SettingsModal 에서 작성한 추가 지침은 PROMPTS/ 합성 결과 뒤에 한 번만
        # 덧붙인다. 합성 순서는 base → safety → tools_guide → orchestrator → 사용자 지침
        # 이 된다. orchestrator 보다 뒤에 오지만 LLM 은 prompt 전체를 한 번에 학습하므로
        # 라우팅 규칙이 사용자 지침에 의해 가려지지 않는다.
        cleaned_user_prompt = user_prompt.strip()
        user_prompt_section = (
            f"\n\n# 사용자 지침\n{cleaned_user_prompt}" if cleaned_user_prompt else ""
        )

        # activate_skill 이 호출될 때 새 system prompt 를 동적 재조립하기 위한 클로저.
        # base prompt 와 state 는 이미 이번 턴 시점으로 확정됐으므로 클로저에 캡처해도 안전.
        if has_agents:
            _base_prompt = (
                prompt_registry.compose(include_orchestrator=True) + user_prompt_section
            )

            def _recompose(updated_skills: list[Skill]) -> str:
                return _compose_orchestrator_system_prompt(
                    base=_base_prompt,
                    skills=updated_skills,
                    state=state,
                    agent_registry=agent_registry,  # type: ignore[arg-type]
                    skill_registry=skill_registry,
                )

            composed_system = _recompose(skills)
        else:
            # 하위호환 — AGENTS 가 없으면 orchestrator.md 제외하고 단층 동작.
            _base_prompt = (
                prompt_registry.compose(include_orchestrator=False)
                + user_prompt_section
            )

            def _recompose(updated_skills: list[Skill]) -> str:  # type: ignore[misc]
                return _compose_system_prompt(
                    _base_prompt, updated_skills, state, skill_registry
                )

            composed_system = _recompose(skills)

        # pending_question 은 직전 턴 ask_user 의 잔재 — 시스템 프롬프트에 1회 주입됐으면
        # 즉시 클리어해야 같은 질문이 두 턴 연속 컨텍스트에 남지 않는다.
        state.pending_question = None

        messages: list[Message] = [
            Message(role="system", content=composed_system),
            *history,
            user_msg,
        ]

        if skills:
            yield SkillActiveEvent(skills=[s.meta.name for s in skills])

        if state.todo_list:
            yield TodoUpdateEvent(todos=list(state.todo_list))

        # 오케스트레이터: COMPLETE_SUB_AGENT 는 서브 에이전트 전용이라 숨김.
        # AGENTS 없으면 위임 도구(순차·병렬)도 제거.
        _delegation_tools = {SUB_AGENT_DISPATCH, SUB_AGENTS_PARALLEL_DISPATCH}
        orchestrator_specs = [
            s
            for s in registry.specs()
            if s.name != COMPLETE_SUB_AGENT
            and (has_agents or s.name not in _delegation_tools)
        ]
        # api_refs 가 있는 SKILL 이 활성화되면 infrastructure tools 를 자동 노출한다 —
        # SKILL 본문에 명시하지 않아도 LLM 이 자체 plan 에 활용 가능.
        if _skills_require_runtime_tools(skills):
            orchestrator_specs = _inject_runtime_tools(orchestrator_specs, registry)

        budget = TurnBudget(max_calls=max_agent_calls)

        active_skills = list(skills)  # turn-local mutable copy for activate_skill

        ask_user_occurred = False
        async for ev in _run_agent_turn(
            agent_id=ORCHESTRATOR_ID,
            messages=messages,
            turn_messages=turn_messages,
            provider=provider,
            registry=registry,
            sub_specs=orchestrator_specs,
            agent_registry=agent_registry,
            prompt_registry=prompt_registry,
            skill_registry=skill_registry,
            budget=budget,
            depth=0,
            state=state,
            max_iterations=max_iterations,
            active_skills=active_skills,
            recompose_system=_recompose,
        ):
            if isinstance(ev, AskUserEvent):
                ask_user_occurred = True
            yield ev

        # F11: AskUser 없이 턴이 완료됐으면 pending_tool/missing_slots 는 사용되지 않은
        # 잔재다 — 다음 턴으로 넘기지 않고 클리어해 오염을 방지한다.
        if not ask_user_occurred:
            state.pending_tool = None
            state.pending_args = {}
            state.missing_slots = {}
            state.pending_sub_agent = None
            state.pending_sub_task = None

        store.append(client_id, *turn_messages)
        turn_persisted = True
        state_store.set(client_id, state)
        yield DoneEvent()

    except Exception as exc:  # noqa: BLE001 — 사용자에게 에러 이벤트로 변환해 전달
        logger.exception("harness run_turn failed")
        # 실패한 턴도 영속한다 — 사용자 메시지까지 증발하면 다음 턴 LLM 컨텍스트가
        # 끊긴다. 미해결 tool_call 쌍은 영속 전에 보정(OpenAI 400 방지)하고,
        # mid-mutation pending 은 F11 과 동일하게 클리어한다. 영속 실패가 에러
        # 알림(ErrorEvent/DoneEvent)을 막으면 안 되므로 best-effort 로 감싼다.
        try:
            state.pending_tool = None
            state.pending_args = {}
            state.missing_slots = {}
            state.pending_sub_agent = None
            state.pending_sub_task = None
            if not turn_persisted:
                _balance_all_unresolved(turn_messages)
                store.append(client_id, *turn_messages)
            state_store.set(client_id, state)
        except Exception:  # noqa: BLE001 — 영속은 best-effort, 이중 실패는 로그만
            logger.exception("run_turn 실패 턴 영속 중 추가 오류 (best-effort 포기)")
        # F12: str(exc) 는 API 키·URL 등 민감 정보를 노출할 수 있으므로 타입만 전달.
        safe = f"[{type(exc).__name__}] 처리 중 오류가 발생했습니다."
        yield ErrorEvent(message=safe)
        yield DoneEvent()


# ---------------------------------------------------------------------------
# 공통 turn 루프 — 오케스트레이터 / 서브 에이전트 공용
# ---------------------------------------------------------------------------


async def _run_agent_turn(
    *,
    agent_id: str,
    messages: list[Message],
    turn_messages: list[Message] | None,
    provider,
    registry: ToolRegistry,
    sub_specs: list[ToolSpec],
    agent_registry: AgentRegistry | None,
    prompt_registry: PromptRegistry,
    skill_registry: SkillRegistry,
    budget: TurnBudget,
    depth: int,
    state: AgentState | None,
    max_iterations: int,
    active_skills: list[Skill] | None = None,
    recompose_system: Callable[[list[Skill]], str] | None = None,
) -> AsyncIterator[StreamEvent]:
    """provider→tool 반복 루프 (agent_id 무관 공통).

    Args:
        agent_id: 'orchestrator' 또는 서브 에이전트 이름. 로깅·이벤트 라벨용.
        messages: in-place 누적되는 LLM 컨텍스트 (호출자 소유).
        turn_messages: 영속화 대상 메시지 누적 버퍼. 서브 에이전트는 None (격리).
        provider: LLM 어댑터.
        registry: ToolRegistry (도구 실행자).
        sub_specs: provider 에게 노출할 도구 스펙 (서브는 call_sub_agent 제외).
        agent_registry: 서브 디스패치용. None 이면 call_sub_agent 분기 비활성.
            **서브 에이전트 context 에서는 반드시 None 으로 전달해야 한다.** 중첩
            sub-agent 위임을 완전히 차단하는 L0 방어선. _dispatch_sub_agent 가
            이 계약을 보장한다. (_filter_specs_for_sub_agent 의 L1 + depth guard
            의 L2 + sentinel guard 의 L3 가 추가 안전망으로 존재한다.)
        prompt_registry: 서브 에이전트 system prompt 합성용.
        skill_registry: 서브 에이전트 SKILL 본문 lazy load 용.
        budget: 한 사용자 turn 단위 호출 카운터.
        depth: 0=orchestrator, 1=sub-agent, 2+ 차단 (MAX_AGENT_DEPTH).
        state: planner 도구 활성 여부. 서브 에이전트는 None (PLANNER 도구 미사용).
        max_iterations: 이 turn 내 provider→tool 반복 상한.

    Yields:
        StreamEvent: delta / tool_call / tool_result / reasoning / ask_user
            / todo_update / agent:switch / agent:progress / agent:return / error.
    """
    # sub-agent context 에서는 agent_registry 가 None 이어야 한다.
    # turn_messages=None 은 "서브 에이전트로 호출됐다"는 관례적 신호.
    assert turn_messages is not None or agent_registry is None, (
        "_run_agent_turn: sub-agent context(turn_messages=None)에서 "
        "agent_registry 가 None 이 아님 — 중첩 sub-agent dispatch 가 열릴 수 있습니다. "
        "_dispatch_sub_agent 가 agent_registry=None 으로 호출하는지 확인하세요."
    )
    assistant_buffer: list[str] = []
    pending_tool_calls: list[ToolCall] = []
    history_calls: set[tuple[str, str, str]] = set()
    wind_down_notified = False

    for iteration in range(max_iterations):
        # R7: 남은 호출 여유가 임계 이하로 떨어지면 상한 도달로 hard-cut 되기 전에
        # 마무리를 지시한다 — 진행은 성공 중인데 예산만 소진돼 사용자 노출 단계
        # (display_*)가 잘리는 시나리오 방지. messages 에만 추가 (히스토리 비영속).
        remaining_calls = min(
            max_iterations - iteration, budget.max_calls - budget.used
        )
        if not wind_down_notified and 0 < remaining_calls <= _WIND_DOWN_REMAINING_CALLS:
            messages.append(
                Message(role="user", content=_build_wind_down_message(remaining_calls))
            )
            wind_down_notified = True
            logger.info(
                "agent %s wind-down notified (remaining_calls=%d)",
                agent_id,
                remaining_calls,
            )

        if not budget.try_consume():
            yield ErrorEvent(
                message=f"[budget] {agent_id}: provider 호출 상한({budget.max_calls}) 초과"
            )
            return

        assistant_buffer.clear()
        pending_tool_calls.clear()

        async for event in provider.astream(messages, sub_specs):
            if event.type == "delta":
                assistant_buffer.append(event.content)
                yield event
                continue

            if event.type == "tool_call":
                pending_tool_calls.append(event.call)
                yield event
                continue

            if event.type == "reasoning":
                yield event
                continue

            if event.type == "skill_active":
                # provider 가 내부 단계 전환 시점에 직접 emit 하는 경우 (mock 시나리오 등).
                # 루프를 끊지 않고 그대로 흘려보낸다.
                yield event
                continue

            if event.type == "done":
                break

            yield event
            return

        assistant_text = "".join(assistant_buffer)

        if not pending_tool_calls:
            if assistant_text and turn_messages is not None:
                turn_messages.append(Message(role="assistant", content=assistant_text))
            return

        assistant_msg = Message(
            role="assistant",
            content=assistant_text,
            tool_calls=list(pending_tool_calls),
        )
        messages.append(assistant_msg)
        if turn_messages is not None:
            turn_messages.append(assistant_msg)

        interrupted = False
        for call in pending_tool_calls:
            # F3: provider 가 tool_call 인자 JSON 파싱에 실패한 경우 — 사용자에게 묻지
            # 않고 LLM 에 재전송을 요구한다 (빈 인자로 오인 → 슬롯 누락 질문 방지).
            if MALFORMED_TOOL_ARGS_KEY in (call.arguments or {}):
                result_content = _invalid_call_message(
                    call,
                    history_calls,
                    f"[arg-error] '{call.name}' 도구의 인자가 유효한 JSON 이 "
                    "아닙니다 (스트리밍 중 잘렸거나 형식이 깨졌습니다). 인자를 더 "
                    "짧고 정확한 JSON 으로 같은 도구를 다시 호출하세요.",
                )
                _append_tool_result(messages, turn_messages, call, result_content)
                yield ToolResultEvent(
                    tool_call_id=call.id,
                    name=call.name,
                    result=result_content,
                    is_error=True,
                )
                continue

            # activate_skill — SKILL 카탈로그 의미 기반 활성화. turn-local active_skills 갱신.
            if call.name == ACTIVATE_SKILL and active_skills is not None:
                skill_name = (call.arguments or {}).get("name", "").strip()
                existing_names = {s.meta.name for s in active_skills}
                newly_activated = (
                    skill_registry.get_by_names([skill_name])
                    if skill_name and skill_name not in existing_names
                    else []
                )
                active_skills.extend(newly_activated)
                if newly_activated and recompose_system is not None:
                    messages[0] = Message(
                        role="system", content=recompose_system(list(active_skills))
                    )
                    yield SkillActiveEvent(skills=[s.meta.name for s in active_skills])
                    if state is not None:
                        state.active_skills = [s.meta.name for s in active_skills]
                result_text = (
                    f"SKILL '{skill_name}' 활성화됨. 이제 해당 SKILL 의 지침이 컨텍스트에 포함됩니다."
                    if newly_activated
                    else (
                        f"SKILL '{skill_name}' 은(는) 이미 활성화되어 있거나 카탈로그에 없습니다."
                    )
                )
                _append_tool_result(messages, turn_messages, call, result_text)
                yield ToolResultEvent(
                    tool_call_id=call.id,
                    name=call.name,
                    result=result_text,
                    is_error=not newly_activated,
                )
                continue

            # complete_subagent — 서브 에이전트 종료 sentinel (turn_messages=None 이 서브 에이전트 지표).
            if call.name == COMPLETE_SUB_AGENT and turn_messages is None:
                result_text = (call.arguments or {}).get("summary", "")
                _append_tool_result(messages, turn_messages, call, result_text)
                yield ToolResultEvent(
                    tool_call_id=call.id, name=call.name, result=result_text
                )
                return  # 서브 에이전트 완료 — _dispatch_sub_agent 가 ToolResultEvent 를 캡처

            # PLANNER 도구는 state 가 있을 때만 (서브 에이전트도 sub_state 가 주입되므로 동작함).
            if call.name == PLANNER_ADD_TODO and state is not None:
                result_text = _handle_add_todo(state, call.arguments)
                _append_tool_result(messages, turn_messages, call, result_text)
                yield ToolResultEvent(
                    tool_call_id=call.id, name=call.name, result=result_text
                )
                yield TodoUpdateEvent(todos=list(state.todo_list))
                continue

            if call.name == PLANNER_COMPLETE_TODO and state is not None:
                result_text = _handle_complete_todo(state, call.arguments)
                _append_tool_result(messages, turn_messages, call, result_text)
                yield ToolResultEvent(
                    tool_call_id=call.id, name=call.name, result=result_text
                )
                yield TodoUpdateEvent(todos=list(state.todo_list))
                if _all_todos_terminal(state):
                    yield _build_skill_complete_event(state)
                continue

            # ask_user sentinel — LLM 능동 보완 질문. tool_result placeholder 한 줄 + AskUserEvent 후 turn 중단.
            if call.name == ASK_USER:
                args = call.arguments or {}
                question = (args.get("question") or "").strip()
                options = args.get("options")
                input_type = args.get("input_type", "both")

                # 정규화: options 가 비어 있으면 자유입력만, 비정상 input_type 은 both 로 폴백.
                if not options:
                    options = None
                    input_type = "text"
                elif input_type not in ("choice", "text", "both"):
                    input_type = "both"

                if state is not None:
                    state.pending_question = question

                placeholder = f"[ask_user] 사용자에게 질문을 던졌습니다: {question}"
                _append_tool_result(messages, turn_messages, call, placeholder)
                yield ToolResultEvent(
                    tool_call_id=call.id, name=call.name, result=placeholder
                )
                yield AskUserEvent(
                    question=question,
                    slot_key=ASK_USER,
                    options=options,
                    tool_name=ASK_USER,
                    input_type=input_type,
                )
                interrupted = True
                break

            # 서브 에이전트 디스패치 — async generator nesting 으로 통과.
            if call.name == SUB_AGENT_DISPATCH and agent_registry is not None:
                guard = validate_tool_args(call.arguments, registry.get(call.name))
                if guard.invalid_message:
                    # call_sub_agent 인자 형식 오류 — 사용자 미개입, LLM self-correct.
                    result_content = _invalid_call_message(
                        call, history_calls, guard.invalid_message
                    )
                    _append_tool_result(messages, turn_messages, call, result_content)
                    yield ToolResultEvent(
                        tool_call_id=call.id,
                        name=call.name,
                        result=result_content,
                        is_error=True,
                    )
                    continue
                if not guard.ok:
                    placeholder, ask_ev = _emit_missing_slot(state, call, guard)
                    _append_tool_result(messages, turn_messages, call, placeholder)
                    yield ask_ev
                    interrupted = True
                    break

                captured_summary = (
                    f"[error] {call.arguments.get('agent_name', '?')}: "
                    "sub-agent 가 요약을 반환하지 않음"
                )
                sub_interrupted = False
                async for sub_ev in _dispatch_sub_agent(
                    call=call,
                    parent_agent_id=agent_id,
                    agent_registry=agent_registry,
                    skill_registry=skill_registry,
                    prompt_registry=prompt_registry,
                    registry=registry,
                    provider=provider,
                    budget=budget,
                    depth=depth + 1,
                    max_iterations=max_iterations,
                    orchestrator_state=state,
                ):
                    yield sub_ev
                    if isinstance(sub_ev, AgentReturnEvent):
                        # todo_log 와 통계를 포함한 구조화 텍스트로 LLM 컨텍스트에 주입.
                        captured_summary = _format_sub_agent_result(sub_ev)
                    elif isinstance(sub_ev, AskUserEvent):
                        # 서브 에이전트 슬롯 부족 — 사용자 질문을 그대로 전달 후 중단.
                        sub_interrupted = True

                if sub_interrupted:
                    interrupted = True
                    break

                # 성공적 완료 — pending_sub_agent 초기화
                if state is not None:
                    dispatched_name = (call.arguments or {}).get("agent_name")
                    if state.pending_sub_agent == dispatched_name:
                        state.pending_sub_agent = None
                        state.pending_sub_task = None
                        state.missing_slots = {}

                _append_tool_result(messages, turn_messages, call, captured_summary)
                yield ToolResultEvent(
                    tool_call_id=call.id, name=call.name, result=captured_summary
                )
                continue

            # 병렬 서브 에이전트 디스패치 — 독립 작업들을 동시에 실행하고 단일 결과로 합침.
            if call.name == SUB_AGENTS_PARALLEL_DISPATCH and agent_registry is not None:
                guard = validate_tool_args(call.arguments, registry.get(call.name))
                if guard.invalid_message:
                    # tasks 형식 오류 — 사용자 미개입, LLM self-correct.
                    result_content = _invalid_call_message(
                        call, history_calls, guard.invalid_message
                    )
                    _append_tool_result(messages, turn_messages, call, result_content)
                    yield ToolResultEvent(
                        tool_call_id=call.id,
                        name=call.name,
                        result=result_content,
                        is_error=True,
                    )
                    continue
                if not guard.ok:
                    placeholder, ask_ev = _emit_missing_slot(state, call, guard)
                    _append_tool_result(messages, turn_messages, call, placeholder)
                    yield ask_ev
                    interrupted = True
                    break

                # 병렬 디스패처가 모든 서브 에이전트 이벤트를 인터리브해 yield 하고,
                # 완료 후 통합 요약을 result_holder["combined"] 에 채운다.
                parallel_result: dict[str, str] = {}
                async for sub_ev in _dispatch_parallel_sub_agents(
                    call=call,
                    parent_agent_id=agent_id,
                    agent_registry=agent_registry,
                    skill_registry=skill_registry,
                    prompt_registry=prompt_registry,
                    registry=registry,
                    provider=provider,
                    budget=budget,
                    depth=depth + 1,
                    max_iterations=max_iterations,
                    orchestrator_state=state,
                    max_parallel=MAX_PARALLEL_SUBAGENTS,
                    result_holder=parallel_result,
                ):
                    yield sub_ev

                captured_summary = parallel_result.get(
                    "combined", "[error] 병렬 위임 결과가 비어 있습니다"
                )
                _append_tool_result(messages, turn_messages, call, captured_summary)
                yield ToolResultEvent(
                    tool_call_id=call.id, name=call.name, result=captured_summary
                )
                continue

            tool = registry.get(call.name)
            guard = validate_tool_args(call.arguments, tool)
            if guard.invalid_message:
                # 형식 오류 — 사용자에게 묻지 않고 LLM 에 도구 에러로 회신해 self-correct.
                result_content = _invalid_call_message(
                    call, history_calls, guard.invalid_message
                )
                _append_tool_result(messages, turn_messages, call, result_content)
                yield ToolResultEvent(
                    tool_call_id=call.id,
                    name=call.name,
                    result=result_content,
                    is_error=True,
                )
                continue
            if not guard.ok:
                placeholder, ask_ev = _emit_missing_slot(state, call, guard)
                _append_tool_result(messages, turn_messages, call, placeholder)
                yield ask_ev
                interrupted = True
                break

            call_sig = _call_signature(call)
            if call_sig in history_calls:
                result_content = _LOOP_GUARD_MESSAGE
                _append_tool_result(messages, turn_messages, call, result_content)
                yield ToolResultEvent(
                    tool_call_id=call.id,
                    name=call.name,
                    result=result_content,
                    is_error=True,
                )
                if state is not None:
                    if state.pending_tool == call.name:
                        state.pending_tool = None
                        state.pending_args = {}
                        state.missing_slots = {}
                continue
            else:
                history_calls.add(call_sig)

            result = await _execute_tool(call, registry)
            _append_tool_result(messages, turn_messages, call, result.content)
            yield ToolResultEvent(
                tool_call_id=call.id,
                name=call.name,
                result=result.content,
                data=result.data,
                is_error=result.is_error,
            )

            if state is not None:
                todo_updated = _mark_running_todo_done(
                    state, call.name, result.content, is_error=result.is_error
                )
                if todo_updated:
                    yield TodoUpdateEvent(todos=list(state.todo_list))
                    if _all_todos_terminal(state):
                        yield _build_skill_complete_event(state)
                if state.pending_tool == call.name:
                    state.pending_tool = None
                    state.pending_args = {}
                    state.missing_slots = {}

        if interrupted:
            # 배치 도구 호출 중간에 중단되면 뒤따르는 tool_call 이 응답 없이 남는다.
            # 모든 tool_call 에 placeholder 응답을 채워 메시지 정합성(OpenAI 규약)을 지킨다.
            _balance_unresolved_tool_calls(messages, turn_messages, assistant_msg)
            return
    else:
        # 모든 todo 가 terminal 상태면 작업은 완료됐으나 예산만 소진된 것 — "복구"로 판정.
        is_recovered = (
            state is not None and bool(state.todo_list) and _all_todos_terminal(state)
        )
        if is_recovered:
            msg = (
                f"[max_iterations] {agent_id}: 반복 상한({max_iterations}회)에 도달했으나 "
                "모든 작업이 완료 상태입니다."
            )
        else:
            msg = (
                f"[max_iterations] {agent_id}: {max_iterations}회 반복 상한에 도달했습니다. "
                "작업이 완전히 완료되지 않았을 수 있습니다."
            )
        logger.warning(
            "agent harness reached max_iterations=%d (agent=%s, recovered=%s)",
            max_iterations,
            agent_id,
            is_recovered,
        )
        fallback_msg = Message(
            role="user",
            content="[System] 에이전트 반복 상한에 도달했거나 작업이 중단되었습니다. 지금까지 완료한 작업과 실패한 원인을 정리하여 사용자에게 자연어로 최종 답변을 작성하세요. 도구를 호출하지 마세요.",
        )
        messages.append(fallback_msg)

        assistant_buffer.clear()
        async for event in provider.astream(messages, []):
            if event.type == "delta":
                assistant_buffer.append(event.content)
                yield event
            elif event.type == "done":
                break

        assistant_text = "".join(assistant_buffer)
        if assistant_text:
            fallback_response = Message(role="assistant", content=assistant_text)
            messages.append(fallback_response)
            if turn_messages is not None:
                turn_messages.append(fallback_response)
            # 자연어 응답이 생성됐으므로 ErrorEvent 는 프론트에 노출하지 않는다.
            # is_fallback=True 플래그만 보내 UI 가 마지막 메시지를 스타일링하도록 신호.
            yield ErrorEvent(message=msg, is_fallback=True, is_recovered=is_recovered)
        else:
            # fallback LLM 호출 자체가 실패한 경우 — 일반 에러로 노출.
            yield ErrorEvent(message=msg)
