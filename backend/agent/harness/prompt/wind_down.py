"""반복 예산 임박 마무리(wind-down) 지시문 생성 (R7).

실패 없이 진행 중인데 예산만 소진돼 사용자 노출 단계(display_*)가 hard-cut 되는 것을
막는다. ``_run_agent_turn`` 이 남은 호출이 임계 이하로 떨어질 때 messages 에만 1회
주입한다 (히스토리 비영속 — fallback 메시지와 동일 정책).
"""


def _build_wind_down_message(remaining_calls: int) -> str:
    """반복 예산 임박 시 LLM 컨텍스트에 주입할 마무리 지시문을 생성한다 (R7).

    실패 없이 진행 중인데 예산만 소진돼 사용자 노출 단계(display_*)가 hard-cut
    되는 것을 막는다. fallback 메시지와 동일하게 turn-local — 히스토리 비영속.

    Args:
        remaining_calls: 이번 호출을 포함해 남은 provider 호출 수.

    Returns:
        role=user 로 주입할 [System] 지시문.
    """
    if remaining_calls <= 1:
        return (
            "[System] 이번 응답이 이 턴의 마지막 provider 호출입니다. 도구를 호출하지 "
            "말고, 지금까지 완료한 작업과 산출물을 정리한 최종 답변을 작성하세요."
        )
    return (
        f"[System] 이 턴의 반복 예산이 거의 소진되었습니다 (남은 호출 {remaining_calls}회). "
        "새로운 분석·데이터 생성을 시작하지 마세요. 이미 저장된 산출물이 있으면 지금 즉시 "
        "display_chart/display_markdown 등으로 사용자에게 표시하고 complete_todo 로 plan 을 "
        "정리한 뒤, 다음 응답에서 도구 호출 없이 최종 요약을 작성하세요."
    )
