"""병렬 서브 에이전트 디스패치 검증.

call_sub_agents_parallel 경로:
    - 이벤트 fan-in 병합 + dispatch_id 상관키 (같은 이름 동시 실행 포함)
    - 단일 통합 tool_result (call ↔ tool_result 1:1 쌍 유지)
    - ask_user → abort 변환 (사용자 미개입, orchestrator pending 미설정)
    - 동시성 상한(semaphore) · 예산 소진 안전 처리
"""

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.models import (  # noqa: E402
    AgentReturnEvent,
    AgentState,
    AgentSwitchEvent,
    AskUserEvent,
    DeltaEvent,
    DoneEvent,
    Message,
    StreamEvent,
    ToolCall,
    ToolCallEvent,
    ToolResultEvent,
)
from agent.registries.agents import Agent, AgentMeta  # noqa: E402
from agent.registries.tools import (  # noqa: E402
    SUB_AGENTS_PARALLEL_DISPATCH,
    ToolRegistry,
)
from tests._runner import run_tests  # noqa: E402

_SUB_MARKER = "당신은 '"
_PARALLEL_CALL_ID = "par-call-1"


# ---------------------------------------------------------------------------
# 테스트 더블 — fake registry / provider
# ---------------------------------------------------------------------------


def _reload_all_tool_modules() -> None:
    """@register_tool 데코레이터를 재실행해 (테스트가 비운) registry 를 복구한다."""
    import importlib

    import agent.tools.artifact
    import agent.tools.builtin
    import agent.tools.clarify
    import agent.tools.dispatch
    import agent.tools.planner
    import agent.tools.visualize

    for mod in (
        agent.tools.builtin,
        agent.tools.clarify,
        agent.tools.dispatch,
        agent.tools.planner,
        agent.tools.visualize,
        agent.tools.artifact,
    ):
        importlib.reload(mod)


class _FakeAgentRegistry:
    """어떤 이름이든 동일한 경량 Agent 를 돌려주는 카탈로그 더블."""

    def get_by_name(self, name: str) -> Agent | None:
        if not name:
            return None
        return Agent(
            meta=AgentMeta(name=name, description="t", skills=[], tools=[]),
            source_path="x.md",
            body="페르소나",
        )

    def _ensure_body(self, agent: Agent) -> Agent:
        return agent

    def list_meta(self) -> list[AgentMeta]:
        return []


class _FakeSkillRegistry:
    def get_by_names(self, names: list[str]) -> list:
        return []

    def select(self, *args: Any, **kwargs: Any) -> list:
        return []

    def list_meta(self) -> list:
        return []


class _FakePromptRegistry:
    def compose(self, **kwargs: Any) -> str:
        return "BASE"


def _sub_agent_name(messages: list[Message]) -> str | None:
    if not messages or messages[0].role != "system":
        return None
    txt = messages[0].content
    pos = txt.find(_SUB_MARKER)
    if pos == -1:
        return None
    start = pos + len(_SUB_MARKER)
    end = txt.find("'", start)
    return txt[start:end] if end != -1 else None


class _ParallelProvider:
    """병렬 경로용 결정론 가짜 provider.

    sub-context (system 에 서브 에이전트 marker): sub_mode 에 따라 즉시 종료.
        - "complete": complete_subagent(summary) 호출
        - "ask_user": ask_user 호출 (병렬에선 abort 로 흡수돼야 함)
    orchestrator-context: 1턴=call_sub_agents_parallel, 2턴(tool 결과 존재)=최종 텍스트.
    """

    def __init__(self, tasks: list[dict] | None = None, sub_mode: str = "complete"):
        self.tasks = tasks or []
        self.sub_mode = sub_mode

    async def astream(self, messages, tools):  # noqa: ANN001
        name = _sub_agent_name(messages)
        if name is not None:
            if self.sub_mode == "ask_user":
                yield ToolCallEvent(
                    call=ToolCall(
                        id=f"ask-{uuid.uuid4().hex[:8]}",
                        name="ask_user",
                        arguments={
                            "question": "어느 기간을 분석할까요?",
                            "options": ["오늘", "이번주"],
                            "input_type": "both",
                        },
                    )
                )
                yield DoneEvent()
                return
            yield ToolCallEvent(
                call=ToolCall(
                    id=f"done-{uuid.uuid4().hex[:8]}",
                    name="complete_subagent",
                    arguments={"summary": f"{name} 작업 완료"},
                )
            )
            yield DoneEvent()
            return

        # orchestrator context.
        if any(m.role == "tool" for m in messages):
            for ch in "병렬 작업 완료":
                yield DeltaEvent(content=ch)
            yield DoneEvent()
            return

        yield ToolCallEvent(
            call=ToolCall(
                id=_PARALLEL_CALL_ID,
                name=SUB_AGENTS_PARALLEL_DISPATCH,
                arguments={"tasks": self.tasks},
            )
        )
        yield DoneEvent()


