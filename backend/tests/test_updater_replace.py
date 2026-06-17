"""self-replace 파일 연산 검증 — .old 잔존/탐색기 표시 정합 회귀.

- 독립 updater(`updater/updater.py`)의 replace 는 스왑만 하고 .old 를 남긴다
  (정리는 spawn 이후 cleanup_backup 책임).
- cleanup_backup 은 .old 를 재시도 삭제하고, 없으면 무해.
- notify_shell 은 어느 플랫폼에서도 예외 없이 반환(win32 만 실효).
- backend 안전망 cleanup_stale_backup 은 frozen 에서만 형제 .old 를 청소한다.

독립 updater 모듈은 backend 패키지 밖이라 파일 경로로 직접 로드한다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

import core.updater as core_updater

_UPDATER_PATH = Path(__file__).resolve().parents[2] / "updater" / "updater.py"
_spec = importlib.util.spec_from_file_location("standalone_updater", _UPDATER_PATH)
assert _spec is not None and _spec.loader is not None
updater_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(updater_mod)


def test_replace_swaps_and_keeps_backup(tmp_path: Path) -> None:
    """replace 는 new→current 로 바꾸고 .old 백업은 남긴다(정리는 별도 책임)."""
    current = tmp_path / "App.exe"
    new = tmp_path / "App.new.exe"
    current.write_text("old")
    new.write_text("new")

    assert updater_mod.replace(new, current) is True
    assert current.read_text() == "new"
    assert not new.exists()

    backup = current.with_suffix(".old")
    assert backup.exists()
    assert backup.read_text() == "old"


def test_cleanup_backup_deletes_existing(tmp_path: Path) -> None:
    """cleanup_backup 은 스왑이 남긴 .old 를 삭제한다."""
    current = tmp_path / "App.exe"
    current.write_text("new")
    backup = current.with_suffix(".old")
    backup.write_text("old")

    assert updater_mod.cleanup_backup(current) is True
    assert not backup.exists()


def test_cleanup_backup_noop_when_absent(tmp_path: Path) -> None:
    """.old 가 애초에 없으면 성공으로 간주한다."""
    current = tmp_path / "App.exe"
    current.write_text("new")

    assert updater_mod.cleanup_backup(current) is True


def test_notify_shell_does_not_raise(tmp_path: Path) -> None:
    """win32 면 SHChangeNotify, 그 외 no-op — 어느 쪽이든 예외 없이 반환."""
    updater_mod.notify_shell(tmp_path)


def test_stale_backup_skipped_when_not_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """dev(비-frozen)에서는 안전망이 no-op — 형제 .old 를 건드리지 않는다."""
    current = tmp_path / "App.exe"
    current.write_text("x")
    backup = current.with_suffix(".old")
    backup.write_text("old")

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(current))

    core_updater.cleanup_stale_backup()

    assert backup.exists()


def test_stale_backup_deleted_when_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """frozen 이면 안전망이 형제 .old 를 청소한다(orphan 누적 방지)."""
    current = tmp_path / "App.exe"
    current.write_text("x")
    backup = current.with_suffix(".old")
    backup.write_text("old")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(current))

    core_updater.cleanup_stale_backup()

    assert not backup.exists()
