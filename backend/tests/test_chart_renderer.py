"""chart_renderer 의 mark × encoding 매트릭스 검증.

순수 pytest — FastAPI/harness 의존 없음. polars 만 사용.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from agent.runtime.chart_renderer import render_spec_to_echarts
from agent.runtime.chart_spec import ChartSpecV1


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    """parquet 파일을 임시 폴더에 만들어 base_dir 로 사용."""
    samples = pl.DataFrame(
        {
            "idx": [1, 2, 3, 4, 5],
            "value": [10.0, 12.0, 9.5, 15.0, 11.0],
            "anomaly_score": [0.1, 0.3, 0.05, 0.9, 0.2],
        }
    )
    samples.write_parquet(tmp_path / "samples.parquet")

    stats = pl.DataFrame(
        {
            "metric": ["count", "mean", "median", "stdev", "min", "max"],
            "value": [5.0, 11.5, 11.0, 2.1, 9.5, 15.0],
        }
    )
    stats.write_parquet(tmp_path / "stats.parquet")

    grouped = pl.DataFrame(
        {
            "group": ["A", "A", "B", "B", "C", "C"],
            "metric": ["m1", "m2", "m1", "m2", "m1", "m2"],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    grouped.write_parquet(tmp_path / "grouped.parquet")

    heat = pl.DataFrame(
        {
            "row": ["r1", "r1", "r2", "r2"],
            "col": ["c1", "c2", "c1", "c2"],
            "value": [0.1, 0.5, 0.7, 0.9],
        }
    )
    heat.write_parquet(tmp_path / "heat.parquet")

    return tmp_path


def _render(spec_dict: dict, base_dir: Path) -> list[dict]:
    spec = ChartSpecV1.model_validate(spec_dict)
    return render_spec_to_echarts(spec, base_dir)


def test_bar_nominal_x_quantitative_y(base_dir: Path) -> None:
    result = _render(
        {
            "version": "1",
            "charts": [
                {
                    "mark": "bar",
                    "title": "통계량",
                    "data": {"source": "stats.parquet"},
                    "encoding": {
                        "x": {"field": "metric", "type": "nominal"},
                        "y": {"field": "value", "type": "quantitative"},
                    },
                }
            ],
        },
        base_dir,
    )

    assert len(result) == 1
    item = result[0]
    assert item["chart_type"] == "bar"
    assert item["title"] == "통계량"
    option = item["option"]
    assert option["xAxis"]["type"] == "category"
    assert option["xAxis"]["data"] == ["count", "mean", "median", "stdev", "min", "max"]
    assert option["yAxis"]["type"] == "value"
    assert option["series"][0]["type"] == "bar"
    assert option["series"][0]["data"] == [5.0, 11.5, 11.0, 2.1, 9.5, 15.0]


def test_line_quantitative_x_y(base_dir: Path) -> None:
    result = _render(
        {
            "version": "1",
            "charts": [
                {
                    "mark": "line",
                    "data": {"source": "samples.parquet"},
                    "encoding": {
                        "x": {"field": "idx", "type": "quantitative"},
                        "y": {"field": "value", "type": "quantitative"},
                    },
                }
            ],
        },
        base_dir,
    )
    option = result[0]["option"]
    assert option["xAxis"]["type"] == "value"
    assert option["yAxis"]["type"] == "value"
    assert option["series"][0]["type"] == "line"
    # 페어 형태
    assert option["series"][0]["data"][0] == [1, 10.0]
    assert option["series"][0]["data"][-1] == [5, 11.0]


def test_scatter_two_quantitative(base_dir: Path) -> None:
    result = _render(
        {
            "version": "1",
            "charts": [
                {
                    "mark": "scatter",
                    "data": {"source": "samples.parquet"},
                    "encoding": {
                        "x": {"field": "value", "type": "quantitative"},
                        "y": {"field": "anomaly_score", "type": "quantitative"},
                    },
                }
            ],
        },
        base_dir,
    )
    option = result[0]["option"]
    assert option["series"][0]["type"] == "scatter"
    assert option["series"][0]["symbolSize"] == 8
    assert option["series"][0]["data"][0] == [10.0, 0.1]


def test_box_single_y(base_dir: Path) -> None:
    result = _render(
        {
            "version": "1",
            "charts": [
                {
                    "mark": "box",
                    "title": "분포",
                    "data": {"source": "samples.parquet"},
                    "encoding": {
                        "y": {"field": "value", "type": "quantitative"},
                    },
                }
            ],
        },
        base_dir,
    )
    option = result[0]["option"]
    assert option["series"][0]["type"] == "boxplot"
    # [min, Q1, median, Q3, max] 형식
    box_data = option["series"][0]["data"][0]
    assert len(box_data) == 5
    assert box_data[0] == 9.5  # min
    assert box_data[4] == 15.0  # max


def test_histogram_bin_quantitative(base_dir: Path) -> None:
    result = _render(
        {
            "version": "1",
            "charts": [
                {
                    "mark": "histogram",
                    "data": {"source": "samples.parquet"},
                    "encoding": {
                        "x": {"field": "value", "type": "quantitative", "bin": True},
                    },
                }
            ],
        },
        base_dir,
    )
    option = result[0]["option"]
    assert option["xAxis"]["type"] == "category"
    assert len(option["xAxis"]["data"]) == 10  # bin_count
    counts = option["series"][0]["data"]
    assert sum(counts) == 5  # 전체 샘플 수


def test_heatmap_three_channels(base_dir: Path) -> None:
    result = _render(
        {
            "version": "1",
            "charts": [
                {
                    "mark": "heatmap",
                    "data": {"source": "heat.parquet"},
                    "encoding": {
                        "x": {"field": "col", "type": "nominal"},
                        "y": {"field": "row", "type": "nominal"},
                        "color": {"field": "value", "type": "quantitative"},
                    },
                }
            ],
        },
        base_dir,
    )
    option = result[0]["option"]
    assert option["xAxis"]["data"] == ["c1", "c2"]
    assert option["yAxis"]["data"] == ["r1", "r2"]
    assert option["visualMap"]["min"] == 0.1
    assert option["visualMap"]["max"] == 0.9
    assert len(option["series"][0]["data"]) == 4


def test_color_channel_splits_series(base_dir: Path) -> None:
    result = _render(
        {
            "version": "1",
            "charts": [
                {
                    "mark": "bar",
                    "data": {"source": "grouped.parquet"},
                    "encoding": {
                        "x": {"field": "metric", "type": "nominal"},
                        "y": {"field": "value", "type": "quantitative"},
                        "color": {"field": "group", "type": "nominal"},
                    },
                }
            ],
        },
        base_dir,
    )
    option = result[0]["option"]
    # 그룹 A, B, C 각각 별도 시리즈
    assert len(option["series"]) == 3
    assert {s["name"] for s in option["series"]} == {"A", "B", "C"}


def test_extra_option_deep_merge(base_dir: Path) -> None:
    result = _render(
        {
            "version": "1",
            "charts": [
                {
                    "mark": "bar",
                    "data": {"source": "stats.parquet"},
                    "encoding": {
                        "x": {"field": "metric", "type": "nominal"},
                        "y": {"field": "value", "type": "quantitative"},
                    },
                    "extra_option": {"tooltip": {"formatter": "{b}: {c}"}},
                }
            ],
        },
        base_dir,
    )
    option = result[0]["option"]
    assert option["tooltip"]["formatter"] == "{b}: {c}"
    assert option["tooltip"]["trigger"] == "axis"  # 기존 값 보존


def test_missing_parquet_raises(base_dir: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nonexistent"):
        _render(
            {
                "version": "1",
                "charts": [
                    {
                        "mark": "bar",
                        "data": {"source": "nonexistent.parquet"},
                        "encoding": {
                            "x": {"field": "x", "type": "nominal"},
                            "y": {"field": "y", "type": "quantitative"},
                        },
                    }
                ],
            },
            base_dir,
        )


def test_missing_column_raises(base_dir: Path) -> None:
    with pytest.raises(ValueError, match="컬럼"):
        _render(
            {
                "version": "1",
                "charts": [
                    {
                        "mark": "bar",
                        "data": {"source": "stats.parquet"},
                        "encoding": {
                            "x": {"field": "nope", "type": "nominal"},
                            "y": {"field": "value", "type": "quantitative"},
                        },
                    }
                ],
            },
            base_dir,
        )


def test_path_escape_blocked(base_dir: Path) -> None:
    with pytest.raises(ValueError, match="단순 파일명"):
        _render(
            {
                "version": "1",
                "charts": [
                    {
                        "mark": "bar",
                        "data": {"source": "../escape.parquet"},
                        "encoding": {
                            "x": {"field": "x", "type": "nominal"},
                            "y": {"field": "y", "type": "quantitative"},
                        },
                    }
                ],
            },
            base_dir,
        )


def test_pandas_written_parquet_loads(tmp_path: Path) -> None:
    """pandas 가 쓴 parquet 도 polars 로 읽혀야 한다 (호환성 보장)."""
    import pandas as pd

    pdf = pd.DataFrame({"metric": ["a", "b", "c"], "value": [1.0, 2.0, 3.0]})
    pdf.to_parquet(tmp_path / "from_pandas.parquet")

    result = _render(
        {
            "version": "1",
            "charts": [
                {
                    "mark": "bar",
                    "data": {"source": "from_pandas.parquet"},
                    "encoding": {
                        "x": {"field": "metric", "type": "nominal"},
                        "y": {"field": "value", "type": "quantitative"},
                    },
                }
            ],
        },
        tmp_path,
    )
    assert result[0]["option"]["series"][0]["data"] == [1.0, 2.0, 3.0]
