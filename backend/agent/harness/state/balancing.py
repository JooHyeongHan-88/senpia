"""대화 히스토리 정합성 — 미해결 tool_call 에 placeholder 응답을 채운다.

OpenAI 와이어 규약상 assistant 의 모든 tool_call 은 매칭되는 tool 메시지가 있어야
한다. 배치 도구 호출 도중 AskUser·예외 등으로 턴이 끊기면 뒤따르는 호출이 응답 없이
남아, 그 메시지가 영속되면 다음 턴 요청이 400 으로 거부된다 (F1b·R1). 구
``harness/state.py`` 의 balancing 섹션을 그대로 옮겨왔다.
"""

from agent.models import Message


def _balance_unresolved_tool_calls(
    messages: list[Message],
    turn_messages: list[Message] | None,
    assistant_msg: Message,
) -> None:
    """중단으로 처리되지 못한 tool_call 에 placeholder tool 응답을 채운다.

    OpenAI 와이어 규약상 assistant 의 모든 tool_call 은 매칭되는 tool 메시지가
    있어야 한다. 배치 도구 호출 도중 AskUser 등으로 턴이 끊기면 뒤따르는 호출이
    응답 없이 남아, 이 메시지가 히스토리에 영속되면 다음 턴 요청이 400 으로
    거부된다. 미해결 tool_call 마다 placeholder 응답을 추가해 쌍을 맞춘다.

    Args:
        messages: LLM 컨텍스트 (in-place 보정).
        turn_messages: 영속화 버퍼. 서브 에이전트는 None.
        assistant_msg: 이번 iteration 의 assistant 메시지 (tool_calls 보유).
    """
    if not assistant_msg.tool_calls:
        return
    resolved = {m.tool_call_id for m in messages if m.role == "tool" and m.tool_call_id}
    for tc in assistant_msg.tool_calls:
        if tc.id in resolved:
            continue
        placeholder = "[중단됨] 사용자 입력 대기로 이 도구 호출은 실행되지 않았습니다."
        tool_msg = Message(role="tool", content=placeholder, tool_call_id=tc.id)
        messages.append(tool_msg)
        if turn_messages is not None:
            turn_messages.append(tool_msg)


_ERROR_TOOL_PLACEHOLDER = (
    "[중단됨] 턴이 오류로 종료되어 이 도구 호출은 완료되지 않았습니다."
)


def _balance_all_unresolved(turn_messages: list[Message]) -> None:
    """버퍼 전체를 스캔해 모든 미해결 tool_call 에 placeholder 응답을 채운다.

    run_turn 최상위 예외 경로 전용. `_balance_unresolved_tool_calls` 와 달리 예외
    시점의 in-flight assistant_msg 를 특정할 수 없으므로 전수 검사한다. placeholder
    는 끝에 append 하지 않고 해당 assistant 의 tool 응답 블록 바로 뒤에 삽입한다 —
    OpenAI 와이어 규약상 tool 메시지는 자신의 assistant 메시지에 인접해야 한다.

    Args:
        turn_messages: 영속화 직전의 턴 버퍼 (in-place 보정).
    """
    i = 0
    while i < len(turn_messages):
        msg = turn_messages[i]
        if msg.role != "assistant" or not msg.tool_calls:
            i += 1
            continue
        # 이 assistant 에 인접한 tool 응답 블록의 끝(j)과 해결된 id 집합을 수집.
        j = i + 1
        resolved: set[str] = set()
        while j < len(turn_messages) and turn_messages[j].role == "tool":
            if turn_messages[j].tool_call_id:
                resolved.add(turn_messages[j].tool_call_id)
            j += 1
        for tc in msg.tool_calls:
            if tc.id in resolved:
                continue
            turn_messages.insert(
                j,
                Message(
                    role="tool",
                    content=_ERROR_TOOL_PLACEHOLDER,
                    tool_call_id=tc.id,
                ),
            )
            j += 1
        i = j
