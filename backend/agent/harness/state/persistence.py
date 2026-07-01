"""run_turn 예외 경로의 best-effort 턴 영속 (R1).

실패한 턴도 영속한다 — 사용자 메시지까지 증발하면 다음 턴 LLM 컨텍스트가 끊긴다.
미해결 tool_call 쌍은 영속 전에 보정(``_balance_all_unresolved``, OpenAI 400 방지)하고,
mid-mutation pending 은 F11 과 동일하게 클리어한다. 영속 실패가 호출부의 에러 알림
(ErrorEvent/DoneEvent)을 막으면 안 되므로 모든 예외를 내부에서 삼킨다.

구 ``harness/loop.py`` 의 실패 턴 영속 헬퍼를 그대로 옮겨왔다 — 영속 협력자
(``balancing._balance_all_unresolved``·``pending.clear_all_pending``)와 같은 ``state/``
서브패키지에 두어 응집도를 높인다.
"""

import logging

from agent.models import AgentState, Message
from agent.stores.agent_state import AgentStateStore
from agent.stores.conversation import ConversationStore

from agent.harness.state.balancing import _balance_all_unresolved
from agent.harness.state.pending import clear_all_pending

logger = logging.getLogger(__name__)


def _persist_failed_turn(
    *,
    client_id: str,
    turn_messages: list[Message],
    state: AgentState,
    store: ConversationStore,
    state_store: AgentStateStore,
    turn_persisted: bool,
) -> None:
    """run_turn 예외 경로의 best-effort 영속 (R1).

    실패한 턴도 영속한다 — 사용자 메시지까지 증발하면 다음 턴 LLM 컨텍스트가
    끊긴다. 미해결 tool_call 쌍은 영속 전에 보정(OpenAI 400 방지)하고, mid-mutation
    pending 은 F11 과 동일하게 클리어한다. 영속 실패가 호출부의 에러 알림
    (ErrorEvent/DoneEvent)을 막으면 안 되므로 모든 예외를 내부에서 삼킨다.

    Args:
        turn_persisted: 성공 경로 append 가 이미 끝났으면 True — 중복 영속 방지.
    """
    try:
        clear_all_pending(state)
        if not turn_persisted:
            _balance_all_unresolved(turn_messages)
            store.append(client_id, *turn_messages)
        state_store.set(client_id, state)
    except Exception:  # noqa: BLE001 — 영속은 best-effort, 이중 실패는 로그만
        logger.exception("run_turn 실패 턴 영속 중 추가 오류 (best-effort 포기)")
