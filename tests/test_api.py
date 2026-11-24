"""端到端 API 测试：登记 -> 换发 -> 分批确认 -> 查询 -> 再换发。"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app, get_conn


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    # 同时固定环境变量与模块属性：monkeypatch.undo 还原模块属性后，
    # 默认路径仍指向本测试的临时库
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    db.init_db(str(db_file))
    yield TestClient(app)


ROWS = ["area-a", "area-b", "area-c"]
COLS = ["cargo-x", "cargo-y", "cargo-z"]
BASE = [
    [10, 5, 5],   # 行小计 20
    [4, 8, 8],    # 行小计 20
    [6, 7, 7],    # 行小计 20
]
# 列小计：20, 20, 20


def _register(client, month="2026-11", matrix=None):
    return client.post(
        f"/months/{month}/register",
        json={"rows": ROWS, "cols": COLS, "matrix": matrix or BASE},
    )


def test_health_and_register(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = _register(client)
    assert r.status_code == 201
    # 同月重复登记被拒
    assert _register(client).status_code == 409
    # 未登记月份查询 404
    assert client.get("/months/2000-01/table").status_code == 404


def test_full_flow_single_batch_and_query_masking(client):
    _register(client)
    # 一个 2x2 环：四角 +/-1，两组小计不变
    new = [
        [11, 4, 5],
        [3, 9, 8],
        [6, 7, 7],
    ]
    r = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS, "cols": COLS, "matrix": new},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    rp_id = body["replacement_id"]
    assert body["batch_count"] == 1
    assert body["changed_cells"] == 4
    batch_no = body["batches"][0]["batch_no"]
    assert len(body["batches"][0]["cells"]) == 4

    # 确认前：查询仍显示原值
    table = client.get("/months/2026-11/table").json()
    assert table["matrix"] == BASE
    assert table["pending_replacement_id"] == rp_id
    assert table["row_subtotals"] == [20, 20, 20]
    assert table["col_subtotals"] == [20, 20, 20]

    # 确认
    r = client.post(f"/replacements/{rp_id}/batches/{batch_no}/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    assert r.json()["remaining_batches"] == 0

    # 最后一批确认后与新表完全一致
    table = client.get("/months/2026-11/table").json()
    assert table["matrix"] == new
    assert table["row_subtotals"] == [20, 20, 20]
    assert table["col_subtotals"] == [20, 20, 20]
    assert "pending_replacement_id" not in table
    assert client.get(f"/replacements/{rp_id}").json()["status"] == "confirmed"


def test_multi_batch_confirm_in_any_order_and_masking(client):
    rows = ["area-a", "area-b", "area-c"]
    cols = ["cargo-w", "cargo-x", "cargo-y", "cargo-z"]
    base = [
        [10, 5, 5, 4],   # 行小计 24
        [4, 8, 8, 4],    # 行小计 24
        [6, 7, 7, 4],    # 行小计 24
    ]
    # 列小计：20, 20, 20, 12
    r = client.post(
        "/months/2026-11/register",
        json={"rows": rows, "cols": cols, "matrix": base},
    )
    assert r.status_code == 201

    # 两条共享行 A 的 4 环，共 8 格，两组小计均不变
    new = [
        [9, 6, 6, 3],    # A: w-1, x+1, y+1, z-1
        [5, 7, 8, 4],    # B: w+1, x-1
        [6, 7, 6, 5],    # C: y-1, z+1
    ]
    body = client.post(
        "/months/2026-11/replacements",
        json={"rows": rows, "cols": cols, "matrix": new},
    ).json()
    rp_id = body["replacement_id"]
    assert body["batch_count"] == 2
    assert body["changed_cells"] == 8

    # 任意顺序：先确认第 2 批
    r = client.post(f"/replacements/{rp_id}/batches/2/confirm")
    assert r.status_code == 200
    assert r.json()["remaining_batches"] == 1
    assert r.json()["status"] == "pending"

    # 查询只显示已确认格的新值，其余仍是原值
    table = client.get("/months/2026-11/table").json()["matrix"]
    batches = client.get(f"/replacements/{rp_id}/batches").json()
    confirmed_cells = {
        tuple(cell)
        for b in batches if b["batch_no"] == 2
        for cell in b["cells"]
    }
    for i, r_name in enumerate(rows):
        for j, c_name in enumerate(cols):
            if (r_name, c_name) in confirmed_cells:
                assert table[i][j] == new[i][j]
            else:
                assert table[i][j] == base[i][j]

    # 每批确认后两组小计都不变
    view = client.get("/months/2026-11/table").json()
    assert view["row_subtotals"] == [24, 24, 24]
    assert view["col_subtotals"] == [20, 20, 20, 12]

    # 再确认第 1 批：全部完成
    r = client.post(f"/replacements/{rp_id}/batches/1/confirm").json()
    assert r["status"] == "confirmed"
    assert client.get("/months/2026-11/table").json()["matrix"] == new
    final = client.get("/months/2026-11/table").json()
    assert final["row_subtotals"] == [24, 24, 24]
    assert final["col_subtotals"] == [20, 20, 20, 12]


def test_duplicate_confirm_is_idempotent(client):
    _register(client)
    new = [[11, 4, 5], [3, 9, 8], [6, 7, 7]]
    rp_id = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS, "cols": COLS, "matrix": new},
    ).json()["replacement_id"]

    first = client.post(f"/replacements/{rp_id}/batches/1/confirm").json()
    assert first["written"] == 4 and first["already_confirmed"] is False
    second = client.post(f"/replacements/{rp_id}/batches/1/confirm").json()
    assert second["already_confirmed"] is True and second["written"] == 0

    # 底表只写过一次
    conn = sqlite3.connect(db.DB_PATH)
    n = conn.execute(
        "SELECT COUNT(*) FROM replacement_cell "
        "WHERE replacement_id = ? AND confirmed = 1", (rp_id,)
    ).fetchone()[0]
    conn.close()
    assert n == 4


def test_write_failure_keeps_original_values(client, monkeypatch):
    _register(client)
    new = [[11, 4, 5], [3, 9, 8], [6, 7, 7]]
    rp_id = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS, "cols": COLS, "matrix": new},
    ).json()["replacement_id"]

    real_connect = db.connect
    real_execute = sqlite3.Connection.execute
    db_file = db.DB_PATH  # 固定当前测试的库路径
    state = {"fail_armed": True, "writes": 0}

    class FlakyConn(sqlite3.Connection):
        def execute(self, sql, params=()):
            if (
                state["fail_armed"]
                and isinstance(sql, str)
                and sql.lstrip().startswith("UPDATE live_cell")
            ):
                state["writes"] += 1
                if state["writes"] == 2:
                    # 批次写到一半时模拟磁盘写入失败
                    raise sqlite3.OperationalError("simulated disk write failure")
            return real_execute(self, sql, params)

    def flaky_connect(path=None):
        conn = sqlite3.connect(path or db_file, timeout=30, factory=FlakyConn)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # 只替换连接工厂，不动 DB_PATH/env，避免还原后库路径漂移
    monkeypatch.setattr(db, "connect", flaky_connect)

    r = client.post(f"/replacements/{rp_id}/batches/1/confirm")
    assert r.status_code == 500
    monkeypatch.setattr(db, "connect", real_connect)
    state["fail_armed"] = False

    # 该批各格都保留原值，批次仍未确认
    table_resp = client.get("/months/2026-11/table")
    assert table_resp.status_code == 200, table_resp.text
    assert table_resp.json()["matrix"] == BASE
    batch = client.get(f"/replacements/{rp_id}/batches").json()[0]
    assert batch["confirmed"] is False

    # 恢复后可正常确认
    ok = client.post(f"/replacements/{rp_id}/batches/1/confirm").json()
    assert ok["status"] == "confirmed"
    assert client.get("/months/2026-11/table").json()["matrix"] == new


def test_pending_replacement_blocks_new_application(client):
    _register(client)
    new1 = [[11, 4, 5], [3, 9, 8], [6, 7, 7]]
    first = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS, "cols": COLS, "matrix": new1},
    )
    assert first.status_code == 201
    rp_id = first.json()["replacement_id"]

    # 还有未确认批次：退回新的换发申请
    r = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS, "cols": COLS, "matrix": new1},
    )
    assert r.status_code == 409

    # 确认完成后可以再次申请下一轮换发
    client.post(f"/replacements/{rp_id}/batches/1/confirm")
    new2 = [[10, 5, 5], [4, 8, 8], [6, 7, 7]]  # 回到最初底表
    r = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS, "cols": COLS, "matrix": new2},
    )
    assert r.status_code == 201
    assert r.json()["batch_count"] == 1


# --------------------------------------------------------------------------- #
# 提交校验
# --------------------------------------------------------------------------- #
def test_reject_changed_shape(client):
    _register(client)
    r = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS + ["area-d"], "cols": COLS,
              "matrix": BASE + [[1, 1, 1]]},
    )
    assert r.status_code == 422


def test_reject_change_over_one_ton(client):
    _register(client)
    bad = [row[:] for row in BASE]
    bad[0][0] += 2
    r = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS, "cols": COLS, "matrix": bad},
    )
    assert r.status_code == 422
    assert "+/-1" in r.json()["detail"]


def test_reject_broken_row_subtotal(client):
    _register(client)
    bad = [row[:] for row in BASE]
    bad[0][0] += 1  # 只动一格：行小计 +1，列小计 +1
    r = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS, "cols": COLS, "matrix": bad},
    )
    assert r.status_code == 422
    assert "subtotal" in r.json()["detail"]


def test_reject_identical_table(client):
    _register(client)
    r = client.post(
        "/months/2026-11/replacements",
        json={"rows": ROWS, "cols": COLS, "matrix": BASE},
    )
    assert r.status_code == 422


def test_reject_negative_and_bad_shape(client):
    r = client.post(
        "/months/2026-11/register",
        json={"rows": ROWS, "cols": COLS,
              "matrix": [[-1, 0, 0], [0, 0, 0], [0, 0, 0]]},
    )
    assert r.status_code == 422
    r = client.post(
        "/months/2026-11/register",
        json={"rows": ROWS, "cols": COLS,
              "matrix": [[0, 0], [0, 0], [0, 0]]},
    )
    assert r.status_code == 422


def test_unknown_replacement_and_batch_404(client):
    _register(client)
    assert client.get("/replacements/999").status_code == 404
    assert client.get("/replacements/999/batches").status_code == 404
    assert client.post("/replacements/999/batches/1/confirm").status_code == 404
