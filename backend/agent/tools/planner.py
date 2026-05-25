"""Planner sentinel 도구 — harness 가 tool_call 분기에서 가로채 직접 처리한다.

`run()` body 는 실행되지 않는다. spec 만 LLM 에게 노출되며, harness 의
`PLANNER_ADD_TODO` / `PLANNER_COMPLETE_TODO` 분기가 AgentState 갱신을 담당한다.
"""

from typing import Annotated, Any

from agent.registries.tools import (
    PLANNER_ADD_TODO,
    PLANNER_COMPLETE_TODO,
    register_tool,
)


@register_tool(
    name=PLANNER_ADD_TODO,
    description=(
        "두 단계 이상이 필요한 작업을 시작할 때 항상 먼저 호출한다. "
        "각 item 은 description(필수)과 tool_name(선택, 사용할 도구 힌트)을 가진다. "
        "호출 즉시 todo_list 에 PENDING 상태로 추가된다."
    ),
    slot_prompts={"items": "어떤 단계들로 작업을 분해하면 좋을까요?"},
    sentinel=True,
)
async def add_todo(
    items: Annotated[
        list[dict[str, Any]],
        "추가할 sub-task 목록. 각 항목: description(필수), tool_name(선택)",
    ],
) -> str:
    raise RuntimeError("sentinel tool — handled by harness, never executed")


@register_tool(
    name=PLANNER_COMPLETE_TODO,
    description=(
        "todo_list 의 한 단계를 처리 완료 표시한다. task_id 는 add_todo 또는 직전 "
        "todo_update 이벤트에서 얻은 식별자를 사용한다. "
        "도구 실행이 실패했거나 단계를 건너뛸 때는 status 를 'failed' 또는 'skipped' 로 지정한다."
    ),
    slot_prompts={"task_id": "어느 단계를 완료 처리하시겠습니까?"},
    sentinel=True,
)
async def complete_todo(
    task_id: Annotated[str, "완료 처리할 단계의 id"],
    summary: Annotated[str, "완료 결과 요약 (한국어 한 줄)"] = "",
    status: Annotated[
        str, "completed | failed | skipped (기본값: completed)"
    ] = "completed",
) -> str:
    raise RuntimeError("sentinel tool — handled by harness, never executed")
