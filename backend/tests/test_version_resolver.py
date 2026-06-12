"""core.version — 버전 resolver 단위 테스트."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import tomllib


def test_dev_version_matches_pyproject():
    """dev 경로: resolve_app_version()가 실제 pyproject.toml 버전을 반환한다."""
    from core.version import resolve_app_version

    assert not getattr(sys, "frozen", False)
    version = resolve_app_version()
    assert version != "0.0.0", "fallback이 반환됨 — pyproject.toml 파싱 실패"

    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        expected = tomllib.load(f)["project"]["version"]
    assert version == expected


def test_frozen_version_from_module(monkeypatch):
    """frozen 경로: sys.modules['_version'] 이 있으면 그 버전을 반환한다."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setitem(
        sys.modules, "_version", types.SimpleNamespace(__version__="9.9.9")
    )

    from core.version import resolve_app_version

    assert resolve_app_version() == "9.9.9"


def test_frozen_version_import_error(monkeypatch):
    """frozen 경로: _version import 실패 시 FALLBACK_VERSION('0.0.0')을 반환한다."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # sys.modules[name] = None 은 import 시 ImportError 를 강제한다.
    monkeypatch.setitem(sys.modules, "_version", None)

    from core.version import FALLBACK_VERSION, resolve_app_version

    assert resolve_app_version() == FALLBACK_VERSION


def test_read_pyproject_version_edge_cases(tmp_path):
    """_read_pyproject_version: 부재 파일/손상 TOML/version 키 부재 → None."""
    from core.version import _read_pyproject_version

    assert _read_pyproject_version(tmp_path / "nonexistent.toml") is None

    bad = tmp_path / "bad.toml"
    bad.write_text("this = [broken", encoding="utf-8")
    assert _read_pyproject_version(bad) is None

    no_ver = tmp_path / "no_ver.toml"
    no_ver.write_text('[project]\nname = "test"\n', encoding="utf-8")
    assert _read_pyproject_version(no_ver) is None

    valid = tmp_path / "valid.toml"
    valid.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    assert _read_pyproject_version(valid) == "1.2.3"
