"""Harness 의 turn 상태 정합성 헬퍼 묶음.

``run_turn`` / ``_run_agent_turn`` 이 사용하는, turn 실행 루프와 분리 가능한
상태 조작 유틸리티를 책임별 모듈로 나눈다 (구 ``harness/state.py`` 분해).

- ``todo``: Planner 도구 핸들러 — add_todo / complete_todo 등으로 AgentState.todo_list 갱신.
- ``balancing``: 대화 히스토리 정합성 — 미해결 tool_call 에 placeholder 응답을 채워
  OpenAI 와이어 규약(모든 tool_call 은 매칭 tool 응답 필요)을 지킨다 (F1b·R1).
- ``loop_guard``: 동일 호출 반복 감지용 호출 시그니처 (R4). 참조 ``result/...`` 파일
  fingerprint 까지 포함한다.
"""
