# 工作记录（草稿）

按时间顺序记录 final 项目的每一步：做了什么、为什么这样做、怎么运行、还有什么没定。
这是原始记录，项目完成后再整理成正式的 README 和方法文档。

---

## 项目目标

为 Virginia 和 Georgia 两个州的每个县（VA 133 个县级单位，GA 159 个县）计算数据中心选址的 suitability 分数并排名。

- 指标：8 个维度、18 个指标，来自 Jane 的 `Virginia_Georgia_八维18指标_FCC更新.xlsx`。
- 权重：分两层。
  - **大权重**：8 个维度之间的权重，由客户的 4 项需求输入动态调整。
  - **小权重**：每个维度内各指标之间的权重。
- 打分：使用 Adelyn 的决策矩阵。

## 整体流程

```
① data_prep           Jane 的县级指标表 → 标准化的长表（每行 = 县 × 指标）
② indicator_scoring   原始值 → 效用分 u (0–100)；小权重 ω → 维度分 D (0–1)
③ dimension_weights   客户 4 项输入 → 大权重 w
④ decision            Score = 100 × Σ w_k · D_k → 排名、Pareto、取舍对比
```

当前进度：④ 完成（含维度内聚合方式的扩展）；①②③ 未开始。Gate 暂时不考虑，在矩阵里先关闭。

## 目录结构

```
final/
├── configs/                  模型配置（维度、指标、锚点、客户输入默认值）
├── data/raw/                 原始数据来源说明（大文件不上传）
├── data/processed/           18 项县级指标表
├── src/dc_locator/
│   ├── data_prep/            ①
│   ├── indicator_scoring/    ②
│   ├── dimension_weights/    ③
│   └── decision/             ④ 决策矩阵
├── scripts/                  一键运行完整流程
├── tests/decision/           ④ 的测试
├── tests/fixtures/           示例请求 JSON
├── outputs/                  运行结果（不进 git）
└── docs/                     文档（本文件）
```

暂时为空的文件夹里放了 `.gitkeep`，以便 git 保留目录结构。

---

## 2026-10-04 第 1 步：决策矩阵从 7 维改为 8 维

### 来源

Adelyn 的 `adelyn_decision` v0.2（`~/Downloads/Adelyn/`）。原代码把 7 个维度和 7 个指标写成常量（`DIMENSION_ORDER`、`REQUIRED_METRICS`），每个维度只能有 1 个指标，不能直接用于 8 维 18 个指标。

### 新位置

- `src/dc_locator/decision/matrix.py`：主体
- `src/dc_locator/decision/__main__.py`：命令行
- `src/dc_locator/decision/__init__.py`：对外接口 `recommend`、`compare_runs`、`run_decision`、`ContractError`

版本号改为 `v0.3`（`schema_version` 和 `model_version` 都是 `v0.3`）。

### 改动

1. **维度和指标由配置驱动**
   - `scoring_config.dimension_order` 决定有哪些维度。
   - `scoring_config.indicators[*].dimension_id` 决定每个指标属于哪个维度。
   - 代码里只保留 `DEFAULT_DIMENSION_ORDER` 作为参考，不用于校验。
   - 新增 `ModelSpec`，从配置中解析出维度列表、指标列表和指标到维度的映射，传给各个函数，替代原来的全局常量。
2. **一个维度可以有多个指标**：校验每个维度至少有 1 个指标，且维度内小权重 `local_weight` 之和为 1。
3. **大权重可以为 0**：例如州内排名时，把能源 / 碳设为 0。
4. **Gate 可以关闭**
   - 在 `constraint_rules` 中设 `"gates_enabled": false`，或直接传 `None`。
   - 关闭后不需要 `project_profile` 和 `evidence_records`，`gate_results` 为空，每个县的 `gate_status = "not_evaluated"`。
   - 分数完整的县全部进入 `conditional` 组参与排名，并在 diagnostics 中说明"本次未做 Gate 检查"。
   - Gate 打开时，Adelyn 原来的逻辑完全不变。
5. **新增诊断**：某个维度在所有候选县上分数相同、且权重大于 0 时，在 diagnostics 中提示"该维度不会改变排名"。预计能源 / 碳在州内会触发这条提示。
6. **输出新增字段**：每个县的推荐记录增加 `gate_status` 和 `dimension_scores`，便于前端展示。
7. **缺失处理**：某个维度分为 null 时，把这个维度的**所有**指标都记入 `missing_metric_ids`。原来的写法只记一个。

