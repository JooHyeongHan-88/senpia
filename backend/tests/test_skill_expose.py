"""SKILL expose 플래그 — 유저 비노출(비공개) SKILL 의 도달 차단·프로그램 경로 보존 검증.

expose=False 인 SKILL 은 유저 도달 표면 4개(슬래시 메뉴·force·trigger·이름매칭)에서 전부
차단되지만, activate_skill·R9 carry 가 쓰는 get_by_names 로는 여전히 해석돼야 한다(캡슐화-
하되-호출가능). 기본값 True 의 backward compat 도 함께 확인한다.

러너(_runner.run_tests)가 픽스처를 주입하지 않으므로 pytest tmp_path 대신 tempfile 로 임시
SKILLS 디렉터리를 직접 만든다 — pytest·standalone 양쪽에서 동작.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.registries.skills import SkillRegistry  # noqa: E402
from tests._runner import run_tests  # noqa: E402

# 두 trigger 는 서로 부분문자열이 아니어야 한다 — 한글은 substring 매칭이라
# 한쪽 trigger 가 다른 메시지에 섞여 들면 의도치 않게 매칭된다.
_EXPOSED_SKILL = """\
---
name: public_demo
description: 노출 데모 스킬
trigger:
  - 리포트작성
---

# 공개 데모
공개 스킬 본문.
"""

_HIDDEN_SKILL = """\
---
name: hidden_demo
description: 비공개 데모 스킬
trigger:
  - 후보정제
expose: false
---

# 비공개 데모
비공개 스킬 본문 — activate_skill 로만 도달.
"""


@contextmanager
def _registry() -> Iterator[SkillRegistry]:
    """노출 1 + 비공개 1 스킬을 담은 임시 SkillRegistry 를 yield 한다."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "public_demo.md").write_text(_EXPOSED_SKILL, encoding="utf-8")
        (tmp / "hidden_demo.md").write_text(_HIDDEN_SKILL, encoding="utf-8")
        reg = SkillRegistry(tmp)
        reg.load()
        yield reg


def test_list_meta_exposed_only_excludes_hidden() -> None:
    with _registry() as reg:
        all_names = {m.name for m in reg.list_meta()}
        exposed_names = {m.name for m in reg.list_meta(exposed_only=True)}
    assert all_names == {"public_demo", "hidden_demo"}  # 전체 열거 보존
    assert exposed_names == {"public_demo"}  # 유저 표면은 비공개 제외


def test_select_skips_hidden_even_by_trigger() -> None:
    with _registry() as reg:
        # 비공개 스킬의 trigger 가 메시지에 있어도 select 가 반환하지 않는다(표면 #3).
        matched = {s.meta.name for s in reg.select("후보정제 실행해줘")}
        # 공개 스킬은 정상 매칭(회귀).
        matched_public = {s.meta.name for s in reg.select("리포트작성 해줘")}
    assert matched == set()
    assert matched_public == {"public_demo"}


def test_select_skips_hidden_by_name() -> None:
    with _registry() as reg:
        # 메시지에 스킬 '이름' 이 등장해도 비공개면 name-fallback 차단(표면 #4).
        matched = {s.meta.name for s in reg.select("hidden_demo 써줘")}
    assert matched == set()


def test_get_by_names_resolves_hidden() -> None:
    with _registry() as reg:
        # activate_skill·R9 carry 가 의존 — 비공개 SKILL 도 이름으로 해석돼야 한다.
        resolved = reg.get_by_names(["hidden_demo"])
    assert [s.meta.name for s in resolved] == ["hidden_demo"]
    assert resolved[0].body.strip()  # body lazy load 완료


def test_expose_defaults_true_backward_compat() -> None:
    # expose 미지정 스킬(public_demo)은 기본 True 라 노출·선택된다.
    with _registry() as reg:
        public = next(m for m in reg.list_meta() if m.name == "public_demo")
    assert public.expose is True


if __name__ == "__main__":
    run_tests(globals())
