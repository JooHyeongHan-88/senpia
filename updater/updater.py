"""self-replace 부트스트랩.

usage: updater.exe <pid> <new_exe> <current_exe>

1. pid 프로세스가 종료될 때까지 대기.
2. new_exe → current_exe 로 교체.
3. current_exe 기동 후 자기 자신 종료.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


LOG_PATH = Path(os.environ.get("TEMP", ".")) / "app-updater.log"
WAIT_TIMEOUT = 60.0
WAIT_INTERVAL = 0.25
# Windows 는 방금 종료된 EXE 의 이미지 섹션을 즉시 해제하지 않거나 AV 가 파일을
# 스캔하는 동안 핸들을 유지한다. 여유를 충분히 준다.
POST_EXIT_GRACE = 3.0
REPLACE_RETRY = 30
REPLACE_RETRY_INTERVAL = 0.5
# .old 백업 삭제는 옛 EXE 이미지/AV 잠금이 풀린 뒤에야 성공한다. 스왑 직후 한 번만
# 시도하면 실패해 .old 가 잔존하므로, 잠금이 풀릴 때까지 넉넉히 재시도한다.
BACKUP_DELETE_RETRY = 20
BACKUP_DELETE_INTERVAL = 0.5


def log(msg: str) -> None:
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        SYNCHRONIZE = 0x00100000
        STILL_ACTIVE = 259

        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE | 0x0400, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong(0)
            ok = ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            )
            if not ok:
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_for_exit(pid: int) -> bool:
    deadline = time.time() + WAIT_TIMEOUT

    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(WAIT_INTERVAL)

    return False


def replace(new_exe: Path, current_exe: Path) -> bool:
    """new_exe 를 current_exe 위치로 교체한다.

    os.replace(new, old) 는 Windows 에서 ERROR_ACCESS_DENIED 로 실패할 수 있다:
    - 방금 종료된 EXE 의 이미지 섹션이 아직 해제되지 않은 짧은 시간
    - AV/EDR 이 새로 다운로드된 EXE 를 스캔하며 파일 핸들을 보유하는 시간

    rename-to-backup 전략이 이를 우회한다:
      1. current_exe → current_exe.old  (rename — 이름 변경은 잠긴 파일에도 동작)
      2. new_exe     → current_exe      (rename — 목적지가 비어 있으므로 항상 성공)

    .old 백업 정리는 잠금이 풀린 뒤에야 안정적으로 가능하므로 여기서 하지 않고
    스왑·spawn 이후 cleanup_backup 에서 재시도 삭제한다.
    """
    backup = current_exe.with_suffix(".old")
    last_err: Exception | None = None

    for attempt in range(REPLACE_RETRY):
        try:
            # 이전 실패 시 남은 .old 파일 제거.
            try:
                backup.unlink()
            except FileNotFoundError:
                pass

            # 1단계: 기존 EXE 를 .old 로 치운다.
            # Windows 는 실행 직후 종료된 EXE 의 rename 을 허용한다.
            current_exe.rename(backup)

            # 2단계: 새 EXE 를 원래 이름으로 이동. 목적지가 없으므로 반드시 성공.
            try:
                new_exe.rename(current_exe)
            except OSError as e:
                # 예외 상황: backup 을 원위치로 복원해 앱이 재실행 가능하도록 유지.
                try:
                    backup.rename(current_exe)
                except OSError:
                    pass
                raise e

            return True

        except OSError as e:
            last_err = e
            time.sleep(REPLACE_RETRY_INTERVAL)

    log(f"replace failed after {REPLACE_RETRY} attempts: {last_err}")
    return False


def cleanup_backup(current_exe: Path) -> bool:
    """스왑으로 생긴 {stem}.old 백업을 잠금이 풀릴 때까지 재시도 삭제한다.

    스왑 직후 옛 EXE 이미지가 Windows/AV 에 잠겨 단발 삭제는 실패하므로(.old 잔존),
    spawn 이후 시점에 재시도한다. 이미 없으면 성공으로 간주한다.

    Args:
        current_exe (Path): 교체 완료된 현재 EXE 경로. 형제 {stem}.old 가 대상.

    Returns:
        bool: 삭제 성공(또는 애초에 없음) 시 True, 끝까지 실패 시 False.
    """
    backup = current_exe.with_suffix(".old")

    for attempt in range(BACKUP_DELETE_RETRY):
        try:
            backup.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError as e:
            last_err = e
            time.sleep(BACKUP_DELETE_INTERVAL)

    log(f"cleanup_backup failed after {BACKUP_DELETE_RETRY} attempts: {last_err}")
    return False


def notify_shell(folder: Path) -> None:
    """Windows 탐색기에 폴더 갱신을 알려 stale 한 파일 뷰를 강제 새로고침한다.

    빠른 연속 rename/삭제에 대해 탐색기가 shell-change 알림을 놓쳐 옛 이름(.old)을
    캐시에 남기는 문제를 우회한다(수동 F5 없이 정상 표시).
    """
    if sys.platform != "win32":
        return

    try:
        import ctypes

        SHCNE_UPDATEDIR = 0x00001000
        SHCNF_PATHW = 0x0005
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_UPDATEDIR, SHCNF_PATHW, ctypes.c_wchar_p(str(folder)), None
        )
    except Exception as e:
        log(f"notify_shell failed: {e}")


def spawn(current_exe: Path) -> None:
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200

    flags = 0
    if sys.platform == "win32":
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [str(current_exe)],
        creationflags=flags,
        close_fds=True,
        cwd=str(current_exe.parent),
    )


def main() -> int:
    if len(sys.argv) != 4:
        log(f"invalid args: {sys.argv}")
        return 2

    try:
        pid = int(sys.argv[1])
    except ValueError:
        log(f"invalid pid: {sys.argv[1]}")
        return 2

    new_exe = Path(sys.argv[2])
    current_exe = Path(sys.argv[3])

    log(f"start: pid={pid} new={new_exe} current={current_exe}")

    if not new_exe.is_file():
        log("new exe missing")
        return 3

    if not wait_for_exit(pid):
        log("timed out waiting for pid exit")
        return 4

    time.sleep(POST_EXIT_GRACE)

    if not replace(new_exe, current_exe):
        return 5

    log("replaced successfully, spawning")

    try:
        spawn(current_exe)
    except Exception as e:
        log(f"spawn failed: {e}")
        return 6

    # 새 EXE 를 먼저 띄운 뒤(빠른 재시작) .old 를 정리한다 — 이 시점이면 옛 EXE 잠금이
    # 풀려 삭제가 안정적으로 성공하고, 탐색기도 강제 새로고침으로 정상 표시된다.
    cleanup_backup(current_exe)
    notify_shell(current_exe.parent)

    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
