"""Sub-agent 위임 · 종료 sentinel 도구.

call_sub_agent  — 오케스트레이터가 서브 에이전트에게 작업을 위임한다.
complete_subagent — 서브 에이전트가 작업을 마쳤을 때 결과를 오케스트레이터에 반환한다.

두 도구 모두 harness 가 tool_call 단계에서 직접 처리하므로 함수 본문은 실행되지 않는다.
"""

from typing import Annotated

from agent.registries.tools import (
    COMPLETE_SUB_AGENT,
    SUB_AGENT_DISPATCH,
    register_tool,
)


@register_tool(
    name=SUB_AGENT_DISPATCH,
    description=(
        "특정 서브 에이전트에게 작업을 위임한다. agent_name 은 가용 서브 에이전트 "
        "카탈로그에 등록된 에이전트 식별자, task 는 그 에이전트가 수행할 한국어 "
        "작업 지시문 한 단락이다. 호출 즉시 서브 에이전트 turn 이 자동 실행되고 "
        "결과 요약본이 tool_result 로 반환된다."
    ),
    slot_prompts={
        "agent_name": "어느 서브 에이전트에게 작업을 맡길까요?",
        "task": "에이전트가 수행할 작업을 한 문단으로 알려 주세요.",
    },
    sentinel=True,
)
async def call_sub_agent(
    agent_name: Annotated[str, "위임할 서브 에이전트 식별자 (예: coding_agent)"],
    task: Annotated[str, "에이전트가 수행할 작업 지시문 (한국어 한 단락)"],
) -> str:
    raise RuntimeError("sentinel tool — handled by harness, never executed")


@register_tool(
    name=COMPLETE_SUB_AGENT,
    description=(
        "서브 에이전트가 맡은 작업을 완료했을 때 호출한다. summary 에 수행 결과와 "
        "핵심 발견 사항을 1~3문장으로 기술한다. 이 도구를 호출해야만 오케스트레이터가 "
        "결과를 인식하므로 작업 완료 시 반드시 마지막으로 호출해야 한다."
    ),
    slot_prompts={
        "summary": "수행한 작업과 결과를 1~3문장으로 요약해 주세요.",
    },
    sentinel=True,
)
async def complete_subagent(
    summary: Annotated[
        str, "수행한 작업 결과 요약 (오케스트레이터에 tool_result 로 전달됨)"
    ],
) -> str:
    raise RuntimeError("sentinel tool — handled by harness, never executed")
