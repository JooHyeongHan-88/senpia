"""save_artifact 의 kind='parquet' 분기 회귀 테스트.

namespace 변수 참조 ('$varname') 해석, polars/pandas 입력 처리, 검증 분기 모두 검사.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 도구 등록 트리거.
import agent.tools.artifact as artifact_module  # noqa: E402, F401
from agent.runtime import namespace as ns_module  # noqa: E402
from core import result_store  # noqa: E402
from tests._runner import run_tests  # noqa: E402


def _setup() -> None:
    """매 테스트 시작 시 세션 컨텍스트와 namespace 를 초기화."""
    ns_module._reset_for_tests()
    result_store.set_session_context("parquettest1234", "parquet테스트")


def _save(**kwargs):
    return asyncio.run(artifact_module.save_artifact(**kwargs))


def _store(name: str, value) -> None:
    ns = ns_module.current_namespace()
    ns.store(name, value)


def test_parquet_happy_path_polars_dataframe() -> None:
    _setup()
    df = pl.DataFrame({"a": [1, 2, 3], "b": [10.0, 20.0, 30.0]})
    _store("samples_df", df)

    result = _save(filename="samples.parquet", kind="parquet", source="$samples_df")

    assert result.is_error is False, result.content
    assert result.data["kind"] == "parquet"
    assert result.data["rows"] == 3
    assert result.data["columns"] == 2
    assert result.data["path"].endswith("/samples.parquet")

    # 디스크에서 다시 읽기
    abs_path = (result_store.turn_slot() / "samples.parquet").resolve()
    loaded = pl.read_parquet(abs_path)
    assert loaded.shape == (3, 2)
    assert loaded.columns == ["a", "b"]


def test_parquet_accepts_pandas_dataframe() -> None:
    _setup()
    import pandas as pd

    pdf = pd.DataFrame({"metric": ["a", "b"], "value": [1.0, 2.0]})
    _store("stats_df", pdf)

    result = _save(filename="stats.parquet", kind="parquet", source="$stats_df")

    assert result.is_error is False, result.content
    assert result.data["rows"] == 2


def test_parquet_rejects_non_dataframe() -> None:
    _setup()
    _store("not_a_df", [1, 2, 3])

    result = _save(filename="x.parquet", kind="parquet", source="$not_a_df")

    assert result.is_error is True
    assert "DataFrame" in result.content


def test_parquet_rejects_missing_source() -> None:
    _setup()
    result = _save(filename="x.parquet", kind="parquet")
    assert result.is_error is True
    assert "source" in result.content


def test_parquet_rejects_missing_namespace_var() -> None:
    _setup()
    result = _save(filename="x.parquet", kind="parquet", source="$ghost_df")
    assert result.is_error is True
    assert "ghost_df" in result.content


def test_parquet_rejects_invalid_source_format() -> None:
    _setup()
    result = _save(filename="x.parquet", kind="parquet", source="not a varname")
    assert result.is_error is True


def test_parquet_rejects_extension_mismatch() -> None:
    _setup()
    df = pl.DataFrame({"a": [1]})
    _store("df", df)

    result = _save(filename="data.json", kind="parquet", source="$df")
    assert result.is_error is True
    assert "확장자" in result.content


def test_parquet_forbids_content_field() -> None:
    _setup()
    df = pl.DataFrame({"a": [1]})
    _store("df", df)

    result = _save(
        filename="data.parquet",
        kind="parquet",
        source="$df",
        content="이건 들어가면 안 됨",
    )
    assert result.is_error is True
    assert "content" in result.content


def test_markdown_kind_forbids_source_field() -> None:
    _setup()
    result = _save(
        filename="report.md",
        kind="markdown",
        content="# 본문",
        source="$df",
    )
    assert result.is_error is True
    assert "source" in result.content


def test_markdown_kind_requires_content() -> None:
    _setup()
    result = _save(filename="report.md", kind="markdown")
    assert result.is_error is True
    assert "content" in result.content


def test_parquet_schema_metadata_returned() -> None:
    _setup()
    df = pl.DataFrame({"idx": [1, 2], "value": [1.5, 2.5]})
    _store("df", df)

    result = _save(filename="data.parquet", kind="parquet", source="$df")

    assert result.is_error is False
    assert "schema" in result.data
    names = [s["name"] for s in result.data["schema"]]
    assert names == ["idx", "value"]


def test_parquet_polars_series_promoted_to_frame() -> None:
    _setup()
    s = pl.Series("x", [1.0, 2.0, 3.0])
    _store("xs", s)

    result = _save(filename="x.parquet", kind="parquet", source="$xs")

    assert result.is_error is False, result.content
    assert result.data["rows"] == 3
    assert result.data["columns"] == 1


if __name__ == "__main__":
    run_tests(globals())