### 没有改动的部分

- 打分公式：`Score = Σ_j w_{dim(j)} · ω_j · u_j`，等价于 `100 × Σ_k w_k · D_k`。代码会检查这两种算法的结果是否一致（容差 1e-7）。
- 任何一项缺失，总分即为 null，状态为 `incomplete`，不参与排名；缺失不会被当成 0 或 50。
- 并列排名用竞赛排名法（1, 1, 3），分差 ≤ 1e-8 视为并列。
- Pareto 用原始值和各指标方向判断支配关系。
- 取舍对比：与第 1 名（或第 2 名）逐个指标比较原始值的差。
- `compare_runs`：比较两次运行的输入、Gate 和推荐结果的变化。
- `run_decision`：串联上游各模块的入口。

### 8 维 18 指标的 ID（暂定，目前只在测试中使用）

| dimension_id | 指标 metric_id | 单位 | 方向（暂定） |
|---|---|---|---|
| climate_risk | wildfire_bp_national_pct | fraction | low_better |
| climate_risk | inland_flood_eal_national_pct | fraction | low_better |
| water | baseline_water_stress | aqueduct_index_0_5 | low_better |
| water | future_water_stress_2050 | aqueduct_index_0_5 | low_better |
| land_ecology | low_impervious_share | fraction | high_better（方向待定） |
| land_ecology | protected_gap12_share | fraction | low_better |
| land_ecology | wetland_share | fraction | low_better |
| fiber_connectivity | commercial_fiber_100_20_share | fraction | high_better |
| fiber_connectivity | commercial_fiber_1000_100_share | fraction | high_better |
| workforce_community | labor_force | persons | high_better |
| workforce_community | svi_national_pct | fraction | low_better（默认可能不计分，待定） |
| cooling_climate | cdd65 | degF_day_per_year | low_better |
| cooling_climate | hot_days_over_90f | days_per_year | low_better |
| transportation | interstate_distance_km | km | low_better |
| transportation | rail_distance_km | km | low_better |
| energy_carbon | industrial_electricity_price | USD_per_MWh | low_better |
| energy_carbon | saidi_no_major_events | minutes_per_customer_year | low_better |
| energy_carbon | grid_co2e_intensity | kgCO2e_per_MWh | low_better |

### 测试

`tests/decision/test_matrix.py` 共 25 项，全部通过。

- **Adelyn 原有的 16 项**：全部改写为 8 维版本并保留，包括得分与贡献分解、缺失、真实 0、并列、Pareto、test_only 配置、非 baseline 情景、Gate 的各种情况、`compare_runs`、`run_decision`。
- **新增的 9 项**：
  - 8 维 18 指标的基本打分
  - 维度内小权重是否生效
  - 改变大权重会改变第一名
  - 小权重之和不为 1 时报错
  - 有维度没有指标时报错
  - 大权重为 0 时正常运行
  - "维度分数全部相同"的诊断
  - 关闭 Gate 时正常排名
  - 不传 `constraint_rules` 时等同于关闭 Gate
- `tests/decision/builders.py`：生成合成测试数据。所有指标分默认 40，任何合法的权重组合总分都是 40，方便检查计算是否正确。

### 怎么运行

需要 Python 3.10 或以上，第 1 步不依赖任何第三方库。

```bash
cd final

# 运行测试
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v

# 命令行运行示例（2 个县，Gate 关闭）
PYTHONPATH=src python3 -m dc_locator.decision recommend \
  --request tests/fixtures/decision_request_8d.json \
  --output-dir outputs/demo

# 比较两次运行
PYTHONPATH=src python3 -m dc_locator.decision compare \
  --previous outputs/run_a/decision_output.json \
  --current outputs/run_b/decision_output.json \
  --output outputs/change_report.json
```

示例输出：51107 的冷却维度分更高，总分 43.125，排第 1；51013 总分 40.0，排第 2。其余 7 个维度两个县分数相同，diagnostics 中对这 7 个维度给出"不会改变排名"的提示。

`outputs/demo/` 下会生成 `decision_output.json`、`recommendations.json`、`gate_results.json`、`diagnostics.json`。

---

## 2026-10-04 第 1.5 步：矩阵支持三种维度内聚合方式

### 为什么要改

