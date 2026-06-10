"""턴 시작 시 terminal todo 리셋 — 완료된 plan 이 다음 턴에 누적되지 않는다.

이전 턴의 todo 가 전부 terminal(completed/failed/skipped)이면 새 턴은 빈 plan 으로
시작해야 한다. 리셋이 없으면 add_todo 누적분이 새 메시지의 '작업 진행' 패널에
그대로 재표시되고 '# 현재 To-do' 시스템 프롬프트 섹션을 매 턴 오염시킨다.
비-terminal todo 는 턴 경계를 넘는 plan(AskUser 연속 흐름)이므로 보존된다.
"""

from __future__ import annotations

from agent import harness
from agent.models import (
    AgentState,
    DeltaEvent,
    DoneEvent,
    TodoItem,
    TodoStatus,
    TodoUpdateEvent,
)
from agent.registries.agents import registry as agent_registry
from agent.registries.prompts import registry as prompt_registry
from agent.registries.skills import registry as skill_registry
from agent.registries.tools import registry
from agent.stores.conversation import ConversationStore


class _MemStateStore:
    """AgentStateStore 의 인메모리 대체 — 디스크 flush 없이 동일 인터페이스."""

    def __init__(self) -> None:
        self.states: dict[str, AgentState] = {}

    def get(self, client_id: str) -> AgentState:
        return self.states.setdefault(client_id, AgentState())

    def set(self, client_id: str, state: AgentState) -> None:
        self.states[client_id] = state

    def reset(self, client_id: str) -> None:
        self.states.pop(client_id, None)


class _TextOnlyProvider:
    """도구 호출 없이 텍스트만 응답하는 provider — 턴 경계 동작 검증용."""

    async def astream(self, messages, tools):  # noqa: ANN001
        yield DeltaEvent(content="네, 진행하겠습니다.")
        yield DoneEvent()


def _todo(task_id: str, status: TodoStatus) -> TodoItem:
    return TodoItem(task_id=task_id, description=f"작업 {task_id}", status=status)


async def _run_simple_turn(client_id: str, state_store: _MemStateStore) -> list:
    agent_registry.load()
    skill_registry.load()
    store = ConversationStore(max_history=40)
    return [
        ev
        async for ev in harness.run_turn(
            client_id,
            "다음 작업을 진행해줘",
            store=store,
            state_store=state_store,
            skill_registry=skill_registry,
            prompt_registry=prompt_registry,
            registry=registry,
            agent_registry=agent_registry,
            provider=_TextOnlyProvider(),
            max_iterations=3,
            max_agent_calls=5,
        )
    ]


async def test_all_terminal_todos_cleared_at_turn_start() -> None:
    state_store = _MemStateStore()
    state_store.set(
        "todo-reset-1",
        AgentState(
            todo_list=[
                _todo("t1", TodoStatus.COMPLETED),
                _todo("t2", TodoStatus.FAILED),
                _todo("t3", TodoStatus.SKIPPED),
            ]
        ),
    )

    events = await _run_simple_turn("todo-reset-1", state_store)

    stale_updates = [e for e in events if isinstance(e, TodoUpdateEvent)]
    assert not stale_updates, "리셋 후 stale TodoUpdateEvent 가 발화됨"
    assert state_store.get("todo-reset-1").todo_list == []


async def test_pending_todo_survives_turn_start() -> None:
    state_store = _MemStateStore()
    state_store.set(
        "todo-reset-2",
        AgentState(
            todo_list=[
                _todo("t1", TodoStatus.COMPLETED),
                _todo("t2", TodoStatus.PENDING),
            ]
        ),
    )

    events = await _run_simple_turn("todo-reset-2", state_store)

    updates = [e for e in events if isinstance(e, TodoUpdateEvent)]
    assert updates, "미완료 plan 은 새 턴에서도 표시되어야 함"
    assert any(t.task_id == "t2" for t in updates[0].todos)
    remaining = state_store.get("todo-reset-2").todo_list
    assert [t.task_id for t in remaining] == ["t1", "t2"]
