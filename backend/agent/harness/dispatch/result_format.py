"""서브 에이전트 결과 → 오케스트레이터 LLM 컨텍스트용 텍스트 포매팅.

``AgentReturnEvent`` 를 todo 통계가 포함된 구조화 텍스트로 변환하거나, 서브 에이전트
응답에서 'Task Summary:' 헤더 이후를 요약으로 추출한다. 순차·병렬 디스패처와
오케스트레이터 루프가 공유한다.
"""

from agent.models import AgentReturnEvent, TodoStatus

TASK_SUMMARY_HEADER = "Task Summary:"


def _format_sub_agent_result(event: AgentReturnEvent) -> str:
    """AgentReturnEvent 를 오케스트레이터 LLM 컨텍스트용 구조화 텍스트로 변환.

    todo_log 가 있으면 단계별 성공/실패 기록을 포함하고, 없으면 도구 호출 통계만
    추가한다. 오케스트레이터는 이 텍스트를 tool_result 로 받아 Case 5 보고에 활용한다.
    """
    lines: list[str] = [f"[{event.from_agent} 완료] {event.summary}"]

    status_icon: dict[str, str] = {
        TodoStatus.COMPLETED.value: "✓",
        TodoStatus.FAILED.value: "✗",
        TodoStatus.SKIPPED.value: "–",
    }

    if event.todo_log:
        n_completed = sum(1 for t in event.todo_log if t.status == TodoStatus.COMPLETED)
        n_failed = sum(1 for t in event.todo_log if t.status == TodoStatus.FAILED)
        n_skipped = sum(1 for t in event.todo_log if t.status == TodoStatus.SKIPPED)

        stat_parts = [f"완료 {n_completed}"]
        if n_failed:
            stat_parts.append(f"실패 {n_failed}")
        if n_skipped:
            stat_parts.append(f"건너뜀 {n_skipped}")

        lines.append(f"실행 단계: {len(event.todo_log)}개 ({' · '.join(stat_parts)})")
        for item in event.todo_log:
            icon = status_icon.get(item.status.value, "?")
            detail = f": {item.result_summary}" if item.result_summary else ""
            lines.append(f"  [{icon}] {item.description}{detail}")
    elif event.tool_calls_count > 0:
        stat = f"도구 호출: {event.tool_calls_count}건"
        if event.error_count:
            stat += f" (실패 {event.error_count}건)"
        lines.append(stat)

    return "\n".join(lines)


def _extract_task_summary(full_text: str, agent_name: str) -> str:
    """서브 에이전트 응답에서 'Task Summary:' 헤더 이후 텍스트 추출.

    헤더가 없으면 마지막 200자를 폴백 요약으로 사용 — LLM 미준수 방어.
    """
    if not full_text:
        return f"[{agent_name}] (빈 응답)"
    if TASK_SUMMARY_HEADER in full_text:
        return full_text.split(TASK_SUMMARY_HEADER, 1)[1].strip() or f"[{agent_name}]"
    return f"[{agent_name}] {full_text[-200:].strip()}"