组员提出：不同维度应该用不同方式把指标合成维度分，而不是全部用加权平均（详见下一节）。第 1 步的矩阵默认维度分 = 加权平均，并且会用这个公式核对上游传来的维度分。几何平均或 min 算出的维度分会被它当成"算错了"而拒绝。

例：野火 u = 90、洪水 u = 10。几何平均 D = √(0.9 × 0.1) = 0.30；按加权平均核对得 0.50，两者对不上。

### 改了什么

1. `scoring_config` 新增可选字段 `dimension_aggregation`，每个维度一个值，默认 `weighted_mean`：
   - `weighted_mean`：D = Σ ω·u / 100
   - `weighted_geometric`：D = Π (u/100)^ω，一项差不能被另一项完全弥补
   - `min`：D = min(u) / 100（只看 ω > 0 的指标），最差的一项说了算
2. 新函数 `aggregate_dimension(method, scores, weights)`，并从 `dc_locator.decision` 导出。第 2 步计算维度分时直接调用它，保证两边用的是同一套公式。
3. 核对方式：原来核对总分（指标贡献之和 = 维度加权和），现在改为**逐个维度**用声明的方法重算维度分，与上游传来的值比对（容差 1e-7），不一致就报错，错误信息会写明是哪个县、哪个维度。
4. 输出：
   - 新增 `dimension_contributions`：每个维度贡献的分数 100·w·D，8 项之和永远等于总分。
   - `metric_contributions`：只有加权平均的维度才拆到指标层（w·ω·u）；几何平均和 min 的维度，指标贡献为 `null`，因为这类公式里单个指标"贡献多少分"没有定义。
5. 校验：未知的聚合方式、或给不存在的维度声明聚合方式，直接报错。

### 测试

共 33 项，全部通过：原有 25 项不变，新增 8 项：

- 几何平均（气候）
- min（水）
- 带权重的几何平均（土地 0.5 / 0.25 / 0.25）
- 所有指标分相等时三种方法结果相同
- 维度贡献之和等于总分，加权平均维度的指标贡献之和等于该维度贡献
- 维度分没有按声明方法计算时报错
- 未知聚合方式报错
- 给不存在的维度声明聚合方式报错

示例命令的结果不变（51107：43.125 分，第 1；51013：40.0 分，第 2），因为示例配置没有声明聚合方式，全部默认为加权平均。

---

## 已确定的第 2 步设计（组员方案 + 修正，尚未写代码）

### 原始值 → 效用分：分段线性函数

```
越低越好： u = 100（x ≤ T）；100 × (L − x)/(L − T)（T < x < L）；0（x ≥ L）
越高越好： u = 0（x ≤ L）；100 × (x − L)/(T − L)（L < x < T）；100（x ≥ T）
```

T 为理想值，L 为不可接受值。作用是统一单位、统一方向（全部越高越好），并设定饱和点。

**不使用 Jane 表里的两州 min-max 标准化值**：那组值没有统一方向，而且换一批县或加一个州，所有分数都会变。

T、L 的依据按可信度分三级：外部标准或公认分级 > 工程或业务逻辑 > 数据分布。锚点必须**先于** swing weighting 确定，因为权重的含义是"从 L 改善到 T 值多少"。

### 计分结构（13 个计分指标 + 5 个提示指标）

| 维度 | 计分指标（ω 暂定） | 聚合方式 | 提示指标 |
|---|---|---|---|
| 气候 | 野火 0.5、洪水 0.5 | weighted_geometric | — |
| 水 | 当前、2050 水压力 | min | 水压力变化量（2050 − 当前） |
| 土地 | 低不透水 0.5、保护地 0.25、湿地 0.25 | weighted_geometric | — |
| 光纤 | 1000/100 覆盖率 1.0 | — | 100/20 覆盖率 |
| 劳动力 | ln(劳动力) 1.0 | — | SVI 等级 |
| 制冷 | CDD65 1.0 | — | >90°F 天数分级 |
| 交通 | Interstate 0.7、铁路 0.3 | weighted_mean | — |
| 能源 | 电价 0.25、SAIDI 0.35、碳 0.40 | weighted_mean | 只用于州间比较 |

对组员原方案的修正：土地原公式 `u1 × √(u2 × u3)` 的指数之和为 2，三项都是 0.8 时结果只有 0.64，会让土地维度系统性偏低。改为指数之和为 1 的加权几何平均 `u1^0.5 · u2^0.25 · u3^0.25`。

