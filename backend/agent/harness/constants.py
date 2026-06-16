"""Turn 루프 레벨 상수 — 식별자·튜닝값·고정 지시문.

``loop`` 과 ``call_handlers`` 가 공유하는 turn 실행 루프 차원의 상수만 모은다.
모듈 고유 로직에 밀착된 상수(``state.todo._TERMINAL_STATUSES``,
``state.loop_guard._LOOP_GUARD_MESSAGE``, ``state.balancing._ERROR_TOOL_PLACEHOLDER``,
``dispatch.result_format.TASK_SUMMARY_HEADER`` 등)는 응집도를 위해 각 거처에 그대로
둔다 — 이곳은 "여러 모듈에 흩어져 있던 루프 차원 상수"의 단일 거처다.
"""

# 오케스트레이터(depth 0) 에이전트 식별자. AgentSwitch/Progress 라벨·로깅에 쓰인다.
ORCHESTRATOR_ID = "orchestrator"

# 남은 provider 호출(반복 상한·turn budget 중 작은 쪽)이 이 수 이하로 떨어지면
# LLM 에 마무리(wind-down)를 지시한다 (R7). 2 = '마지막 도구 실행 1회 + 최종 요약
# 1회' — 이미 저장된 산출물을 display_* 로 사용자에게 노출할 최소 여유.
WIND_DOWN_REMAINING_CALLS = 2

# max_iterations 소진 시 LLM 에 회신하는 마무리 지시문 (F6). 턴-로컬로만 주입하고
# 히스토리에는 영속하지 않는다.
MAX_ITERATIONS_FALLBACK_INSTRUCTION = (
    "[System] 에이전트 반복 상한에 도달했거나 작업이 중단되었습니다. 지금까지 완료한 "
    "작업과 실패한 원인을 정리하여 사용자에게 자연어로 최종 답변을 작성하세요. 도구를 "
    "호출하지 마세요."
)
