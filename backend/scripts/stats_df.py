"""DataFrame 기반 요약 통계 유틸리티.

`stats.py` 는 stdlib 만 사용해 dict 반환을 보장한다. 이 모듈은 신규 차트 파이프라인에서
parquet 으로 직렬화 가능한 polars DataFrame 을 반환해 같은 데이터를 시각화 spec 의
data.source 로 그대로 사용할 수 있게 한다.

`api_refs` 를 통해 SKILL 에 노출되며 harness 의 `call_function` / `exec_code` 등에서 호출된다.
"""

from __future__ import annotations

import polars as pl


def compute_summary_stats_df(data: list[float] | pl.Series) -> pl.DataFrame:
    """숫자 시퀀스의 요약 통계량을 polars DataFrame 으로 반환한다.

    Args:
        data: 분석 대상 1차원 숫자 시퀀스 (list 또는 polars Series). 비어 있으면 ValueError.

    Returns:
        columns=(metric: str, value: float64), rows=count·mean·median·stdev·min·max 순.
        표본 1개일 땐 stdev=0.0 으로 처리한다.

    Raises:
        ValueError: data 가 비어 있을 때.

    Example:
        >>> df = compute_summary_stats_df([1.0, 2.0, 3.0, 4.0, 5.0])
        >>> df.shape
        (6, 2)
        >>> df.columns
        ['metric', 'value']
    """
    series = (
        data
        if isinstance(data, pl.Series)
        else pl.Series("data", data, dtype=pl.Float64)
    )

    if series.len() == 0:
        raise ValueError("data 는 비어 있을 수 없다")

    count = series.len()
    stdev_value = float(series.std(ddof=1)) if count > 1 else 0.0

    return pl.DataFrame(
        {
            "metric": ["count", "mean", "median", "stdev", "min", "max"],
            "value": [
                float(count),
                round(float(series.mean()), 4),
                round(float(series.median()), 4),
                round(stdev_value, 4),
                float(series.min()),
                float(series.max()),
            ],
        }
    )
