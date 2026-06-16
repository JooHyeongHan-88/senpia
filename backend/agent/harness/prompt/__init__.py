"""Harness 의 LLM 컨텍스트(system prompt) 조립 — 책임별 모듈 묶음.

``run_turn`` 이 매 턴 동적으로 합성하는 system prompt 의 텍스트 섹션과 composer 들을
담는다 (구 ``harness/prompts.py`` 분해). 모두 입력 → 문자열 순수 함수라 turn 실행
루프(``harness/loop.py``)와 분리해도 부수효과가 없다.

- ``compose``: 오케스트레이터 / 서브 에이전트 / 단층 fallback 의 최종 조립.
- ``sections``: 공통 섹션 렌더러 (비활성 SKILL 카탈로그·멀티스킬·To-do·Pending Slot).
- ``artifacts``: Session Artifacts 섹션 (디스크 manifest 기반).
- ``api_refs``: 활성 SKILL·에이전트의 api_refs → ApiDoc 섹션.
- ``wind_down``: 반복 예산 임박 마무리 지시문 (R7).
"""
