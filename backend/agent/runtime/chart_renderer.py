"""ChartSpecV1 → ECharts option 변환기.

polars 로 parquet 을 읽어 encoding 채널에 따라 ECharts option JSON 을 생성한다.
프론트엔드는 이 결과를 ``echarts.init().setOption(option)`` 으로 그대로 사용한다.

이 모듈은 순수 함수 모음 — FastAPI/harness 의존성 없이 단독 테스트 가능.

지원 mark / encoding 매트릭스:
    bar       : x(nominal|quantitative) + y(quantitative) + color(nominal) optional
    line      : x(quantitative|temporal) + y(quantitative) + color optional
    scatter   : x(quantitative) + y(quantitative) + color optional
    box       : y(quantitative) [+ x(nominal) for grouped boxplot] + color optional
    histogram : x(quantitative, bin=True) → bin count
    heatmap   : x(nominal) + y(nominal) + color(quantitative)

aggregate 지원: count·mean·sum·min·max. groupby 키는 색/x 채널 조합으로 결정.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

import polars as pl

from .chart_spec import (
    ChartSpecV1,
    ChartV1,
    Encoding,
    EncodingChannel,
    EncodingType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 상수 — ECharts 공통 toolbox / axis type 매핑
# ---------------------------------------------------------------------------

_TOOLBOX_FEATURE: dict[str, Any] = {
    "brush": {"type": ["rect", "polygon", "clear"]},
    "dataZoom": {},
    "restore": {},
    "saveAsImage": {},
}

_ENCODING_TO_AXIS_TYPE: dict[EncodingType, str] = {
    "quantitative": "value",
    "nominal": "category",
    "temporal": "time",
}


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def render_spec_to_echarts(spec: ChartSpecV1, base_dir: Path) -> list[dict[str, Any]]:
    """spec 의 각 차트를 ECharts option dict 로 변환해 리스트로 반환한다.

    Args:
        spec: 검증된 ChartSpecV1 인스턴스.
        base_dir: parquet 파일을 찾을 디렉터리 (spec 파일이 위치한 폴더).

    Returns:
        ``[{chart_type, title, option}, ...]`` — 프론트엔드가 직접 소비하는 형태.

    Raises:
        FileNotFoundError: data.source 가 가리키는 parquet 파일이 없을 때.
        ValueError: encoding 또는 mark 가 데이터와 호환되지 않을 때.
    """
    rendered: list[dict[str, Any]] = []
    for idx, chart in enumerate(spec.charts):
        try:
            df = _load_data_frame(chart.data.source, base_dir)
            option = _render_chart(chart, df)
        except (FileNotFoundError, ValueError) as exc:
            raise type(exc)(
                f"charts[{idx}] ({chart.mark}, {chart.title!r}): {exc}"
            ) from exc

        if chart.extra_option:
            option = _deep_merge(option, chart.extra_option)

        rendered.append(
            {
                "chart_type": chart.mark,
                "title": chart.title,
                "option": option,
            }
        )
    return rendered


# ---------------------------------------------------------------------------
# 데이터 로딩
# ---------------------------------------------------------------------------


def _load_data_frame(source: str, base_dir: Path) -> pl.DataFrame:
    """spec 의 data.source → polars DataFrame.

    경로 검증: 슬래시/역슬래시/`..` 모두 금지 (단순 파일명만).
    """
    if "/" in source or "\\" in source or ".." in source:
        raise ValueError(f"data.source 는 단순 파일명만 허용한다: {source!r}")

    target = base_dir / source
    if not target.exists():
        raise FileNotFoundError(f"parquet 파일을 찾을 수 없다: {source!r}")

    return pl.read_parquet(target)


# ---------------------------------------------------------------------------
# 마크별 렌더러
# ---------------------------------------------------------------------------


def _render_chart(chart: ChartV1, df: pl.DataFrame) -> dict[str, Any]:
    """mark 별 렌더러 분기."""
    if chart.mark == "bar":
        return _render_standard(chart, df, echarts_type="bar")
    if chart.mark == "line":
        return _render_standard(chart, df, echarts_type="line")
    if chart.mark == "scatter":
        return _render_standard(chart, df, echarts_type="scatter")
    if chart.mark == "box":
        return _render_box(chart, df)
    if chart.mark == "histogram":
        return _render_histogram(chart, df)
    if chart.mark == "heatmap":
        return _render_heatmap(chart, df)
    raise ValueError(f"미지원 mark: {chart.mark!r}")


def _render_standard(
    chart: ChartV1,
    df: pl.DataFrame,
    *,
    echarts_type: str,
) -> dict[str, Any]:
    """bar / line / scatter 공용 렌더러.

    encoding.color 가 있으면 color field 로 groupby 해 여러 시리즈를 만든다.
    """
    enc = chart.encoding
    if enc.x is None or enc.y is None:
        raise ValueError(f"{chart.mark} 차트는 x, y encoding 모두 필요하다")

    _ensure_columns(
        df, [enc.x.field, enc.y.field] + ([enc.color.field] if enc.color else [])
    )

    x_axis_type = _ENCODING_TO_AXIS_TYPE[enc.x.type]
    y_axis_type = _ENCODING_TO_AXIS_TYPE[enc.y.type]

    # bar 차트는 보통 category x. type 이 quantitative 여도 사용자가 명시했으면 존중.
    series, x_categories = _build_series(df, enc, echarts_type)

    option: dict[str, Any] = {
        "tooltip": {"trigger": "axis" if echarts_type != "scatter" else "item"},
        "legend": {"data": [s["name"] for s in series]},
        "toolbox": {"feature": _TOOLBOX_FEATURE},
        "brush": {},
        "dataZoom": [{"type": "inside"}, {"type": "slider"}],
        "xAxis": _axis_definition(enc.x, x_axis_type, x_categories),
        "yAxis": _axis_definition(enc.y, y_axis_type, None),
        "series": series,
    }
    if chart.title:
        option["title"] = {"text": chart.title}
    return option


def _render_box(chart: ChartV1, df: pl.DataFrame) -> dict[str, Any]:
    """boxplot 렌더러 — y 컬럼에서 [min, Q1, median, Q3, max] 계산.

    x 채널이 있으면 x 값별로 박스 묶음 (categorical x).
    color 채널이 있으면 색별로 추가 그루핑.
    """
    enc = chart.encoding
    if enc.y is None:
        raise ValueError("box 차트는 y encoding 이 필요하다")

    _ensure_columns(
        df,
        [enc.y.field]
        + ([enc.x.field] if enc.x else [])
        + ([enc.color.field] if enc.color else []),
    )

    # 그룹 키 결정: x + color (있는 것만)
    group_fields = [c.field for c in (enc.x, enc.color) if c is not None]

    if not group_fields:
        # 전체 데이터를 단일 박스로
        categories = [chart.title or enc.y.field]
        box_data = [_box_stats(df[enc.y.field])]
        series_data = [
            {"name": enc.y.title or enc.y.field, "type": "boxplot", "data": box_data}
        ]
    else:
        grouped = df.group_by(group_fields, maintain_order=True).agg(
            pl.col(enc.y.field)
        )
        categories = [
            _compose_group_label(row, group_fields)
            for row in grouped.iter_rows(named=True)
        ]
        box_values = [
            _box_stats(pl.Series(row[enc.y.field]))
            for row in grouped.iter_rows(named=True)
        ]
        series_data = [
            {
                "name": enc.y.title or enc.y.field,
                "type": "boxplot",
                "data": box_values,
            }
        ]

    option: dict[str, Any] = {
        "tooltip": {"trigger": "item"},
        "legend": {"data": [s["name"] for s in series_data]},
        "toolbox": {"feature": _TOOLBOX_FEATURE},
        "xAxis": {
            "type": "category",
            "name": (enc.x.title if enc.x else "") or "",
            "data": categories,
        },
        "yAxis": _axis_definition(enc.y, _ENCODING_TO_AXIS_TYPE[enc.y.type], None),
        "series": series_data,
    }
    if chart.title:
        option["title"] = {"text": chart.title}
    return option


def _render_histogram(chart: ChartV1, df: pl.DataFrame) -> dict[str, Any]:
    """histogram 렌더러 — x.bin=True 인 quantitative 컬럼을 빈으로 나눠 카운트."""
    enc = chart.encoding
    if enc.x is None:
        raise ValueError("histogram 은 x encoding 이 필요하다")
    if not enc.x.bin:
        raise ValueError("histogram 은 x.bin=true 가 필요하다")
    if enc.x.type != "quantitative":
        raise ValueError("histogram 의 x.type 은 quantitative 여야 한다")

    _ensure_columns(df, [enc.x.field])

    series = df[enc.x.field].drop_nulls()
    if series.len() == 0:
        raise ValueError("histogram: 데이터가 비어 있다")

    bin_count = 10  # 향후 spec 으로 노출 가능. 현재는 합리적 기본값.
    bins = _equal_width_bins(series, bin_count)
    counts = _bin_counts(series, bins)

    bin_labels = [f"[{bins[i]:.2f}, {bins[i + 1]:.2f})" for i in range(len(bins) - 1)]

    option: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["count"]},
        "toolbox": {"feature": _TOOLBOX_FEATURE},
        "xAxis": {
            "type": "category",
            "name": enc.x.title or enc.x.field,
            "data": bin_labels,
        },
        "yAxis": {
            "type": "value",
            "name": (enc.y.title if enc.y else "count") or "count",
        },
        "series": [
            {
                "name": "count",
                "type": "bar",
                "data": counts,
            }
        ],
    }
    if chart.title:
        option["title"] = {"text": chart.title}
    return option


def _render_heatmap(chart: ChartV1, df: pl.DataFrame) -> dict[str, Any]:
    """heatmap 렌더러 — x(nominal) × y(nominal) × color(quantitative) 3-튜플."""
    enc = chart.encoding
    if enc.x is None or enc.y is None or enc.color is None:
        raise ValueError("heatmap 은 x, y, color encoding 모두 필요하다")
    if enc.color.type != "quantitative":
        raise ValueError("heatmap 의 color.type 은 quantitative 여야 한다")

    _ensure_columns(df, [enc.x.field, enc.y.field, enc.color.field])

    x_values = df[enc.x.field].unique(maintain_order=True).to_list()
    y_values = df[enc.y.field].unique(maintain_order=True).to_list()
    x_index = {v: i for i, v in enumerate(x_values)}
    y_index = {v: i for i, v in enumerate(y_values)}

    data_points: list[list[float | int]] = []
    color_values: list[float] = []
    for row in df.iter_rows(named=True):
        xi = x_index[row[enc.x.field]]
        yi = y_index[row[enc.y.field]]
        val = float(row[enc.color.field])
        data_points.append([xi, yi, val])
        color_values.append(val)

    option: dict[str, Any] = {
        "tooltip": {"trigger": "item"},
        "toolbox": {"feature": _TOOLBOX_FEATURE},
        "xAxis": {
            "type": "category",
            "name": enc.x.title or enc.x.field,
            "data": [str(v) for v in x_values],
        },
        "yAxis": {
            "type": "category",
            "name": enc.y.title or enc.y.field,
            "data": [str(v) for v in y_values],
        },
        "visualMap": {
            "min": min(color_values, default=0),
            "max": max(color_values, default=1),
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": "5%",
        },
        "series": [
            {
                "name": enc.color.title or enc.color.field,
                "type": "heatmap",
                "data": data_points,
            }
        ],
    }
    if chart.title:
        option["title"] = {"text": chart.title}
    return option


# ---------------------------------------------------------------------------
# 시리즈 빌더 (bar / line / scatter 공용)
# ---------------------------------------------------------------------------


def _build_series(
    df: pl.DataFrame,
    enc: Encoding,
    echarts_type: str,
) -> tuple[list[dict[str, Any]], list[str] | None]:
    """encoding 에 따라 시리즈 리스트와 (필요 시) 카테고리 축 라벨 생성.

    color 가 있으면 그룹별로 시리즈를 분리한다. aggregate 가 있으면 groupby 집계.
    bar 차트는 x 축이 category 이면 카테고리 리스트도 반환.
    """
    assert enc.x is not None and enc.y is not None

    needs_categories = enc.x.type == "nominal" or echarts_type == "bar"
    x_categories: list[str] | None = None

    # color 가 있으면 그룹별 시리즈
    if enc.color is not None:
        group_field = enc.color.field
        groups = df[group_field].unique(maintain_order=True).to_list()

        if needs_categories:
            x_categories = [
                str(v) for v in df[enc.x.field].unique(maintain_order=True).to_list()
            ]

        series_list: list[dict[str, Any]] = []
        for group_value in groups:
            subset = df.filter(pl.col(group_field) == group_value)
            subset = _maybe_aggregate(
                subset, enc, group_field=enc.x.field if needs_categories else None
            )
            series_list.append(
                {
                    "name": str(group_value),
                    "type": echarts_type,
                    "data": _rows_to_pairs(subset, enc, x_categories),
                    **({"symbolSize": 8} if echarts_type == "scatter" else {}),
                }
            )
        return series_list, x_categories

    # 단일 시리즈
    aggregated = _maybe_aggregate(
        df, enc, group_field=enc.x.field if needs_categories else None
    )
    if needs_categories:
        x_categories = [str(v) for v in aggregated[enc.x.field].to_list()]

    series_one = {
        "name": enc.y.title or enc.y.field,
        "type": echarts_type,
        "data": _rows_to_pairs(aggregated, enc, x_categories),
        **({"symbolSize": 8} if echarts_type == "scatter" else {}),
    }
    return [series_one], x_categories


def _maybe_aggregate(
    df: pl.DataFrame,
    enc: Encoding,
    *,
    group_field: str | None,
) -> pl.DataFrame:
    """y.aggregate 가 있으면 group_field 로 묶어 집계한다."""
    assert enc.x is not None and enc.y is not None
    aggregate = enc.y.aggregate
    if aggregate is None or group_field is None:
        return df

    agg_expr = _aggregate_expr(enc.y.field, aggregate)
    grouped = df.group_by(group_field, maintain_order=True).agg(
        agg_expr.alias(enc.y.field)
    )
    return grouped


def _aggregate_expr(field: str, fn: str) -> pl.Expr:
    if fn == "count":
        return pl.col(field).count()
    if fn == "mean":
        return pl.col(field).mean()
    if fn == "sum":
        return pl.col(field).sum()
    if fn == "min":
        return pl.col(field).min()
    if fn == "max":
        return pl.col(field).max()
    raise ValueError(f"미지원 aggregate: {fn!r}")


def _rows_to_pairs(
    df: pl.DataFrame,
    enc: Encoding,
    x_categories: list[str] | None,
) -> list[Any]:
    """DataFrame 의 (x, y) 컬럼을 ECharts series.data 형태로 변환.

    카테고리 축이면 카테고리 인덱스 순서에 맞춘 y 값 리스트만 반환 (xAxis.data 가 라벨).
    수치/시간 축이면 [[x, y], ...] 페어 반환.
    """
    assert enc.x is not None and enc.y is not None

    if x_categories is not None:
        # 카테고리 축: x 값을 인덱스로 매핑해 누락된 자리를 None 으로 채움
        idx = {v: i for i, v in enumerate(x_categories)}
        out: list[float | None] = [None] * len(x_categories)
        for row in df.iter_rows(named=True):
            key = str(row[enc.x.field])
            if key in idx:
                out[idx[key]] = _to_jsonable(row[enc.y.field])
        return out

    return [
        [_to_jsonable(row[enc.x.field]), _to_jsonable(row[enc.y.field])]
        for row in df.iter_rows(named=True)
    ]


# ---------------------------------------------------------------------------
# 박스/히스토그램 유틸
# ---------------------------------------------------------------------------


def _box_stats(series: pl.Series) -> list[float]:
    """polars quantile 로 [min, Q1, median, Q3, max] 계산."""
    clean = series.drop_nulls()
    if clean.len() == 0:
        return [0.0, 0.0, 0.0, 0.0, 0.0]
    return [
        float(clean.min()),
        float(clean.quantile(0.25, interpolation="linear")),
        float(clean.quantile(0.5, interpolation="linear")),
        float(clean.quantile(0.75, interpolation="linear")),
        float(clean.max()),
    ]


def _equal_width_bins(series: pl.Series, bin_count: int) -> list[float]:
    lo = float(series.min())
    hi = float(series.max())
    if lo == hi:
        # 동일 값만 있으면 인위적인 폭 부여
        hi = lo + 1.0
    step = (hi - lo) / bin_count
    return [lo + step * i for i in range(bin_count + 1)]


def _bin_counts(series: pl.Series, bins: list[float]) -> list[int]:
    counts = [0] * (len(bins) - 1)
    for value in series.to_list():
        for i in range(len(bins) - 1):
            lower = bins[i]
            upper = bins[i + 1]
            inside_last = i == len(bins) - 2 and value == upper
            if (lower <= value < upper) or inside_last:
                counts[i] += 1
                break
    return counts


# ---------------------------------------------------------------------------
# 공용 헬퍼
# ---------------------------------------------------------------------------


def _axis_definition(
    channel: EncodingChannel,
    axis_type: str,
    categories: list[str] | None,
) -> dict[str, Any]:
    axis: dict[str, Any] = {
        "type": axis_type,
        "name": channel.title or channel.field,
    }
    if axis_type == "category" and categories is not None:
        axis["data"] = categories
    return axis


def _ensure_columns(df: pl.DataFrame, fields: list[str]) -> None:
    missing = [f for f in fields if f not in df.columns]
    if missing:
        raise ValueError(
            f"parquet 에 다음 컬럼이 없다: {missing!r}. 사용 가능 컬럼: {df.columns!r}"
        )


def _compose_group_label(row: dict[str, Any], fields: list[str]) -> str:
    return " / ".join(str(row[f]) for f in fields)


def _to_jsonable(value: Any) -> Any:
    """JSON 직렬화 가능 타입으로 변환. polars/numpy 스칼라 → Python primitive."""
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    # numpy/polars 스칼라 처리
    try:
        return value.item()  # numpy / polars 스칼라
    except AttributeError:
        return str(value)  # datetime 등은 ISO 문자열


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """override 를 base 에 재귀 병합. list 는 override 가 교체."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