# ---------------------------------------------------------------------------
# 실행 헬퍼
# ---------------------------------------------------------------------------


def _collect(agen) -> list[StreamEvent]:  # noqa: ANN001
    async def _run() -> list[StreamEvent]:
        return [ev async for ev in agen]

    return asyncio.run(_run())


def _run_full(
    tasks: list[dict], *, sub_mode: str = "complete"
) -> tuple[list[StreamEvent], list[Message]]:
    """orchestrator _run_agent_turn 전체를 가짜 provider 로 구동한다."""
    _reload_all_tool_modules()
    from agent.harness import TurnBudget, _run_agent_turn

    registry = ToolRegistry()
    turn_messages: list[Message] = []

    async def _go() -> list[StreamEvent]:
        events: list[StreamEvent] = []
        async for ev in _run_agent_turn(
            agent_id="orchestrator",
            messages=[Message(role="user", content="go")],
            turn_messages=turn_messages,
            provider=_ParallelProvider(tasks=tasks, sub_mode=sub_mode),
            registry=registry,
            sub_specs=registry.specs(),
            agent_registry=_FakeAgentRegistry(),
            prompt_registry=_FakePromptRegistry(),
            skill_registry=_FakeSkillRegistry(),
            budget=TurnBudget(max_calls=20),
            depth=0,
            state=AgentState(),
            max_iterations=8,
        ):
            events.append(ev)
        return events

    return asyncio.run(_go()), turn_messages


def _run_dispatch(
    tasks: list[dict],
    *,
    max_parallel: int = 3,
    budget_calls: int = 20,
    sub_mode: str = "complete",
    state: AgentState | None = None,
) -> tuple[list[StreamEvent], dict[str, str]]:
    """_dispatch_parallel_sub_agents 를 직접 구동한다 (세마포어·예산 제어 용이)."""
    _reload_all_tool_modules()
    from agent.harness import TurnBudget, _dispatch_parallel_sub_agents

    registry = ToolRegistry()
    holder: dict[str, str] = {}
    call = ToolCall(
        id=_PARALLEL_CALL_ID,
        name=SUB_AGENTS_PARALLEL_DISPATCH,
        arguments={"tasks": tasks},
    )

    async def _go() -> list[StreamEvent]:
        events: list[StreamEvent] = []
        async for ev in _dispatch_parallel_sub_agents(
            call=call,
            parent_agent_id="orchestrator",
            agent_registry=_FakeAgentRegistry(),
            skill_registry=_FakeSkillRegistry(),
            prompt_registry=_FakePromptRegistry(),
            registry=registry,
            provider=_ParallelProvider(sub_mode=sub_mode),
            budget=TurnBudget(max_calls=budget_calls),
            depth=1,
            max_iterations=8,
            orchestrator_state=state,
            max_parallel=max_parallel,
            result_holder=holder,
        ):
            events.append(ev)
        return events

    return asyncio.run(_go()), holder


# ---------------------------------------------------------------------------
# 병합 · dispatch_id · 단일 tool_result
# ---------------------------------------------------------------------------


def test_two_agents_merge_into_single_tool_result() -> None:
    events, turn_messages = _run_full(
        [
            {"agent_name": "analyst_agent", "task": "분석 A"},
            {"agent_name": "writer_agent", "task": "리포트 B"},
        ]
    )

    switches = [e for e in events if isinstance(e, AgentSwitchEvent)]
    returns = [e for e in events if isinstance(e, AgentReturnEvent)]
    assert len(switches) == 2, "두 task → AgentSwitch 2건이어야 함"
    assert len(returns) == 2, "두 task → AgentReturn 2건이어야 함"

    # dispatch_id 존재 · 상이.
    sw_ids = {s.dispatch_id for s in switches}
    assert None not in sw_ids, "AgentSwitch 에 dispatch_id 가 채워져야 함"
    assert len(sw_ids) == 2, "두 디스패치 id 는 서로 달라야 함"
    assert {r.dispatch_id for r in returns} == sw_ids, "return id 가 switch id 와 일치"

    # 병렬 call 에 대한 ToolResultEvent 는 정확히 1건, 두 요약을 모두 포함.
    parallel_results = [
        e
        for e in events
        if isinstance(e, ToolResultEvent) and e.name == SUB_AGENTS_PARALLEL_DISPATCH
    ]
    assert len(parallel_results) == 1, "병렬 위임은 단일 tool_result 로 합쳐져야 함"
    body = parallel_results[0].result
    assert "analyst_agent" in body and "writer_agent" in body
    assert "병렬 작업 1/2" in body and "병렬 작업 2/2" in body


