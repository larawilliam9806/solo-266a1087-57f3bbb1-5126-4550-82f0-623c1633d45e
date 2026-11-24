# 港口整吨运量底表分批换发 API

同一月份的整吨运量底表需要分批换发：作业区（行）与货类（列）的小计已经
签核，因此换表全程两组小计都不能变。本服务基于 FastAPI + SQLite，提供
现用表登记、换发申请、最小批次切分、按批号确认与对外查询。

## 业务规则与实现对应

| 规则 | 实现 |
| --- | --- |
| 同月先登记现用表 | `POST /months/{month}/register`，重复登记返回 409 |
| 换发提交行列相同的新表 | 校验行（作业区）、列（货类）标签序列与现用表完全一致，否则 422 |
| 每格最多增减 1 吨 | 逐格比较新旧值，`abs(Δ) > 1` 返回 422 |
| 各行各列小计仍须对上 | 校验每个行标签、列标签上的 Δ 之和均为 0，否则 422 |
| 变动格分成互不重叠的批次 | 有向环分解（见下），批次间格子不相交且覆盖全部变动格 |
| 每批单独更新后两组小计都不变 | 每条环上每个行/列节点都各有一条 +1、一条 -1，天然守恒 |
| 批内无法再拆出更小的合格批次 | 简单有向环不存在保持出入平衡的非空真子集（最小性） |
| 按任意顺序凭批号确认 | `POST /replacements/{id}/batches/{no}/confirm`，批号独立可乱序 |
| 查询只显示已确认格的新值 | 未确认格读现用表值，已确认格读新表值，逐格合并 |
| 最后一批确认后与新表完全一致 | 末批确认时申请置为 `confirmed`，此时所有格子均已确认 |
| 重复确认不重复写入 | 批次已确认时直接返回 `already_confirmed=true`、`written=0` |
| 写入失败各格保留原值 | 确认在单事务内逐格更新，任何异常整批回滚，返回 500 |
| 有未确认批次时退回新申请 | 同月存在 `pending` 申请时新申请返回 409 |

### 批次切分为什么是有向环

把行节点与列节点放在二分图两侧：

- 变动格 `(r, c)` 的 Δ=+1 画有向边 `行r → 列c`，Δ=-1 画 `列c → 行r`；
- 行/列小计不变 ⇔ 每个节点入度 = 出度，即一张平衡有向图；
- 平衡有向图的边可分解为若干条**边不相交的简单有向环**（`app/cycles.py`
  用沿边游走、遇已访问节点即闭合取环的算法实现）；
- 二分图中的环长度至少为 4，对应 2×2 矩形四角 +1/−1 交替；环越长
  （如 6 环、8 环）同样是不可再拆的最小批次；
- 分解结果与输入字典顺序无关，批号稳定可复现。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/months/{month}/register` | 登记某月现用表 |
| POST | `/months/{month}/replacements` | 提交换发，返回切分好的批次 |
| GET  | `/months/{month}/table` | 当前对外可见的表（仅已确认格显示新值）+ 两组小计 |
| GET  | `/replacements/{id}` | 换发申请状态与确认进度 |
| GET  | `/replacements/{id}/batches` | 批次清单及每批格子 |
| POST | `/replacements/{id}/batches/{batch_no}/confirm` | 确认一批（幂等、原子） |
| GET  | `/health` | 健康检查 |

请求体统一为：

```json
{
  "rows": ["area-a", "area-b"],
  "cols": ["cargo-x", "cargo-y"],
  "matrix": [[10, 5], [4, 8]]
}
```

矩阵为非负整数（整吨），行列标签各自唯一，且矩阵尺寸必须与标签一致。

## 本地运行（Docker Compose）

```bash
docker compose up --build
# API: http://localhost:8000  文档: http://localhost:8000/docs
```

SQLite 数据文件保存在命名卷 `port_data` 内的 `/data/port_tables.db`
（可用环境变量 `DB_PATH` 覆盖）。

## 本地运行（裸 Python）

```bash
pip install -r requirements.txt
DB_PATH=./data/port_tables.db uvicorn app.main:app --reload
```

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

测试覆盖：环分解的最小性/不相交/确定性、登记与重复登记、同形与 ±1 吨
校验、两组小计校验、乱序确认、查询遮蔽、重复确认幂等、写入失败整批
回滚、未确认批次阻止新申请、末批确认后与新表一致。

## 快速示例

```bash
# 1. 登记现用表
curl -X POST localhost:8000/months/2026-11/register \
  -H 'Content-Type: application/json' \
  -d '{"rows":["area-a","area-b"],"cols":["cargo-x","cargo-y"],
       "matrix":[[10,5],[4,8]]}'

# 2. 提交换发（四角 +/-1，小计不变）-> 返回 1 个批次、4 个格子
curl -X POST localhost:8000/months/2026-11/replacements \
  -H 'Content-Type: application/json' \
  -d '{"rows":["area-a","area-b"],"cols":["cargo-x","cargo-y"],
       "matrix":[[11,4],[3,9]]}'

# 3. 确认批次 1
curl -X POST localhost:8000/replacements/1/batches/1/confirm

# 4. 查询：全部格子已是新值
curl localhost:8000/months/2026-11/table
```

## 数据模型

- `month`：月份及其行列标签骨架；
- `live_cell`：现用表逐格值，随批次确认被原子更新；
- `replacement`：换发申请，`pending` / `confirmed`；
- `replacement_cell`：新表逐格存底，含登记时的旧值、新值与确认标记；
- `batch` / `batch_cell`：批次及其格子归属。

写事务使用 `BEGIN IMMEDIATE`，并发确认/申请在 SQLite 层串行排队，
避免写冲突；确认时还会带旧值做条件更新，现用表被意外改动时整批失败
而不是静默覆盖。
