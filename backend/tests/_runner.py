"""테스트 모듈을 standalone 으로 실행하기 위한 minimal runner.

pytest 의존을 추가하지 않기 위해 `run_tests(globals())` 형태로 각 test_*.py
파일 끝에서 호출한다. test_ prefix 가 붙은 callable 을 자동 수집해 실행.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import traceback
from collections.abc import Callable
from typing import Any


def run_tests(module_globals: dict[str, Any]) -> None:
    """모듈 globals 에서 test_* 함수를 찾아 실행한다. 실패 시 exit code 1."""
    cases: list[tuple[str, Callable[[], Any]]] = sorted(
        (name, obj)
        for name, obj in module_globals.items()
        if name.startswith("test_") and callable(obj)
    )

    passed = 0
    failed: list[tuple[str, str]] = []

    for name, fn in cases:
        try:
            result = fn()
            if inspect.iscoroutine(result):
                asyncio.run(result)
            sys.stdout.write(f"  PASS  {name}\n")
            passed += 1
        except AssertionError as exc:
            sys.stdout.write(f"  FAIL  {name}\n")
            failed.append((name, f"AssertionError: {exc}\n{traceback.format_exc()}"))
        except Exception as exc:  # noqa: BLE001 — runner 는 모든 예외 포착
            sys.stdout.write(f"  ERR   {name}\n")
            failed.append(
                (name, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            )

    total = passed + len(failed)
    sys.stdout.write(f"\n{passed}/{total} passed\n")
    if failed:
        sys.stdout.write("\n--- 실패 상세 ---\n")
        for name, detail in failed:
            sys.stdout.write(f"\n[{name}]\n{detail}\n")
        sys.exit(1)
