"""Agent harness 코어 머신 — provider 와 도구 사이의 turn 실행 루프.

run_turn 한 번 = 사용자 입력 1건에 대한 응답 1턴.

흐름:
    1. state_store 에서 AgentState (todo/missing_slots) 를 로드.
    2. PromptRegistry(base+safety+orchestrator) + SkillRegistry.select() 결과 + AGENTS 카탈로그
       + state 요약을 합쳐 오케스트레이터 system prompt 를 동적 조립.
    3. _run_agent_turn (공통 provider→tool 루프) 을 depth=0 으로 호출.
       - delta / tool_call / done 이벤트를 그대로 흘려보냄.
       - 각 tool_call 은 ``call_handlers._handle_tool_call`` 에 위임 (3단계 파이프라인).
    4. 서브 에이전트는 격리된 messages 와 specs(call_sub_agent 제외) 로 자체 turn 을
       수행하고, 모든 raw 이벤트를 AgentProgressEvent 로 래핑해 yield. 마지막 응답에서
       "Task Summary:" 헤더를 추출해 AgentReturnEvent.summary 로 반환.
    5. 턴 종료 시 store.append + state_store.set + DoneEvent.

불변 계약:
    - provider.astream 의 delta/tool_call/done 이벤트 흐름
    - AsyncIterator[StreamEvent] 시그니처
    - 마지막에 DoneEvent yield, 예외는 ErrorEvent 로 변환
    - 서브 에이전트의 상세 메시지는 ConversationStore 에 영속화하지 않음 (컨텍스트 격리)

세부 책임은 같은 패키지의 형제 모듈로 분리됨 — system prompt 조립(``prompt`` —
composer 클로저 포함), 상태 변형·히스토리·루프가드·실패 턴 영속(``state``),
서브 에이전트 위임·도구 스펙 선별(``dispatch``), 도구 실행(``tool_exec``),
호출 예산(``budget``), tool_call 단건 처리(``call_handlers``), 루프 생애주기
헬퍼(wind-down·fallback, ``lifecycle``), 히스토리 압축(``compaction``),
루프 상수(``constants``). 본 모듈은 그 조각들을 엮는 루프 골격만 보유한다.
"""

import logging
from collections.abc import AsyncIterator, Callable

from agent.models import (
    AgentState,
    AskUserEvent,
    DoneEvent,
    ErrorEvent,
    Message,
    SkillActiveEvent,
    StreamEvent,
    TodoUpdateEvent,
    ToolCall,
    ToolSpec,
)
from agent.config import COMPACTION_ENABLED, OBJECTIVE_MAX_CHARS
from agent.registries.agents import AgentRegistry
from agent.registries.prompts import PromptRegistry
from agent.registries.skills import Skill, SkillRegistry
from agent.registries.tools import ToolRegistry
from agent.providers.factory import LLMProvider
from agent.stores.agent_state import AgentStateStore
from agent.stores.conversation import ConversationStore

from agent.debug import trace
from agent.harness.budget import TurnBudget
from agent.harness.call_handlers import (
    CallOutcome,
    TurnContext,
    _handle_tool_call,
)
from agent.harness.compaction import _compact_history
from agent.harness.constants import ORCHESTRATOR_ID
from agent.harness.dispatch.spec_filter import _build_orchestrator_specs
from agent.harness.lifecycle import (
    _emit_max_iterations_fallback,
    _maybe_inject_wind_down,
)
from agent.harness.prompt.compose import _make_system_prompt_composer
from agent.harness.state.balancing import _balance_unresolved_tool_calls
from agent.harness.state.pending import clear_all_pending, has_pending
from agent.harness.state.persistence import _persist_failed_turn
from agent.harness.state.todo import _TERMINAL_STATUSES

