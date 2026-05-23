import os
import sys
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# 경로 해석
#
# 빌드 결과물 위치:
#   - dev:     <project_root>/build/web         (Vite outDir)
#              <project_root>/build/updater     (PyInstaller Updater 출력)
#   - frozen:  <MEIPASS>/web                    (App.spec datas 로 임베드)
#              <MEIPASS>/updater                (동, Updater.exe 만 포함)
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]

    return Path(__file__).resolve().parent.parent


if not getattr(sys, "frozen", False):
    load_dotenv(dotenv_path=_project_root() / ".env", override=False)


# ---------------------------------------------------------------------------
# 디렉터리
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    WEB_DIR = _project_root() / "web"
else:
    WEB_DIR = _project_root() / "build" / "web"

ASSETS_DIR = WEB_DIR / "assets"


# ---------------------------------------------------------------------------
# 네트워크 (frontend 와 공유 — .env 로 override 가능)
# ---------------------------------------------------------------------------

HOST = os.environ.get("APP_HOST", "127.0.0.1")
PORT = int(os.environ.get("APP_PORT", "8765"))
ALLOWED_ORIGIN = f"http://{HOST}:{PORT}"


# ---------------------------------------------------------------------------
# browser / watchdog
# ---------------------------------------------------------------------------

# STARTUP_GRACE: 첫 client 연결까지 기다리는 상한.
# 이 시간 동안 한 번도 연결이 없으면 비었다고 판단하지 않고 계속 대기.
STARTUP_GRACE = 60
SHUTDOWN_GRACE = 2

# presence SSE 가 끊겼다가 같은 client_id 로 재연결될 수 있는 시간 (F5/네트워크 블립 흡수).
# 이 시간 안에 다시 붙으면 실제 제거를 취소한다.
PRESENCE_RECONNECT_GRACE = 2

# 서버가 SSE 채널에 `: ping` 코멘트 라인을 흘려보내는 주기.
# 중간 프록시의 idle timeout 으로 끊기지 않도록 유지.
PRESENCE_KEEPALIVE_INTERVAL = 30

# SSE 첫 응답에 실어보내는 `retry:` 디렉티브 — EventSource 재연결 간격(ms).
PRESENCE_RETRY_HINT_MS = 1000


# ---------------------------------------------------------------------------
# update / nexus
# ---------------------------------------------------------------------------

NEXUS_BASE_URL = os.environ.get(
    "APP_NEXUS_BASE_URL",
    "https://nexus.internal/repository/app",
).rstrip("/")
LATEST_JSON_URL = f"{NEXUS_BASE_URL}/latest.json"
UPDATE_CHECK_TIMEOUT = 5
UPDATE_DOWNLOAD_TIMEOUT = 60
UPDATE_CHECK_CACHE_TTL = 300


# ---------------------------------------------------------------------------
# LLM / Agent harness
# ---------------------------------------------------------------------------

# 현재는 "mock" 만 지원. vLLM 연결 시 "vllm" 추가 예정.
LLM_PROVIDER = os.environ.get("APP_LLM_PROVIDER", "mock")
LLM_BASE_URL = os.environ.get("APP_LLM_BASE_URL")
LLM_MODEL = os.environ.get("APP_LLM_MODEL")
LLM_API_KEY = os.environ.get("APP_LLM_API_KEY")

SYSTEM_PROMPT = (
    "You are a helpful AI agent. 한국어 사용자에게는 한국어로 친절히 답한다. "
    "필요하면 등록된 도구를 사용해 정확한 정보를 제공한다."
)

# Agent harness 한 턴에서 허용하는 provider→tool→provider 반복 횟수 상한.
MAX_AGENT_ITERATIONS = 5

# store 가 client 한 명당 보관하는 메시지 수 상한 (system 제외).
MAX_HISTORY_MESSAGES = 40
