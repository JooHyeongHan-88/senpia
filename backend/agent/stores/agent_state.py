"""client_id 별 AgentState 디스크 영속 저장소.

ConversationStore 와 분리해 두는 이유:
    - 메시지는 히스토리 트리밍 대상이지만 todo / pending_slot 은 진행 상태라 잘리면 안 됨.
    - 슬롯 답변 흐름이 EXE 재기동을 건너서도 이어져야 함.

쓰기 전략:
    매 set/reset 마다 전체 JSON 을 *.tmp 로 작성한 뒤 os.replace 로 원자 교체.
    클라이언트 수가 적고 상태도 작아 단순성 우선. 부하가 커지면 partial-write 로
    전환하면 됨.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

from pydantic import ValidationError

from agent.models import AgentState

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE = 86400  # 24시간


class AgentStateStore:
    def __init__(self, file_path: Path) -> None:
        self._lock = threading.Lock()
        self._file = file_path
        self._cache: dict[str, AgentState] = {}
        self._last_access: dict[str, float] = {}
        self._load()

    def get(self, client_id: str) -> AgentState:
        """현재 상태의 deep copy. 호출자가 자유롭게 수정해도 캐시는 흔들리지 않음."""
        with self._lock:
            self._last_access[client_id] = time.time()
            state = self._cache.get(client_id)
            if state is None:
                return AgentState()
            return state.model_copy(deep=True)

    def set(self, client_id: str, state: AgentState) -> None:
        """상태를 저장하고 디스크에 원자적으로 flush 한다."""
        with self._lock:
            self._last_access[client_id] = time.time()
            self._cache[client_id] = state.model_copy(deep=True)
            self._flush()

    def reset(self, client_id: str) -> None:
        """특정 클라이언트 상태를 제거하고 디스크에 반영한다."""
        with self._lock:
            self._last_access.pop(client_id, None)
            if self._cache.pop(client_id, None) is not None:
                self._flush()

    def evict_stale(self, max_age_seconds: int = _DEFAULT_MAX_AGE) -> int:
        """마지막 접근 후 max_age_seconds 를 초과한 클라이언트 상태를 제거한다.

        EXE 재기동 시 1회 호출해 장기 미사용 클라이언트가 파일을 불필요하게
        키우는 것을 막는다.

        Args:
            max_age_seconds: 이 시간(초) 이상 접근이 없으면 제거. 기본값 86400(24h).

        Returns:
            제거된 클라이언트 수.
        """
        now = time.time()
        stale_ids = [
            cid for cid, ts in self._last_access.items() if now - ts > max_age_seconds
        ]
        if not stale_ids:
            return 0
        with self._lock:
            for cid in stale_ids:
                self._cache.pop(cid, None)
                self._last_access.pop(cid, None)
            self._flush()
        logger.info("evicted %d stale agent state(s)", len(stale_ids))
        return len(stale_ids)

    # ------------------------------------------------------------------ #
    # 디스크 IO
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
            self._cache = {
                cid: AgentState.model_validate(payload) for cid, payload in raw.items()
            }
            # 파일 mtime 을 모든 키의 보수적 초기 접근 시각으로 사용한다.
            # 실제 마지막 접근 시각보다 이를 수 있으나, evict_stale 오탐을 막는
            # 안전한 기본값이다.
            file_mtime = self._file.stat().st_mtime
            for cid in self._cache:
                self._last_access[cid] = file_mtime
            logger.info(
                "agent_states loaded: %d clients from %s", len(self._cache), self._file
            )
        except (json.JSONDecodeError, ValidationError, OSError) as exc:
            # 손상된 파일은 사용자 동작을 막지 않고 빈 상태로 폴백.
            logger.warning("agent_states load failed (%s) — starting empty", exc)
            self._cache = {}

    def _flush(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        payload = {cid: state.model_dump() for cid, state in self._cache.items()}
        tmp = self._file.with_suffix(self._file.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self._file)
