"""앱 버전 resolver.

frozen EXE 는 빌드 시 App.spec 이 pyproject.toml 에서 생성·박제한 ``_version.py`` 를
읽고, dev 는 pyproject.toml 을 직접 파싱한다. ``backend/_version.py`` 는 gitignored
생성물이므로 fresh clone 에는 존재하지 않는다 — dev 경로가 pyproject.toml 을
진실원천으로 삼아야 "pull 직후 실행 불가"가 발생하지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.config import _project_root

FALLBACK_VERSION: str = "0.0.0"


def _read_pyproject_version(pyproject_path: Path) -> str | None:
    """pyproject.toml 의 [project].version 값을 읽는다.

    Args:
        pyproject_path (Path): pyproject.toml 파일 경로.

    Returns:
        str | None: 버전 문자열. 파일 부재·TOML 파싱 실패·키 부재 시 None.
    """
    # frozen 경로에서는 불필요한 모듈이므로 dev 분기에서만 지연 import 한다.
    import tomllib

    try:
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None

    project = data.get("project")
    if not isinstance(project, dict):
        return None

    version = project.get("version")
    if not isinstance(version, str) or not version:
        return None

    return version


def resolve_app_version() -> str:
    """현재 앱 버전을 해석한다.

    frozen 은 App.spec 이 빌드 시 박제한 ``_version`` 모듈을 import 하고(MEIPASS 에는
    pyproject.toml 이 없다), dev 는 pyproject.toml 을 직독한다. dev 에 빌드 잔여물
    ``backend/_version.py`` 가 남아 있어도 무시한다 — stale 버전 보고 방지.

    Returns:
        str: 해석된 버전 문자열. 어느 경로로도 얻지 못하면 FALLBACK_VERSION.
    """
    if getattr(sys, "frozen", False):
        try:
            from _version import __version__
        except ImportError:
            return FALLBACK_VERSION
        return __version__

    version = _read_pyproject_version(_project_root() / "pyproject.toml")
    return version if version is not None else FALLBACK_VERSION


APP_VERSION: str = resolve_app_version()