def test_history_has_exactly_one_tool_message_for_parallel_call() -> None:
    _events, turn_messages = _run_full(
        [
            {"agent_name": "a1", "task": "x"},
            {"agent_name": "a2", "task": "y"},
        ]
    )
    tool_msgs = [
        m
        for m in turn_messages
        if m.role == "tool" and m.tool_call_id == _PARALLEL_CALL_ID
    ]
    assert len(tool_msgs) == 1, "병렬 call.id 에 대응하는 tool 메시지는 정확히 1건"
    # 짝이 되는 assistant tool_calls 도 보존돼야 함 (와이어 규약).
    assistant_with_calls = [
        m for m in turn_messages if m.role == "assistant" and m.tool_calls
    ]
    assert assistant_with_calls, "tool_calls 를 가진 assistant 메시지가 있어야 함"


# ---------------------------------------------------------------------------
# 같은 이름 2개 동시 — dispatch_id 충돌 없음
# ---------------------------------------------------------------------------


def test_same_agent_twice_distinct_dispatch_ids() -> None:
    events, holder = _run_dispatch(
        [
            {"agent_name": "analyst_agent", "task": "샤드 1"},
            {"agent_name": "analyst_agent", "task": "샤드 2"},
        ]
    )
    switches = [e for e in events if isinstance(e, AgentSwitchEvent)]
    returns = [e for e in events if isinstance(e, AgentReturnEvent)]
    assert len(switches) == 2 and len(returns) == 2
    assert len({s.dispatch_id for s in switches}) == 2, (
        "같은 이름이라도 dispatch_id 는 달라야 라우팅 충돌이 없다"
    )
    assert holder["combined"].count("analyst_agent") >= 2


# ---------------------------------------------------------------------------
# ask_user → abort (사용자 미개입)
# ---------------------------------------------------------------------------


def test_ask_user_inside_parallel_is_aborted_not_surfaced() -> None:
    state = AgentState()
    events, holder = _run_dispatch(
        [
            {"agent_name": "analyst_agent", "task": "분석"},
            {"agent_name": "writer_agent", "task": "리포트"},
        ],
        sub_mode="ask_user",
        state=state,
    )

    assert not any(isinstance(e, AskUserEvent) for e in events), (
        "병렬 중 ask_user 는 사용자에게 노출되지 않아야 함"
    )
    returns = [e for e in events if isinstance(e, AgentReturnEvent)]
    assert len(returns) == 2, "abort 도 AgentReturn 으로 트레일을 닫아야 함"
    assert "[중단]" in holder["combined"]
    assert "call_sub_agent" in holder["combined"], "순차 재위임 안내가 포함돼야 함"
    # abort 는 orchestrator pending 을 건드리지 않는다.
    assert state.pending_sub_agent is None
    assert state.pending_sub_task is None


# ---------------------------------------------------------------------------
# 동시성 상한 · 예산
# ---------------------------------------------------------------------------


def test_semaphore_one_still_completes_all() -> None:
    events, holder = _run_dispatch(
        [
            {"agent_name": "a1", "task": "x"},
            {"agent_name": "a2", "task": "y"},
            {"agent_name": "a3", "task": "z"},
        ],
        max_parallel=1,
    )
    returns = [e for e in events if isinstance(e, AgentReturnEvent)]
    assert len(returns) == 3, "semaphore=1 직렬화여도 전원 완료해야 함"
    assert "병렬 작업 3/3" in holder["combined"]


def test_budget_exhaustion_does_not_crash() -> None:
    # max_calls=1 → 첫 서브만 provider 호출 성공, 나머지는 budget ErrorEvent.
    events, holder = _run_dispatch(
        [
            {"agent_name": "a1", "task": "x"},
            {"agent_name": "a2", "task": "y"},
        ],
        budget_calls=1,
    )
    returns = [e for e in events if isinstance(e, AgentReturnEvent)]
    assert len(returns) == 2, "예산 소진이어도 두 트레일 모두 닫혀야 함"
    assert "combined" in holder and holder["combined"]


def test_empty_tasks_yields_error_summary() -> None:
    events, holder = _run_dispatch([])
    assert not any(isinstance(e, AgentSwitchEvent) for e in events)
    assert "error" in holder["combined"].lower()


if __name__ == "__main__":
    run_tests(globals())
