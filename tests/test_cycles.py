"""批次切分（有向环分解）的单元测试。"""

from itertools import combinations

from app.cycles import decompose_into_cycles


def _is_minimal_batch(deltas, batch_cells):
    """环上任何非空真子集都不可能同时保持行/列小计守恒。"""
    cells = list(batch_cells)
    for size in range(1, len(cells)):
        for sub in combinations(cells, size):
            rows, cols = set(), set()
            row_sum = col_sum = 0
            for r, c in sub:
                rows.add(r)
                cols.add(c)
            # 真子集守恒 <=> 其中每个行、列标签上的 delta 之和为 0
            if all(
                sum(deltas[(rr, cc)] for (rr, cc) in sub if rr == r) == 0
                for r in rows
            ) and all(
                sum(deltas[(rr, cc)] for (rr, cc) in sub if cc == c) == 0
                for c in cols
            ):
                return False
    return True


def _check_partition(deltas, batches):
    changed = {cell for cell, d in deltas.items() if d != 0}
    flat = [cell for batch in batches for cell in batch]
    assert len(flat) == len(changed)
    assert set(flat) == changed
    for batch in batches:
        assert _is_minimal_batch(deltas, batch)


def test_single_four_cycle():
    # 2x2 矩形上 +1/-1 交替：唯一的最小批次就是这 4 格
    deltas = {
        ("A", "x"): +1, ("A", "y"): -1,
        ("B", "x"): -1, ("B", "y"): +1,
    }
    batches = decompose_into_cycles(deltas)
    assert len(batches) == 1
    assert set(batches[0]) == {("A", "x"), ("A", "y"), ("B", "x"), ("B", "y")}
    _check_partition(deltas, batches)


def test_six_cycle_on_three_by_three():
    # 真正的 6 环：3 个行节点、3 个列节点各出现两次，不可再拆
    deltas = {
        ("A", "x"): +1, ("A", "y"): 0, ("A", "z"): -1,
        ("B", "x"): -1, ("B", "y"): +1, ("B", "z"): 0,
        ("C", "x"): 0, ("C", "y"): -1, ("C", "z"): +1,
    }
    batches = decompose_into_cycles(deltas)
    assert len(batches) == 1  # 6 格构成一条不可再拆的 6 环
    assert len(batches[0]) == 6
    _check_partition(deltas, batches)


def test_two_overlapping_cycles_3x4():
    # 8 个变动格；行 A 有 2 入 2 出，两条 4 环共享节点 A
    deltas = {
        ("A", "x"): +1, ("A", "y"): -1, ("A", "z"): +1, ("A", "w"): -1,
        ("B", "x"): -1, ("B", "y"): +1,
        ("C", "z"): -1, ("C", "w"): +1,
    }
    batches = decompose_into_cycles(deltas)
    assert len(batches) == 2
    assert sorted(len(b) for b in batches) == [4, 4]
    _check_partition(deltas, batches)


def test_two_disjoint_four_cycles_4x4():
    deltas = {
        ("A", "x"): +1, ("A", "y"): -1,
        ("B", "x"): -1, ("B", "y"): +1,
        ("C", "z"): +1, ("C", "w"): -1,
        ("D", "z"): -1, ("D", "w"): +1,
    }
    batches = decompose_into_cycles(deltas)
    assert len(batches) == 2
    assert all(len(b) == 4 for b in batches)
    _check_partition(deltas, batches)


def test_deterministic_output():
    deltas = {
        ("A", "x"): +1, ("A", "y"): -1, ("A", "z"): +1, ("A", "w"): -1,
        ("B", "x"): -1, ("B", "y"): +1,
        ("C", "z"): -1, ("C", "w"): +1,
    }
    shuffled = dict(list(deltas.items())[::-1])
    assert decompose_into_cycles(deltas) == decompose_into_cycles(shuffled)
