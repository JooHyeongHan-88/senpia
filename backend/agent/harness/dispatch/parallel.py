"""병렬 서브 에이전트 디스패치 — ``_dispatch_parallel_sub_agents``.

여러 서브 에이전트를 동시에 실행하고 이벤트를 asyncio.Queue 로 fan-in 해 인터리브
yield 한다. 전원 완료 후 입력 순서대로 요약을 합쳐 단일 tool_result 본문으로 채운다
(call ↔ tool_result 1:1 쌍 유지).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from agent.models import AgentReturnEvent, AgentState, StreamEvent, ToolCall
from agent.registries.agents import AgentRegistry
from agent.registries.prompts import PromptRegistry
from agent.registries.skills import SkillRegistry
from agent.registries.tools import SUB_AGENT_DISPATCH, ToolRegistry

from agent.harness.budget import TurnBudget
from agent.harness.dispatch.result_format import _format_sub_agent_result
from agent.harness.dispatch.sequential import _dispatch_sub_agent

logger = logging.getLogger(__name__)


async def _dispatch_parallel_sub_agents(
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
    orchestrator_state: AgentState | None,
    max_parallel: int,
    result_holder: dict[str, str],
) -> AsyncIterator[StreamEvent]:
    """여러 서브 에이전트를 동시에 실행하고 이벤트를 fan-in 으로 병합 yield 한다.

    각 task 는 격리된 `_dispatch_sub_agent` 로 실행되며, ask_user 가 발생하면 그
    작업만 에러 요약으로 종료된다(ask_user_mode="abort"). 전원 완료 후 입력 순서대로
    요약을 합쳐 `result_holder["combined"]` 에 단일 텍스트로 채운다 — 호출부가 이를
    하나의 tool_result 로 사용한다 (call ↔ tool_result 1:1 쌍 유지).

    동시성은 `asyncio.Semaphore(max_parallel)` 로 제한한다. 소비 루프가 취소되면
    (ESC·탭 종료) finally 가 모든 producer task 를 취소·정리해 고아 task 를 남기지 않는다.

    Args:
        call: 원본 call_sub_agents_parallel ToolCall. id 를 dispatch_id prefix 로 쓴다.
        depth: 자식 서브 에이전트가 실행될 깊이 (호출부가 depth+1 을 전달).
        max_parallel: 동시 실행 상한 (APP_MAX_PARALLEL_SUBAGENTS).
        result_holder: 완료 후 'combined' 키에 통합 요약 텍스트를 채울 out-param.
    """
    raw_tasks = (call.arguments or {}).get("tasks") or []
    # guard 를 이미 통과했으므로 dict 리스트로 가정. 방어적으로 dict 만 취한다.
    specs: list[tuple[str, str, str]] = []  # (dispatch_id, agent_name, task)
    for i, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            continue
        agent_name = str(item.get("agent_name", "")).strip()
        task = str(item.get("task", "")).strip()
        specs.append((f"{call.id}::p{i}", agent_name, task))

    if not specs:
        result_holder["combined"] = "[error] 병렬 위임 작업 목록이 비어 있습니다"
        return

    sem = asyncio.Semaphore(max(1, max_parallel))
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    summaries: dict[str, str] = {}

    async def _produce(dispatch_id: str, agent_name: str, task: str) -> None:
        """단일 서브 에이전트를 실행하며 이벤트를 큐로 흘려보낸다."""
        synth_call = ToolCall(
            id=dispatch_id,
            name=SUB_AGENT_DISPATCH,
            arguments={"agent_name": agent_name, "task": task},
        )
        try:
            async with sem:
                async for ev in _dispatch_sub_agent(
                    call=synth_call,
                    parent_agent_id=parent_agent_id,
                    agent_registry=agent_registry,
                    skill_registry=skill_registry,
                    prompt_registry=prompt_registry,
                    registry=registry,
                    provider=provider,
                    budget=budget,
                    depth=depth,
                    max_iterations=max_iterations,
                    orchestrator_state=orchestrator_state,
                    dispatch_id=dispatch_id,
                    ask_user_mode="abort",
                    skip_consecutive_guard=True,
                ):
                    await queue.put(("ev", ev))
                    if isinstance(ev, AgentReturnEvent):
                        summaries[dispatch_id] = _format_sub_agent_result(ev)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — producer 예외를 트레일 요약으로 흡수
            logger.exception("parallel sub-agent producer failed: %s", agent_name)
            summaries[dispatch_id] = f"[error] {agent_name}: {type(exc).__name__}"
        finally:
            await queue.put(("done", dispatch_id))

    tasks = [
        asyncio.create_task(_produce(did, name, task)) for did, name, task in specs
    ]

    try:
        remaining = len(tasks)
        while remaining > 0:
            kind, payload = await queue.get()
            if kind == "ev":
                yield payload
            else:  # "done"
                remaining -= 1
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # 입력(task) 순서대로 요약을 합쳐 단일 tool_result 본문을 구성한다.
    blocks: list[str] = []
    total = len(specs)
    for idx, (did, agent_name, _task) in enumerate(specs, start=1):
        body = summaries.get(did) or f"[{agent_name}] (요약 없음)"
        blocks.append(f"### 병렬 작업 {idx}/{total} — {agent_name}\n{body}")
    result_holder["combined"] = "\n\n".join(blocks)
