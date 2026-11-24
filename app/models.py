"""Pydantic 请求/响应模型。"""

from typing import List

from pydantic import BaseModel, Field, field_validator


class TablePayload(BaseModel):
    """整吨运量底表：rows/cols 为作业区、货类标签，matrix 为同形整数矩阵。"""

    rows: List[str] = Field(min_length=1)
    cols: List[str] = Field(min_length=1)
    matrix: List[List[int]]

    @field_validator("rows", "cols")
    @classmethod
    def _unique_labels(cls, v: List[str]) -> List[str]:
        if len(set(v)) != len(v):
            raise ValueError("labels must be unique")
        return v

    @field_validator("matrix")
    @classmethod
    def _shape_and_ints(cls, v: List[List[int]]) -> List[List[int]]:
        if not v:
            raise ValueError("matrix must not be empty")
        width = len(v[0])
        for row in v:
            if len(row) != width:
                raise ValueError("matrix rows must share one width")
            for cell in row:
                # bool 是 int 的子类，整吨表不接受布尔值
                if isinstance(cell, bool) or not isinstance(cell, int):
                    raise ValueError("every cell must be an integer tonnage")
        return v
