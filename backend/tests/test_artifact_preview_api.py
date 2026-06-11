"""/api/artifact/preview·csv·reveal 엔드포인트 통합 검증 — 아티팩트 패널 HTTP 경계.

TestClient 로 라우터를 직접 구동해 경로 검증(resolve_result_path containment)·
head 미리보기·CSV 변환·폴더 열기가 HTTP 경계에서 올바르게 엮이는지 확인한다.
reveal 은 실제 탐색기를 띄우지 않도록 _open_folder 를 monkeypatch 한다.
dev(non-frozen)라 origin 가드는 통과.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.artifact import router as artifact_router

_PARQUET_PATH = "result/sess/ts/data.parquet"
_TOTAL_ROWS = 15
_NAN_ROW_INDEX = 2


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """tmp_path 를 RESULT_DIR 로 둔 채 parquet 산출물을 만들고 클라이언트 반환."""
    monkeypatch.setattr("core.result_store.RESULT_DIR", tmp_path)

    out_dir = tmp_path / "sess" / "ts"
    out_dir.mkdir(parents=True)

    values = [float(i) for i in range(_TOTAL_ROWS)]
    values[_NAN_ROW_INDEX] = float("nan")
    pl.DataFrame(
        {
            "name": [f"r{i}" for i in range(_TOTAL_ROWS)],
            "value": values,
            "when": [date(2026, 1, i + 1) for i in range(_TOTAL_ROWS)],
        }
    ).write_parquet(out_dir / "data.parquet")
    (out_dir / "note.md").write_text("# note", encoding="utf-8")

    app = FastAPI()
    app.include_router(artifact_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/artifact/preview
# ---------------------------------------------------------------------------


def test_preview_returns_head_and_meta(client: TestClient) -> None:
    resp = client.get("/api/artifact/preview", params={"path": _PARQUET_PATH})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["filename"] == "data.parquet"
    assert data["path"] == _PARQUET_PATH
    assert data["total_rows"] == _TOTAL_ROWS
    assert data["size"] > 0
    assert data["head"]["columns"] == ["name", "value", "when"]
    # head 기본 10행 — total(15) 보다 작게 잘린다.
    assert len(data["head"]["rows"]) == 10
    assert [c["name"] for c in data["schema"]] == ["name", "value", "when"]
    assert all(c["dtype"] for c in data["schema"])


def test_preview_json_safe_cells(client: TestClient) -> None:
    """NaN 은 null 로, date 등 비원시 타입은 문자열로 직렬화된다."""
    resp = client.get("/api/artifact/preview", params={"path": _PARQUET_PATH})
    rows = resp.json()["head"]["rows"]

    assert rows[_NAN_ROW_INDEX][1] is None  # NaN → null
    assert rows[0][1] == 0.0  # 정상 float 은 그대로
    assert isinstance(rows[0][2], str)  # date → "2026-01-01"
    assert rows[0][2] == "2026-01-01"


def test_preview_rows_param(client: TestClient) -> None:
    resp = client.get(
        "/api/artifact/preview", params={"path": _PARQUET_PATH, "rows": 3}
    )
    assert len(resp.json()["head"]["rows"]) == 3

    # ge=1 검증 위반 → FastAPI 422.
    assert (
        client.get(
            "/api/artifact/preview", params={"path": _PARQUET_PATH, "rows": 0}
        ).status_code
        == 422
    )


def test_preview_rejects_non_parquet(client: TestClient) -> None:
    resp = client.get(
        "/api/artifact/preview", params={"path": "result/sess/ts/note.md"}
    )
    assert resp.status_code == 400


def test_preview_missing_file_returns_404(client: TestClient) -> None:
    resp = client.get(
        "/api/artifact/preview", params={"path": "result/sess/ts/ghost.parquet"}
    )
    assert resp.status_code == 404


def test_preview_rejects_traversal(client: TestClient) -> None:
    resp = client.get(
        "/api/artifact/preview", params={"path": "result/../escape.parquet"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /api/artifact/csv
# ---------------------------------------------------------------------------


def test_csv_returns_full_data_as_attachment(client: TestClient) -> None:
    resp = client.get("/api/artifact/csv", params={"path": _PARQUET_PATH})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")

    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition
    assert "data.csv" in disposition

    lines = resp.text.strip().splitlines()
    assert lines[0] == "name,value,when"
    assert len(lines) == 1 + _TOTAL_ROWS  # 헤더 + 전체 행 (head 절단 없음)
    assert lines[1].startswith("r0,")


def test_csv_rejects_non_parquet(client: TestClient) -> None:
    resp = client.get("/api/artifact/csv", params={"path": "result/sess/ts/note.md"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/artifact/reveal
# ---------------------------------------------------------------------------


def test_reveal_opens_containing_folder(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """파일 경로를 주면 그 파일이 속한 폴더가 탐색기로 열린다."""
    opened: list[Path] = []
    monkeypatch.setattr(
        "api.artifact._open_folder", lambda folder: opened.append(folder)
    )

    resp = client.post("/api/artifact/reveal", json={"path": _PARQUET_PATH})
    assert resp.status_code == 200, resp.text
    assert resp.json()["path"] == "result/sess/ts"

    assert len(opened) == 1
    assert opened[0].name == "ts"
    assert (opened[0] / "data.parquet").exists()  # 폴더는 파일의 부모.


def test_reveal_is_extension_agnostic(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """reveal 은 parquet 전용이 아니다 — 패널의 모든 칩 종류(markdown 등)가 쓴다.

    preview/csv 처럼 _resolve_parquet 을 재사용하는 리팩토링이 들어오면
    markdown·chart·image 칩의 폴더 열기가 조용히 400 으로 회귀하는 것을 막는다.
    """
    opened: list[Path] = []
    monkeypatch.setattr(
        "api.artifact._open_folder", lambda folder: opened.append(folder)
    )

    resp = client.post("/api/artifact/reveal", json={"path": "result/sess/ts/note.md"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["path"] == "result/sess/ts"
    assert len(opened) == 1


def test_reveal_missing_file_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """존재하지 않는 산출물은 404 이며 탐색기를 띄우지 않는다."""
    opened: list[Path] = []
    monkeypatch.setattr(
        "api.artifact._open_folder", lambda folder: opened.append(folder)
    )

    resp = client.post(
        "/api/artifact/reveal", json={"path": "result/sess/ts/ghost.parquet"}
    )
    assert resp.status_code == 404
    assert opened == []


def test_reveal_rejects_traversal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RESULT_DIR 밖으로 벗어나는 경로는 거부한다."""
    opened: list[Path] = []
    monkeypatch.setattr(
        "api.artifact._open_folder", lambda folder: opened.append(folder)
    )

    resp = client.post(
        "/api/artifact/reveal", json={"path": "result/../escape.parquet"}
    )
    assert resp.status_code == 404
    assert opened == []
