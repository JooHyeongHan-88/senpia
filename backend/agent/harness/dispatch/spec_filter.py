"""서브 에이전트에 노출할 도구 스펙 선별 + 런타임 도구 주입.

오케스트레이터/서브 에이전트가 provider 에게 노출하는 ToolSpec 집합을 결정한다.
서브 에이전트는 위임 도구(call_sub_agent 등)를 시야에서 제거하고, api_refs 가 있으면
인프라 런타임 도구를 화이트리스트와 무관하게 자동 노출한다.
"""

from agent.models import ToolSpec
from agent.registries.agents import Agent
from agent.registries.skills import Skill, SkillRegistry
from agent.registries.tools import (
    COMPLETE_SUB_AGENT,
    SUB_AGENT_DISPATCH,
    SUB_AGENTS_PARALLEL_DISPATCH,
    ToolRegistry,
)
from agent.tools.artifact_io import ARTIFACT_IO_TOOL_NAMES
from agent.tools.runtime import INFRASTRUCTURE_TOOL_NAMES


def _skills_require_runtime_tools(skills: list[Skill]) -> bool:
    """활성 SKILL 중 하나라도 api_refs 를 가지면 infrastructure tools 가 필요하다."""
    return any(s.meta.api_refs for s in skills)


def _inject_runtime_tools(
    specs: list[ToolSpec], registry: ToolRegistry
) -> list[ToolSpec]:
    """specs 에 INFRASTRUCTURE_TOOL_NAMES 가 빠져 있으면 추가한다.

    이미 포함된 경우(자동 등록 등)는 중복 추가하지 않는다.
    """
    existing = {s.name for s in specs}
    extra: list[ToolSpec] = []
    for name in INFRASTRUCTURE_TOOL_NAMES:
        if name in existing:
            continue
        rt = registry.get(name)
        if rt is None:
            continue
        extra.append(
            ToolSpec(name=rt.name, description=rt.description, parameters=rt.parameters)
        )
    return specs + extra


def _build_orchestrator_specs(
    registry: ToolRegistry, skills: list[Skill], *, has_agents: bool
) -> list[ToolSpec]:
    """오케스트레이터 provider 에 노출할 도구 스펙을 선별한다.

    COMPLETE_SUB_AGENT 는 서브 에이전트 전용이라 숨기고, AGENTS 가 없으면 위임
    도구(순차·병렬)도 제거한다. infrastructure 메타 도구(call_function 등)는
    registry.specs() 에 항상 포함되므로 오케스트레이터에는 이미 노출돼 있다 —
    `_inject_runtime_tools` 는 누락분 보강용 idempotent 안전망이다(서브 에이전트는
    화이트리스트로 걸러지므로 거기서 실효). 따라서 오케스트레이터에서 baseline
    api_refs 가 추가로 필요로 하는 것은 도구가 아니라 prompt 의 docstring 섹션뿐이다
    (compose 가 담당). 도구 노출은 손대지 않는다.
    """
    delegation_tools = {SUB_AGENT_DISPATCH, SUB_AGENTS_PARALLEL_DISPATCH}
    specs = [
        s
        for s in registry.specs()
        if s.name != COMPLETE_SUB_AGENT
        and (has_agents or s.name not in delegation_tools)
    ]
    if _skills_require_runtime_tools(skills):
        specs = _inject_runtime_tools(specs, registry)
    return specs


def _resolve_agent_skills(agent: Agent, skill_registry: SkillRegistry) -> list[Skill]:
    """agent.meta.skills 의 이름들을 SkillRegistry 에서 lazy load. 미존재는 무시."""
    if not agent.meta.skills:
        return []
    return skill_registry.get_by_names(agent.meta.skills)


def _filter_specs_for_sub_agent(
    all_specs: list[ToolSpec],
    agent: Agent,
    skill_bodies: list[Skill] | None = None,
) -> list[ToolSpec]:
    """서브 에이전트에게 노출할 도구 스펙.

    금지 도구:
        - SUB_AGENT_DISPATCH / SUB_AGENTS_PARALLEL_DISPATCH: 무한 재귀 방지
          (depth-guard 가 2차 안전망). 서브 에이전트는 순차·병렬 위임 모두 금지.
    허용 도구:
        - COMPLETE_SUB_AGENT: 서브 에이전트가 완료 시 반드시 호출해야 함.
        - PLANNER_ADD_TODO / PLANNER_COMPLETE_TODO: 서브 에이전트도 자체 작업을
          분해할 수 있도록 허용. sub_state(로컬) 로 관리되므로 오케스트레이터와 분리.
    화이트리스트:
        - agent.meta.tools 비어 있으면 위 금지 외 전체.
        - 비어있지 않으면 그 화이트리스트만 (단 금지 도구는 항상 제외).

    Infrastructure tools 자동 노출:
        - 에이전트 또는 학습 SKILL 에 api_refs 가 하나라도 있으면 화이트리스트와
          무관하게 INFRASTRUCTURE_TOOL_NAMES 가 specs 에 포함된다. SKILL 본문에
          명시하지 않아도 LLM 이 자체 plan 으로 call_function/eval_expression 등을
          호출 가능. 산출물 체이닝(load_artifact 로 과거 parquet 재사용 등)도
          런타임 작업의 일부이므로 ARTIFACT_IO_TOOL_NAMES 를 함께 포함한다 —
          에이전트 작성자가 화이트리스트에 일일이 적지 않아도 동작.
    """
    forbidden: frozenset[str] = frozenset(
        {SUB_AGENT_DISPATCH, SUB_AGENTS_PARALLEL_DISPATCH}
    )
    allowed = set(agent.meta.tools)

    needs_runtime = bool(agent.meta.api_refs) or (
        skill_bodies is not None and any(s.meta.api_refs for s in skill_bodies)
    )
    if needs_runtime:
        allowed_runtime: set[str] = set(INFRASTRUCTURE_TOOL_NAMES) | set(
            ARTIFACT_IO_TOOL_NAMES
        )
    else:
        allowed_runtime = set()

    out: list[ToolSpec] = []
    for spec in all_specs:
        if spec.name in forbidden:
            continue
        if allowed and spec.name not in allowed and spec.name not in allowed_runtime:
            continue
        out.append(spec)
    return out
