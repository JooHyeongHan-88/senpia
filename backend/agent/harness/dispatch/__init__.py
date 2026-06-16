"""서브 에이전트 디스패치 — 오케스트레이터의 위임 실행 묶음.

``_run_agent_turn`` 의 tool_call 분기가 호출하는, 서브 에이전트 위임 관련 로직을
책임별 모듈로 나눈다 (구 ``harness/core.py`` 의 디스패치 섹션 분해).

- ``sequential``: ``_dispatch_sub_agent`` — 단일 서브 에이전트 순차 위임.
- ``parallel``: ``_dispatch_parallel_sub_agents`` — 독립 작업 동시 실행 fan-in.
- ``spec_filter``: 서브 에이전트에 노출할 도구 스펙 선별 + 런타임 도구 주입.
- ``result_format``: AgentReturnEvent → 오케스트레이터 컨텍스트용 구조화 텍스트.
"""
