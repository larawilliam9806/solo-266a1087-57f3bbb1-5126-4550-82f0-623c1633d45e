"""FastAPI 入口：港口整吨运量底表分批换发 API。"""

import sqlite3
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from . import db, service
from .models import TablePayload


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="港口运量底表分批换发 API",
    description=(
        "同月先登记现用表；换发提交同形新表（每格最多增减 1 吨、行列小计"
        "不变），系统把变动格切成互不重叠的最小批次，按批号任意顺序确认。"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(service.ServiceError)
def _service_error_handler(_request, exc: service.ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(sqlite3.Error)
def _sqlite_error_handler(_request: Request, exc: sqlite3.Error) -> JSONResponse:
    # 写入失败等数据库异常：事务已在 service 层回滚，返回统一 500
    return JSONResponse(
        status_code=500,
        content={"detail": f"database write failed, batch rolled back: {exc}"},
    )


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


@app.post("/months/{month}/register", status_code=201)
def register(
    month: str, payload: TablePayload, conn=Depends(get_conn)
) -> Dict[str, Any]:
    """同月先登记现用表（作业区 x 货类的整吨矩阵）。"""
    return service.register_month(
        conn, month, payload.rows, payload.cols, payload.matrix
    )


@app.post("/months/{month}/replacements", status_code=201)
def create_replacement(
    month: str, payload: TablePayload, conn=Depends(get_conn)
) -> Dict[str, Any]:
    """提交换发：校验通过后返回切分好的批次清单。"""
    return service.create_replacement(
        conn, month, payload.rows, payload.cols, payload.matrix
    )


@app.get("/months/{month}/table")
def get_table(month: str, conn=Depends(get_conn)) -> Dict[str, Any]:
    """查询当前对外可见的表：只显示已确认格的新值，其余为原值。"""
    return service.get_table(conn, month)


@app.get("/replacements/{rp_id}")
def get_replacement(rp_id: int, conn=Depends(get_conn)) -> Dict[str, Any]:
    return service.get_replacement(conn, rp_id)


@app.get("/replacements/{rp_id}/batches")
def list_batches(rp_id: int, conn=Depends(get_conn)) -> List[Dict[str, Any]]:
    return service.list_batches(conn, rp_id)


@app.post("/replacements/{rp_id}/batches/{batch_no}/confirm")
def confirm_batch(
    rp_id: int, batch_no: int, conn=Depends(get_conn)
) -> Dict[str, Any]:
    """凭批号确认（可任意顺序）；重复确认幂等，写入失败整批回滚。"""
    return service.confirm_batch(conn, rp_id, batch_no)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}