### 锚点初稿（待团队确认）

| 指标 | 方向 | T | L | 依据 |
|---|---|---|---|---|
| 野火全国百分位 | 低优 | 0 | 1.0 | 百分位的自然端点 |
| 洪水损失率全国百分位 | 低优 | 0 | 1.0 | 同上 |
| 基线 / 2050 水压力 | 低优 | 1.0 | 4.0 | Aqueduct 分级（低 / 极高的分界） |
| 低不透水比例 | 高优（方向待定） | 0.95 | 0.25 | 业务逻辑 + 数据分布 |
| GAP1/2 保护地比例 | 低优 | 0 | 0.50 | 半个县受保护视为极限 |
| 湿地比例 | 低优 | 0 | 0.60 | 数据上限附近 |
| 1000/100 光纤覆盖率 | 高优 | 0.90 | 0 | 90% 以上视为饱和 |
| ln(劳动力人数) | 高优 | ln(50,000) | ln(2,000) | 5 万人以上视为充足 |
| CDD65 | 低优 | 500 | 2,500 | 数据分布（两州 276–2,499） |
| 到 Interstate 距离 | 低优 | 5 km | 60 km | 业务逻辑 + 数据 p90 |
| 到铁路距离 | 低优 | 2 km | 30 km | 同上 |
| 工业电价 | 低优 | 50 | 120 USD/MWh | 全美州级电价的大致区间 |
| SAIDI | 低优 | 100 | 400 分钟/年 | 全美 utility 的大致区间 |
| 电网碳强度 | 低优 | 100 | 650 kg/MWh | 低碳电网 / 煤电为主的电网 |

注意：几何平均和 min 遇到 u = 0 会让整个维度变成 0，所以这三个维度的 L 尽量设在真正不可接受的位置；另外会提供可选的效用分下限（如 1 分）。

### 小权重的确定方法

用 **Swing Weighting**（组员建议），取代 Weights 指南里的"ROC + CRITIC"：先定锚点，再比较"把每个指标从 L 改善到 T，哪个最有价值"，最有价值的给 100 分，其余相对打分，最后归一化。CRITIC 和 entropy 降级为第 3b 步的诊断对照（理由：数据波动大不代表更重要）。上表的 ω 是暂定值，团队打分后直接替换配置。

---

## 之前讨论中已经形成、但还没有写进代码的设计

以下内容见 Hackson 根目录的讨论文档，后续步骤会实现：

- `客户权重输入_4项_v0.2.md`：4 项客户输入（冷却方式、业务延迟敏感度、可靠性要求、优先目标）、乘数，以及大权重公式 `w_k = w0_k × M_k / Σ(w0 × M)`。
- 州内排名时，能源 / 碳的大权重设为 0（这三个指标在州内是同一个值）；能源 / 碳只用于州间比较。
- `camille_权重敏感性测试.py`：临时原型，用真实数据验证了 4 项输入会改变排名。它没有使用这个矩阵，锚点和小权重都是临时值。

## 待定问题

1. 18 个指标的 ID 是否需要改名。
2. 低不透水比例的方向（空地多是优点，还是意味着占用绿地）。
3. SVI 是否计分，计分时方向如何。
4. 效用锚点：暂定两州合并的 p10/p90，百分位类指标用 0 和 1。
5. 小权重：等分、ROC + CRITIC 组合，还是其他方法。
6. 大权重的基准值 w0 和各项乘数，需要团队确认（可用 AHP）。
7. 缺失值政策：Weights 指南主张在可用指标中重新归一化，Jane 要求不逐县重新分配权重。目前矩阵按"缺失则不打分"处理。
8. Gate 什么时候接回来。

## 下一步

按顺序：

1. **第 3a 步**：`src/dc_locator/dimension_weights/`
   - 基准权重 w0：从 AHP 比较矩阵计算（几何平均法和特征向量法，检查 CR）；
   - 客户 4 项输入的乘数调整；
   - 州内（能源设为 0）和州间两种模式；
   - 单维度上限 0.40；
   - 输出 `dimension_weights` 和调整记录。
2. **第 2 步**：`src/dc_locator/indicator_scoring/`，分段效用函数 + 维度内聚合 + 提示指标，锚点写进 `configs/`。
3. **第 3b 步**：交叉检验（AHP / ROC / 等权 / CRITIC 对比）、SMAA 稳健性检验、有效权重分析。
