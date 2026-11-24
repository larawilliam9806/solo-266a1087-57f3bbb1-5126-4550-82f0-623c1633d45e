"""把所有变动格分解为互不重叠的最小批次。

建模：
  - 行（作业区）与列（货类）为二分图两侧节点；
  - 变动格 (r, c)，增量 +1 对应有向边 行r -> 列c，减量 -1 对应 列c -> 行r；
  - 行/列小计不变  <=>  每个节点的入度等于出度（平衡有向图）。

平衡有向图中的边可以分解为若干条边不相交的简单有向环。二分图中的环
长度至少为 4（即 2x2 矩形上 +1/-1 交替），且简单环的任何非空真子集都
不可能仍保持每个节点出入平衡，因此每条环就是一个"无法再拆"的最小批次。
"""

from collections import defaultdict
from typing import Dict, List, Tuple

Cell = Tuple[str, str]


def decompose_into_cycles(deltas: Dict[Cell, int]) -> List[List[Cell]]:
    """把变动格分解为边不相交、覆盖全部变动格的简单有向环。

    参数:
        deltas: {(row, col): delta}，delta 仅允许 -1 / 0 / +1，0 会被忽略。
                要求每个行标签、列标签上的 delta 之和均为 0（小计不变）。

    返回:
        批次列表，每个批次是构成一条简单有向环的格子列表；
        各批次互不重叠，且并集恰好等于全部变动格。结果确定（与输入
        字典的迭代顺序无关），便于批号稳定。
    """
    # 邻接表：节点用 ("R", 行标签) / ("C", 列标签) 区分两侧。
    adj: Dict[tuple, List[tuple]] = defaultdict(list)
    for (r, c), d in sorted(deltas.items()):
        if d == 0:
            continue
        if d > 0:
            u, v = ("R", r), ("C", c)
        else:
            u, v = ("C", c), ("R", r)
        adj[u].append((v, (r, c)))

    batches: List[List[Cell]] = []

    # 沿未使用的边行走，回到当前路径上的节点即闭合出一条简单环；
    # 闭合后若还有剩余边则继续行走，直到所有边都被某个环收走。
    while adj:
        start = min(adj.keys(), key=lambda n: (n[0], n[1]))
        path_nodes: List[tuple] = [start]
        on_path: Dict[tuple, int] = {start: 0}
        path_edges: List[Cell] = []
        node = start

        while True:
            nxt, cell = adj[node].pop()
            if not adj[node]:
                del adj[node]
            path_edges.append(cell)

            if nxt in on_path:
                # 闭合：on_path[nxt] 之后的边构成一条简单有向环。
                idx = on_path[nxt]
                cycle = path_edges[idx:]
                batches.append(cycle)

                # 环之前的前缀仍是当前有效游走，裁掉环上的节点与边。
                del path_edges[idx:]
                for old_node in path_nodes[idx + 1:]:
                    del on_path[old_node]
                del path_nodes[idx + 1:]
                node = nxt
            else:
                on_path[nxt] = len(path_nodes)
                path_nodes.append(nxt)
                node = nxt

            if node not in adj:
                # 平衡图保证只有起点才会走死；此时该起点的边已全部成环。
                break

    _assert_partition(deltas, batches)
    return batches


def _assert_partition(deltas: Dict[Cell, int], batches: List[List[Cell]]) -> None:
    """防御性自检：批次两两不相交、覆盖全部非零变动格、环上小计守恒。"""
    changed = {cell for cell, d in deltas.items() if d != 0}
    seen: set = set()
    for batch in batches:
        batch_set = set(batch)
        if len(batch_set) != len(batch):
            raise RuntimeError("batch contains duplicate cells")
        if seen & batch_set:
            raise RuntimeError("batches overlap")
        seen |= batch_set

        row_sum: Dict[str, int] = defaultdict(int)
        col_sum: Dict[str, int] = defaultdict(int)
        for r, c in batch:
            row_sum[r] += deltas[(r, c)]
            col_sum[c] += deltas[(r, c)]
        if any(s != 0 for s in row_sum.values()):
            raise RuntimeError("batch breaks row subtotals")
        if any(s != 0 for s in col_sum.values()):
            raise RuntimeError("batch breaks column subtotals")

    if seen != changed:
        raise RuntimeError("batches do not cover every changed cell")
