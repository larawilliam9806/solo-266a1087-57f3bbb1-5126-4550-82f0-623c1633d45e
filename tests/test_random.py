"""随机性质测试：任意平衡 delta 矩阵都能被正确切成最小批次。"""

import random
from itertools import combinations

from app.cycles import decompose_into_cycles


def _random_balanced_deltas(rng: random.Random, n_rows: int, n_cols: int):
    """通过叠加随机 4 环构造行列各自守恒、取值 {-1,0,+1} 的 delta 矩阵。"""
    deltas = {(r, c): 0 for r in range(n_rows) for c in range(n_cols)}
    for _ in range(rng.randint(1, 8)):
        r1, r2 = rng.sample(range(n_rows), 2)
        c1, c2 = rng.sample(range(n_cols), 2)
        sign = rng.choice([-1, 1])
        corners = [((r1, c1), sign), ((r1, c2), -sign),
                   ((r2, c1), -sign), ((r2, c2), sign)]
        if all(abs(deltas[cell] + d) <= 1 for cell, d in corners):
            for cell, d in corners:
                deltas[cell] += d
    return {
        (f"r{r}", f"c{c}"): v
        for (r, c), v in deltas.items() if v != 0
    }


def _balanced(deltas):
    rows, cols = {}, {}
    for (r, c), d in deltas.items():
        rows[r] = rows.get(r, 0) + d
        cols[c] = cols.get(c, 0) + d
    return all(v == 0 for v in rows.values()) and all(
        v == 0 for v in cols.values()
    )


def _has_balanced_proper_subset(deltas, batch):
    """枚举真子集：若存在行列各自守恒的非空真子集，则该批不是最小批。"""
    cells = list(batch)
    for size in range(1, len(cells)):
        for sub in combinations(cells, size):
            rows, cols = {}, {}
            for r, c in sub:
                rows[r] = rows.get(r, 0) + deltas[(r, c)]
                cols[c] = cols.get(c, 0) + deltas[(r, c)]
            if all(v == 0 for v in rows.values()) and all(
                v == 0 for v in cols.values()
            ):
                return True
    return False


def test_random_matrices_partition_balance_and_minimality():
    rng = random.Random(20261124)
    for _ in range(60):
        n_rows = rng.randint(2, 5)
        n_cols = rng.randint(2, 5)
        deltas = _random_balanced_deltas(rng, n_rows, n_cols)
        if not deltas:
            continue
        assert _balanced(deltas)

        batches = decompose_into_cycles(deltas)

        # 互不重叠且覆盖全部变动格
        flat = [cell for batch in batches for cell in batch]
        assert len(flat) == len(deltas)
        assert set(flat) == set(deltas)

        # 每批守恒，且批内拆不出更小的合格批次
        for batch in batches:
            assert len(batch) >= 4  # 二分图中不存在 2 环
            assert not _has_balanced_proper_subset(deltas, batch)
            row_sum, col_sum = {}, {}
            for r, c in batch:
                row_sum[r] = row_sum.get(r, 0) + deltas[(r, c)]
                col_sum[c] = col_sum.get(c, 0) + deltas[(r, c)]
            assert all(v == 0 for v in row_sum.values())
            assert all(v == 0 for v in col_sum.values())

        # 确定性：同输入重复分解结果一致
        assert decompose_into_cycles(dict(deltas)) == batches