logger = logging.getLogger(__name__)


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
    provider: LLMProvider,
    max_iterations: int,
    agent_registry: AgentRegistry | None = None,
    max_agent_calls: int = 10,
    force_skills: list[str] | None = None,
    session_title: str = "",
    user_prompt: str = "",
    orchestrator_api_refs: list[str] | None = None,
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
        orchestrator_api_refs: 오케스트레이터 baseline api_refs
            (APP_ORCHESTRATOR_API_REFS). None/빈 리스트면 기존 동작(SKILL 주도)과
            동일하다. 지정 시 활성 SKILL 과 무관하게 라이브러리 API 노출 +
            런타임 도구 주입이 상시 켜진다.

    Yields:
        StreamEvent: delta / tool_call / tool_result / ask_user / todo_update
            / skill_active / reasoning / agent:switch / agent:progress
            / agent:return / done / error.
    """
    # 세션 컨텍스트를 contextvars 에 저장 — 도구·프로바이더가 산출물 경로 해소 시 참조.
    from core.result_store import set_session_context

    set_session_context(client_id, session_title)
    trace.start_turn_trace()

    history = store.get_history(client_id)
    state = state_store.get(client_id)
    # 직전 턴 plan 이 전부 끝났으면 새 턴은 빈 plan 으로 시작한다 — 완료된 todo 가
    # 새 메시지 UI 에 누적 표시되고 '# 현재 To-do' 프롬프트를 매 턴 오염시키는 것을
    # 방지. 비-terminal todo 가 남아 있으면 유지 (AskUser 등 턴 경계를 넘는 plan).
    if state.todo_list and all(
        item.status in _TERMINAL_STATUSES for item in state.todo_list
    ):
        state.todo_list = []
    # 세션 첫 턴(history 비어있음)의 사용자 메시지를 원래 목표로 1회 박제한다 —
    # 이후 히스토리가 트림돼도 매 턴 '# 이전 진행 요약' 으로 재주입되는 안정 앵커.
    if not state.objective and not history and user_message.strip():
        state.objective = user_message.strip()[:OBJECTIVE_MAX_CHARS]
    user_msg = Message(role="user", content=user_message)
    turn_messages: list[Message] = [user_msg]
    baseline_api_refs = orchestrator_api_refs or []
    # 성공 경로의 append 이후 예외 시 except 가 재-append 해 턴이 중복 영속되는 것을
    # 막는 플래그 (append 성공 ↔ state flush 실패 사이의 좁은 창).
    turn_persisted = False

    try:
        if force_skills:
            # force(=유저 슬래시)는 유저 표면이므로 expose=False 비공개 SKILL 을 거부한다.
            # get_by_names 자체는 그대로 둔다 — activate_skill·R9 carry 가 비공개 SKILL 을
            # 정당하게 해석해야 하므로 차단은 이 force 경계에서만 한다.
            skills = [
                s for s in skill_registry.get_by_names(force_skills) if s.meta.expose
            ]
        else:
            skills = skill_registry.select(
                user_message, available_tools=registry.names()
            )
            # ask_user 등으로 끊겼던 작업의 SKILL 지침을 마저 들고 간다. pending 이
            # 살아있는 동안만 — 영구 sticky 가 아니라 다음 턴 pending 해소 시 자동
            # 종료한다(R5/F11 공격적 클리어 철학 유지). 캐리된 SKILL 은 skills 리스트를
            # 타고 그대로 compose 의 '# Skill:' 본문 주입을 받으므로 composer 무변경.
            if has_pending(state) and state.active_skills:
                carried = skill_registry.get_by_names(state.active_skills)
                seen = {s.meta.name for s in skills}
                skills.extend(s for s in carried if s.meta.name not in seen)
        state.active_skills = [s.meta.name for s in skills]

        has_agents = agent_registry is not None and len(agent_registry.list_meta()) > 0

        # 사용자가 SettingsModal 에서 작성한 추가 지침은 PROMPTS/ 합성 결과 뒤에 한 번만
        # 덧붙인다. orchestrator 보다 뒤에 오지만 LLM 은 prompt 전체를 한 번에 학습하므로
        # 라우팅 규칙이 사용자 지침에 의해 가려지지 않는다.
        cleaned_user_prompt = user_prompt.strip()
        user_prompt_section = (
            f"\n\n# 사용자 지침\n{cleaned_user_prompt}" if cleaned_user_prompt else ""
        )
        # activate_skill 이 SKILL 을 켜면 system prompt 를 동적 재조립하는 클로저.
        _recompose = _make_system_prompt_composer(
            has_agents=has_agents,
            prompt_registry=prompt_registry,
            agent_registry=agent_registry,
            skill_registry=skill_registry,
            state=state,
            user_prompt_section=user_prompt_section,
            baseline_api_refs=baseline_api_refs,
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

        orchestrator_specs = _build_orchestrator_specs(
            registry, skills, has_agents=has_agents
        )

        trace.record(
            "turn_start",
            user_message=user_message,
            active_skills=state.active_skills,
            has_agents=has_agents,
            tools=[s.name for s in orchestrator_specs],
        )

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
            clear_all_pending(state)

        dropped = store.append(client_id, *turn_messages)
        turn_persisted = True
        # summarize-then-drop: 슬라이딩 윈도우가 버린 턴을 요약해 보존(망각 방지).
        # happy path 전용 — 예외 경로(_persist_failed_turn)엔 LLM 콜을 추가하지 않는다.
        if COMPACTION_ENABLED and dropped:
            state.progress_summary = await _compact_history(
                provider, state.progress_summary, dropped
            )
        state_store.set(client_id, state)
        trace.record("turn_end", message_count=len(turn_messages))
        yield DoneEvent()

    except Exception as exc:  # noqa: BLE001 — 사용자에게 에러 이벤트로 변환해 전달
        logger.exception("harness run_turn failed")
        trace.record("turn_error", error_type=type(exc).__name__)
        _persist_failed_turn(
            client_id=client_id,
            turn_messages=turn_messages,
            state=state,
            store=store,
            state_store=state_store,
            turn_persisted=turn_persisted,
        )
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
    provider: LLMProvider,
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

    각 iteration 은 한 번의 provider 라운드를 돌려(delta/tool_call 수집), tool_call 이
    있으면 ``_handle_tool_call`` 에 단건씩 위임한다. 핸들러는 이벤트를 즉시 yield 하고
    ``CallOutcome`` 으로 제어 흐름을(CONTINUE / interrupted / stop) 보고한다.

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
    # sub-agent context(turn_messages=None)에서는 agent_registry 가 None 이어야 한다.
    # 이 불변식은 중첩 sub-agent dispatch 를 막는 보안 방어선(L0)이라, -O/optimize 빌드에서
    # 떨어져 나가는 assert 대신 명시적 raise 로 못박는다.
    if turn_messages is None and agent_registry is not None:
        raise RuntimeError(
            "_run_agent_turn: sub-agent context(turn_messages=None)에서 "
            "agent_registry 가 None 이 아님 — 중첩 sub-agent dispatch 가 열릴 수 있습니다. "
            "_dispatch_sub_agent 가 agent_registry=None 으로 호출하는지 확인하세요."
        )

    ctx = TurnContext(
        agent_id=agent_id,
        provider=provider,
        registry=registry,
        agent_registry=agent_registry,
        prompt_registry=prompt_registry,
        skill_registry=skill_registry,
        budget=budget,
        depth=depth,
        max_iterations=max_iterations,
        state=state,
        active_skills=active_skills,
        recompose_system=recompose_system,
        messages=messages,
        turn_messages=turn_messages,
        history_calls=set(),
    )

    assistant_buffer: list[str] = []
    pending_tool_calls: list[ToolCall] = []
    wind_down_notified = False

    for iteration in range(max_iterations):
        with trace.scope(agent_id=agent_id, depth=depth, iteration=iteration):
            wind_down_notified = _maybe_inject_wind_down(
                ctx, iteration, wind_down_notified
            )

            if not budget.try_consume():
                trace.record("budget_exhausted", max_calls=budget.max_calls)
                yield ErrorEvent(
                    message=f"[budget] {agent_id}: provider 호출 상한({budget.max_calls}) 초과"
                )
                return

            assistant_buffer.clear()
            pending_tool_calls.clear()

            async for event in provider.astream(messages, sub_specs):
                match event.type:
                    case "delta":
                        assistant_buffer.append(event.content)
                        yield event
                    case "tool_call":
                        pending_tool_calls.append(event.call)
                        yield event
                    case "reasoning":
                        yield event
                    case "done":
                        break
                    case _:
                        yield event
                        return

            assistant_text = "".join(assistant_buffer)

            if not pending_tool_calls:
                if assistant_text and turn_messages is not None:
                    turn_messages.append(
                        Message(role="assistant", content=assistant_text)
                    )
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
                outcome = CallOutcome()
                async for ev in _handle_tool_call(ctx, call, outcome):
                    yield ev
                if outcome.stop:
                    # complete_subagent — 즉시 종료 (남은 호출 무시, 보정 없음).
                    return
                if outcome.interrupted:
                    interrupted = True
                    break

            if interrupted:
                # 배치 도구 호출 중간에 중단되면 뒤따르는 tool_call 이 응답 없이 남는다.
                # 모든 tool_call 에 placeholder 응답을 채워 메시지 정합성(OpenAI 규약)을 지킨다.
                _balance_unresolved_tool_calls(messages, turn_messages, assistant_msg)
                return
    else:
        async for ev in _emit_max_iterations_fallback(ctx):
            yield ev
