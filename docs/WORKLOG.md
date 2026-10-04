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

当前进度：④ 完成，已改为只接收 n × 8 维度分；② 的聚合函数已完成，其余 ①②③ 未开始。Gate 暂时不考虑，在矩阵里先关闭。

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
| fiber | commercial_fiber_100_20_share | fraction | high_better |
| fiber | commercial_fiber_1000_100_share | fraction | high_better |
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

> 已被第 1.6 步取代：矩阵不再处理维度以下的计算，`aggregate_dimension()` 移到了 `indicator_scoring/`。保留本节作为决策过程的记录。

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

## 2026-10-04 第 1.6 步：矩阵简化为只接收 n × 8 维度分（取代第 1.5 步的做法）

### 为什么改

第 1.5 步让矩阵去核对"维度分是不是按声明的方式由指标算出来的"，等于让矩阵管到了维度以下的层级。讨论后确定：**矩阵只做一件事——n × 8 的维度分矩阵乘以 8 个权重**。维度以下怎么算（分段函数、聚合方式）全部归第 2 步。

理由：
1. 每层只做一件事。以后改分段函数或聚合方式，不需要动矩阵。第 1.5 步就是因为没分清这一点，矩阵才被迫修改。
2. 好讲：报告里矩阵就是"县 × 8 维度的表 + 一行权重"。
3. 唯一的损失是矩阵不再核对维度分是否算对，这个核对改由第 2 步自己的测试负责。

### 改了什么

1. `recommend(dimension_scores, scoring_config, context, project_profile=None, constraint_rules=None, evidence_records=None)`：
   - 不再需要 `metric_results` 和 `indicator_scores`；
   - Gate 相关参数都是可选的，不传就关闭。
2. `dimension_scores` 每条记录：`candidate_id`、可选的 `candidate_name`、`scores = {维度: D 或 null}`。原来的 `dimension_order`、`score_status`、`missing_metric_ids` 字段不再需要，缺失由矩阵自己判断。
3. `scoring_config` 只需要 `dimension_order`、`dimension_weights`、`version`、`status`、`preference_profile_id`，不再包含 `indicators` 和 `dimension_aggregation`。
4. 输出：
   - `dimension_contributions`（100·w·D，之和等于总分）；
   - `dimension_weights_used`；
   - `missing_dimension_ids`（取代 `missing_metric_ids`）；
   - **Pareto 改为在 8 个维度分上判断**（原来是 18 个原始值）；
   - **取舍对比改为维度分之差和加权分差**（原来是原始值之差）。
   - 删除 `metric_contributions`。
5. `run_decision(scoring_config, context, dimension_scores=None, compute_dimension_scores_fn=None, ...)` 也相应简化。
6. 版本号升为 `v0.4`。
7. 第 1.5 步写的 `aggregate_dimension()` 移到 `src/dc_locator/indicator_scoring/aggregation.py`，第 2 步直接使用。矩阵中的 `dimension_aggregation` 字段和核对逻辑全部删除。

### 测试

共 36 项，全部通过：

- `tests/decision/test_matrix.py`（28 项）：
  - 打分 12 项：等分 40、手算核对、动态权重改变第一名、缺失、真实 0、权重为 0、常数维度诊断、并列、Pareto、取舍对比、3 维配置也能运行、real 模式拒绝 test_only 配置；
  - 输入校验 5 项：权重和、分数范围、维度齐全、重复县、非 baseline 情景；
  - Gate 开关 2 项；
  - Gate 原有逻辑 6 项；
  - 运行比较 3 项。
- `tests/indicator_scoring/test_aggregation.py`（8 项）：加权平均、几何平均（野火 90 / 洪水 10 → 0.30）、带权重的几何平均、min、min 忽略权重为 0 的指标、0 分会让几何平均和 min 清零、分数相等时三种方法结果相同、非法输入。

### 示例

`tests/fixtures/decision_request_8d.json`：3 个虚构县，使用默认州内权重（能源 0；水 0.267、气候 0.200、光纤 0.167、土地 0.133、劳动力 0.100、制冷 0.067、交通 0.067）。

| 排名 | 县 | 总分 | Pareto |
|---|---|---|---|
| 1 | A（乡村、水资源充足） | 62.17 | 非支配 |
| 2 | B（城市、网络发达） | 60.17 | 非支配 |
| 3 | C（各维度均衡，全部 0.6） | 60.00 | 非支配 |

三个县都是非支配：各有所长，排序完全由权重决定。

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

## 2026-10-04 方法框架定稿：三方面如何融合（Choquet + DEMATEL + 相关矩阵）

讨论确定（来源：Adelyn 提出的 8×8 矩阵设想 + 本次讨论）：

```
① 客户需求 4 项输入 ──────────────► φ：8 个维度的重要性（动态调整）            第 3a 步
② A 相关矩阵（数据，全州共用）──┐                                              第 3d 步
③ B 因果矩阵（团队打分，DEMATEL）┴──► I：8×8 交互矩阵（协同 / 重复）            第 3c、3d 步
④ 每个县的 1×8 维度分 D ──► 2-additive Choquet：Score = Σφ·D − ½Σ I_kl·|D_k − D_l|   第 4' 步
```

- **φ** 随客户输入变化；**I** 对所有县相同；**D** 每个县不同。所有 I = 0 时，Choquet 等于加权求和。
- A 只说明"同起同落"，B 只说明"影响强弱"，两者都分不出协同还是重复。所以 I 的**正负由团队标注**，**大小由 A 和 B 合成**。
- 实施顺序：3a 客户输入 → φ；3c DEMATEL；4' matrix 加 Choquet；2 分段函数 → D；3d 相关矩阵 + 合成 I；3b 交叉检验与 SMAA。

---

## 2026-10-04 第 3a 步：客户输入 → 维度权重 φ

### 文件

- `src/dc_locator/dimension_weights/`：
  - `ahp.py`：AHP 计算；
  - `customer.py`：客户调整、模式、上限；
  - `__init__.py`：对外函数 `compute_dimension_weights()`；
  - `__main__.py`：命令行；
  - `README.md`。
- `configs/dimension_weights.json`：所有判断类参数，包括 AHP 两两比较、4 项输入的选项和乘数、州内排除的维度、上限。
- `tests/dimension_weights/test_weights.py`：17 项测试。
- 新增依赖：numpy、pandas、openpyxl（`requirements.txt`、`pyproject.toml`）。

### 方法

1. **基准权重 w0 用 AHP**（Saaty 1980）：
   - 8×8 两两比较，Saaty 1–9 标度；
   - 主方法用最大特征向量，行几何平均法作交叉核对（Crawford & Williams 1985），差距 > 0.01 时报警；
   - CR = CI/RI，RI(8) = 1.41，CR ≥ 0.10 拒绝；
   - 多人判断用 AIJ 逐格几何平均合并（Forman & Peniwati 1998）。
2. **客户调整**：w_k = w0_k·M_k / Σ(w0·M)，M_k 是客户选项作用在维度 k 上的乘数之积。等价于把 AHP 的每个比值 w_k/w_l 乘以 M_k/M_l，结果仍是比例尺度的权重。
3. **模式**：
   - `within_state`（州内排县）：能源 / 碳设为 0 后重新归一化；
   - `cross_state`（州间比较）：8 个维度全部保留。
4. **上限**：单维度不超过 0.40，超出部分按比例分给其他维度，反复处理直到没有维度超限。
5. **输出**：
   - 最终权重；
   - 参考权重（默认客户在同一模式下的权重）；
   - 相对参考权重的变化；
   - 每个乘数的记录；
   - 被上限截住的维度；
   - AHP 诊断（λ_max、CI、CR、各人 CR、两种方法的差距、警告）。

### 结果（AHP 初稿，单人填写，待团队替换）

λ_max = 8.080，CR = 0.008，两种方法差距 0.0009。

| 维度 | AHP 基准（8 维） | 州内（默认客户） |
|---|---|---|
| 水 | 0.237 | 0.313 |
| 气候 | 0.137 | 0.182 |
| 光纤 | 0.130 | 0.172 |
| 土地 | 0.080 | 0.106 |
| 制冷 | 0.070 | 0.093 |
| 劳动力 | 0.060 | 0.079 |
| 交通 | 0.041 | 0.054 |
| 能源 | 0.245 | 0 |

例：蒸发冷却 + 可持续优先时，水的权重在上限前为 0.515，被截到 0.40，其余维度按比例上调。

### 测试（17 项）

- **AHP**：
  - 完全一致的矩阵能还原真实权重，且 CR = 0；
  - 初稿 CR < 0.1，两种方法差距 < 0.01；
  - 不一致的矩阵被拒绝；
  - 互反矩阵构造、标度范围和缺对的检查；
  - 两人判断按几何平均合并（4 和 1 → 2）；
  - 全 1 矩阵得到均匀权重。
- **客户调整**：
  - 默认输入等于参考权重；
  - 州内模式排除能源并重新归一化；
  - 州间模式保留全部 8 维；
  - 每个选项都让目标维度朝正确方向变化；
  - 比例尺度保持不变（光纤 / 水的比值恰好乘以 1.6）；
  - 全部 72 种组合 × 2 种模式，权重之和都为 1 且不超过上限；
  - 上限按比例重新分配；
  - 不可行的上限报错；
  - 未知输入或选项报错；
  - 乘数记录正确；
  - 替换 AHP 判断后基准权重随之改变。

全部测试共 53 项，全部通过。

---

## 2026-10-04 合并组员的 Gate 模块（PR #1）

推送第 3a 步时发现远端多了组员合并的 PR #1：`src/dc_locator/gates/virginia/`，包括 Gate 引擎、数据和 `gate_runner.py`，共 27 个文件，没有改动其他任何文件。已在本地合并，测试全部通过后推送。之后需要决定这个 Gate 模块和决策矩阵里 Adelyn 原有的 Gate 逻辑怎么衔接（目前两者互不调用）。

---

## 2026-10-04 第 3c 步：DEMATEL 因果矩阵（B）

### 文件

- `src/dc_locator/interactions/`：
  - `dematel.py`：DEMATEL 计算；
  - `__init__.py`：`run_dematel()`、`load_config()`；
  - `__main__.py`：命令行；
  - `README.md`。
- `configs/interactions.json`：DEMATEL 打分（单人初稿，每个非零分都附一句因果理由）。
- `tests/interactions/test_dematel.py`：8 项测试。

### 方法

参考 Gabus & Fontela（1972）、Si 等（2018）的综述：

1. 每人填 8×8 直接影响分（0–4），多人取平均得 Z；
2. X = Z / s，s = max(最大行和, 最大列和)；
3. T = X(I − X)⁻¹，即直接影响加上所有间接链条；
4. r = T 的行和（施加影响），c = 列和（受到影响）；r + c 为中心度，r − c > 0 为原因、< 0 为结果；
5. α = T 的平均值，T 中大于 α 的连线画进因果关系图；
6. 另外输出 `pairwise_strength`：每一对的 (t_kl + t_lk) ÷ 所有对中的最大值，范围 0–1，供第 3d 步与相关矩阵合成。

收敛检查：X 的谱半径 ≥ 1 时直接报错（这种情况下 (I − X)⁻¹ 不存在）。

### 结果（初稿）

- **原因**：气候（r − c = +1.146）、制冷（+0.599）、交通（+0.310）、土地（+0.087）。
- **结果**：水（−1.316）、能源（−0.476）、光纤（−0.343）、劳动力（−0.007）。
- **最强的总影响**：气候 → 水 0.527，制冷 → 水 0.440，制冷 → 能源 0.395，气候 → 能源 0.371。
- **一句话**：气候是根源，水和能源是它的影响落点。
- **最强的双向联系**：交通 ↔ 劳动力（1.00）、光纤 ↔ 劳动力（0.999）、气候 ↔ 水（0.973）、气候 ↔ 能源（0.885）。

### 测试（8 项）

- 2×2 手算例（T = [[1, 2], [1, 1]]，a 为原因、b 为结果）；
- 间接链条 a → b → c 在 T 中体现为 a → c；
- r − c 之和为 0；
- 初稿中气候是最大原因、水是最大结果；
- 多人打分取平均；
- 非法打分报错；
- 不收敛的矩阵报错；
- `pairwise_strength` 对称、范围 0–1、最大值为 1。

一个测试原本假设最强的一对是"气候–水"，实际是"交通–劳动力"，因为 `pairwise_strength` 把两个方向相加，而交通和劳动力互相影响。代码是对的，已修正测试。

全部测试共 61 项，全部通过。

---

## 2026-10-04 第 4′ 步：决策矩阵加入 2-additive Choquet 打分

### 公式

```
Score_i = 100 × [ Σ_k φ_k·D_ik − ½ Σ_{k<l} I_kl·|D_ik − D_il| ]
```

这是 2-additive Choquet 积分的 Shapley 交互形式（Grabisch 1997；Marichal 2000）：

- φ 为维度权重（Shapley 重要性），之和为 1；
- I_kl ∈ [−1, 1] 为交互指数：> 0 表示互补（两个维度失衡要扣分），< 0 表示重复（两个维度同时高不重复加分）；
- 没有交互时，公式退化为加权求和。

### 单调性条件（必要且充分）

对每个维度 k：φ_k ≥ ½ Σ_l |I_kl|。

推导：Möbius 表示下 m_k = φ_k − ½ Σ_l I_kl，m_kl = I_kl。单调的充要条件是：对任意 k 和任意不含 k 的集合 S，m_k + Σ_{l∈S} m_kl ≥ 0。最坏情况是 S 取所有 I_kl < 0 的维度，代入化简后正好得到 φ_k − ½ Σ_l |I_kl| ≥ 0。

违反时 matrix 直接报错，保证"任一维度分变好，总分不会下降"。

### 代码改动（`src/dc_locator/decision/matrix.py`）

- `scoring_config.interactions`（可选）：`[{"dimensions": [k, l], "value": I_kl}]`。校验内容：维度存在、两个维度不同、同一对不重复、取值在 [−1, 1]、满足单调性条件。
- 每个县的输出新增：
  - `interaction_contributions`：每个交互贡献的分数 −50·I·|D_k − D_l|，标注互补或重复；
  - `scoring_model`：`weighted_sum` 或 `choquet_2additive`。
  - 维度贡献加交互贡献，恰好等于总分。
- 常数维度诊断：如果该维度参与了交互，改为提示"交互项仍随县变化"，因为此时它不再是对排名完全没有作用。

### 测试（`tests/decision/test_choquet.py`，10 项）

- 互补：φ = (0.5, 0.5)、I = +0.4 时，均衡县 (0.5, 0.5) 得 50，失衡县 (0.9, 0.1) 得 34，均衡县排第一；
- 重复：I = −0.4 时，失衡县得 66；
- I = 0 时等于加权求和；
- **与独立实现的 Grabisch min/max 形式核对**：8 维、4 个交互、20 个随机县，结果完全一致；
- 维度贡献加交互贡献等于总分；
- 边界：全 0 得 0 分，全 1 得 100 分；
- 违反单调性条件或交互值超出范围时报错；
- **200 次随机测试**：任一维度提高后总分不下降；
- 非法交互项报错（同一维度、未知维度、同一对重复）；
- 常数维度参与交互时的诊断提示。

### 示例

`tests/fixtures/decision_request_8d_choquet.json`：原来 3 个示例县，加上 3 个交互（水–制冷 +0.10、光纤–劳动力 −0.10、交通–劳动力 −0.06）。

| 县 | 加权求和 | Choquet |
|---|---|---|
| A（乡村） | 62.17 | 62.12 |
| B（城市） | 60.17 | 60.07 |
| C（均衡） | 60.00 | 60.00 |

排名不变：示例交互较小，且均衡县不受影响。真实的交互强度在第 3d 步由数据和团队判断确定。

全部测试共 71 项，全部通过。

---

## 2026-10-04 合并组员的 Georgia Gate 模块（PR #2）

推送第 4′ 步时远端多了 PR #2：`src/dc_locator/gates/georgia/`，共 18 个文件，没有改动其他文件。已合并，测试全部通过。

---

## 2026-10-04 第 1 步（数据）+ 第 2 步：分段效用函数 → 维度分 D

### 指标 ID 和维度 ID 统一为 Jane 的命名

Jane 的工作簿下方已有指标定义表，包括 18 个 ID 和所属维度，以此为准：

- 本文件第 1 步表格中我自拟的指标 ID 全部作废，以 `src/dc_locator/data_prep/__init__.py` 的 `METRIC_IDS` 为准；
- 维度 `fiber_connectivity` 改名为 `fiber`，全仓库已替换（gates 目录除外）。

### 数据整理（`src/dc_locator/data_prep/`）

- 原始文件：`data/raw/virginia_georgia_8d18_indicators_fcc.xlsx`（Jane 的 FCC 更新版，200 KB），并附 `data/raw/README.md` 说明来源。
- 输出：`data/processed/county_indicators_va_ga.csv`，共 292 行（VA 133、GA 159），包括 FIPS、县名、州、土地面积、18 项原始值，以及质量提示和覆盖率。
- 读取时的检查：按表头核对指标列的位置；FIPS 必须是唯一的 5 位编码；不能有缺失值（实际为 0）。

### 指标打分（`src/dc_locator/indicator_scoring/`）

- `utility.py`：分段线性效用函数。
  - 越低越好：u = 100（x ≤ T）、100·(L − x)/(L − T)、0（x ≥ L）；越高越好同理；
  - `transform="ln"` 时对数值和两个锚点同时取对数（劳动力）；
  - 可选指数形状（Kirkwood 1997），供敏感性分析使用；
  - 可选效用下限，默认 0。
- `configs/indicator_scoring.json`：15 个计分指标（方向、T、L、锚点依据）、8 个维度（聚合方式和维度内权重）、4 个提示指标（计算公式和分级）。
- `__init__.py`：`score_counties()` 依次计算效用、维度分和提示指标；`zero_utility_report()` 统计每个指标得 0 分和满分的县数；`dimension_score_records()` 生成 matrix 的输入。

### 用真实数据检查锚点

| 指标 | 得 0 分的县数 | 判断 |
|---|---|---|
| 2050 水压力 | VA 12 | 指数 ≥ 4 是 Aqueduct 官方的"极高"等级，保留；因为取 min，这些县的水维度为 0 |
| 低不透水比例 | VA 15（多为独立市） | 城市核心区没有建园区的空地，保留 |
| 劳动力 | GA 11、VA 2 | 不足 2,000 人，保留 |
| Interstate / 铁路距离 | 每州最多 17 | 交通维度是加权平均，另一项可以补偿 |

### 结果（维度分中位数）

| 维度 | VA | GA |
|---|---|---|
| 气候 | 0.647 | 0.513 |
| 水 | 0.316 | 0.633 |
| 土地 | 0.900 | 0.874 |
| 光纤 | 0.416 | 0.704 |
| 劳动力 | 0.591 | 0.496 |
| 制冷 | 0.694 | 0.287 |
| 交通 | 0.834 | 0.696 |
| 能源（州内常数） | 0.583 | 0.627 |

### 测试（21 项）

- **数据**（3 项）：两州县数、FIPS 唯一、无缺失；CSV 与工作簿一致；能源三项在州内是常数。
- **效用函数**（7 项）：越低越好和越高越好的分段计算、图片里的碳强度例子（63.6）、ln 变换、指数形状、缺失值和下限、非法锚点报错。
- **配置**（3 项）：随仓库提供的配置合法、维度内权重之和为 1、指标不能放在错误的维度。
- **县级打分**（8 项）：
  - 292 个县都有 8 个维度分，且都在 0–1 之间；
  - Loudoun 的气候、水、土地、交通维度与手算一致，精确到 1e-9；
  - 能源维度在州内是常数；
  - 提示指标都已计算，且没有被计分；
  - 输出的记录可以直接作为 matrix 的输入。

全部测试共 92 项，全部通过。

---

## 2026-10-04 第 3d 步：A 相关矩阵 + 合成交互矩阵 I；第一次端到端排名

### 文件

- `src/dc_locator/interactions/interaction.py`：`spearman_matrix()`、`build_interactions()`。
- `src/dc_locator/interactions/__init__.py`：`interaction_matrix()`，把 DEMATEL、相关矩阵和团队标注合成 I。
- `configs/interactions.json` 新增 `interaction_model`：κ、β，以及 7 对交互的类型和理由。
- `src/dc_locator/pipeline.py`：端到端流程（数据 → 维度分 → 权重 → 交互 → Choquet 排名），带命令行；结果写入 `outputs/<run_id>/`，包括 `ranking.csv`、`decision_output.json`、`weights.json`、`interactions.json`。
- 测试：`tests/interactions/test_interaction_matrix.py`（8 项）、`tests/pipeline/test_pipeline.py`（6 项）。

### A 相关矩阵（Spearman，按州计算真实维度分）

两组值得注意的相关性：

- **VA**：气候–制冷 −0.71，制冷–水 0.55，土地–交通 −0.47，交通–劳动力 0.35，光纤–劳动力 −0.20。
- **GA**：交通–劳动力 0.49，制冷–劳动力 0.37，水–交通 −0.35，光纤–劳动力 −0.17。

### 合成规则（比"A、B 取平均"更严谨）

| 类型 | 含义 | 强度来源 | 理由 |
|---|---|---|---|
| 互补（I > 0） | 风险叠加，两个维度要同时好 | 只用 DEMATEL | 互补是偏好和因果判断，数据的相关性看不出来 |
| 重复（I < 0） | 两个维度测的是同一件事 | ½ DEMATEL + ½ max(ρ, 0)；**ρ ≤ 0 时取消** | 重复是经验事实，数据必须支持 |

规模：I = κ·λ_max·(正负号 × s)。λ_max 是在客户权重 φ 下满足单调性条件的最大规模，κ = 0.5 为中等强度。权重为 0 的维度（州内的能源）不设交互。

### 结果

| 交互 | 类型 | VA 的 I | GA 的 I |
|---|---|---|---|
| 气候–水 | 互补 | +0.078 | +0.048 |
| 制冷–水 | 互补 | +0.064 | +0.040 |
| 交通–劳动力 | 重复 | −0.054 | −0.037 |
| 光纤–劳动力 | 重复 | **取消**（ρ = −0.20） | **取消**（ρ = −0.17） |
| 光纤–交通 | 重复 | 取消（ρ = −0.11） | −0.017（ρ = 0.05） |

**数据推翻了一个预设**：我们原以为光纤和劳动力都反映城市化、属于重复，但两州的商业光纤覆盖率和劳动力规模都是负相关，所以这一对没有设为重复。这是"团队判断提出假设、数据可以否决"的一个实例，可以放进报告。

### 第一次真实排名（默认客户，κ = 0.5）

- **VA 前 5**：Loudoun 82.38、Washington 80.32、Louisa 77.01、Bristol city 75.65、Smyth 75.46。Loudoun 排第一，与现实中全球最大的数据中心集群一致。
- **GA 前 5**：Dade 76.57、Candler 75.27、Fayette 74.48、Sumter 74.33、Upson 73.96。
- **Choquet 与加权求和对比**：两州的第一名都相同，前 10 名重合 9 个，排名相关系数 0.995（VA）和 0.992（GA）。交互项让每个县的分数变动约 ±2 分，是在细调，不会推翻结论。

### 测试（14 项）

- **交互矩阵**（8 项）：互补只用 DEMATEL；重复混合 DEMATEL 和 ρ⁺；ρ ≤ 0 的重复被取消；权重为 0 的维度不设交互；κ = 1 时恰好达到单调性上界；κ 线性缩放且不改变相对比例；非法输入报错；常数维度的相关系数处理。
- **端到端**（6 项）：133 个县全部排名且分数在 0–100 之间；使用的是 Choquet 模型；与加权求和的前 10 名至少重合 8 个；改变客户输入会同时改变权重和排名；κ = 0 时恰好等于加权求和；州内不使用能源维度。

全部测试共 106 项，全部通过。

---

## 2026-10-04 第 3b 步：交叉检验与稳健性（SMAA-2）

### 文件

- `src/dc_locator/validation/`：
  - `methods.py`：5 种对照权重方法；
  - `smaa.py`：SMAA-2；
  - `__init__.py`：编排 5 项检验并写出结果；
  - `__main__.py`：命令行；
  - `README.md`。
- 输出：`outputs/validation_<州>/`，共 8 个文件（CSV 和 JSON）。
- 测试：`tests/validation/test_validation.py`，共 11 项。

### 方法

1. **权重方法对比**：AHP（主方法）、等权、ROC（按 AHP 的排序，Barron & Barrett 1996）、CRITIC（Diakoulaki 等 1995）、熵权、DEMATEL 衍生权重 √((r+c)² + (r−c)²)。CRITIC 和熵权衡量的是区分度，不是重要性，所以只作对照。
2. **SMAA-2**（Lahdelma & Salminen 2001）：
   - 权重按 Dirichlet(20·φ) 抽样，均值等于客户权重；
   - κ 按 U(0, 1) 抽样，每个样本按该样本的权重重新计算 λ_max；
   - 共 10,000 次，向量化计算，每个州约 2 秒；
   - 输出排名接受度、排第一的概率、进入前 10 的概率、排名分位数、90 分位后悔值，以及中心权重（某县获胜的那些样本的平均权重）。
3. **有效权重**：φ_k·Cov(D_k, S) / Var(S)，交互项单列一行。
4. **客户输入响应**：每次只改一个选项，比较前 10 名重合数、排名相关系数和新的第一名。
5. **效用函数形状**：指数形状（ρ = ±2）与线性对比。

### 结果

**VA（稳健）**

| 检验 | 结果 |
|---|---|
| SMAA 排第一的概率 | Loudoun 57%、Washington 36% |
| SMAA 进入前 10 的概率 | Louisa 99.7%、Washington 99.6%、Loudoun 98.7% |
| 90 分位后悔值最低 | Loudoun（7.0 分） |
| 其他权重方法 | AHP 和 ROC 选 Loudoun；等权、CRITIC、熵权、DEMATEL 选 Washington County |
| 有效权重 | 水 0.49、光纤 0.33（名义值 0.31、0.17）；气候 −0.06 |

结论：Loudoun 和 Washington County 是两个稳健的领先者，谁排第一取决于权重。

**GA（对权重敏感）**

| 检验 | 结果 |
|---|---|
| SMAA 排第一的概率 | Dade 38%、Candler 20% |
| SMAA 进入前 10 的概率 | Dade 79%、Candler 77%、Sumter 76% |
| 其他权重方法 | 分歧很大，与最终排名的相关系数只有 0.19–0.94 |
| 有效权重 | **水解释了 66% 的分数差异** |

结论：GA 应该给出一组候选县（Dade、Candler、Sumter），并明确说明排名主要由水资源驱动。

### 测试中发现的两处测试数据错误（代码正确）

1. CRITIC 测试里，"flat" 列和 "spread" 列变化模式完全相同（r = 1），CRITIC 正确地给了 spread 0 权重。已改为不相关的 flat 列，并新增 "copy" 列验证完全重复的两列权重相同。
2. 所有维度完全相关时，CRITIC 的信息量全为 0，归一化会报错。这是 CRITIC 没有定义的边界情况，已改为测试"会报错"。

全部测试共 117 项，全部通过。

---

## 下一步（待讨论）

1. **团队打分**：AHP 两两比较、DEMATEL 影响分、7 对交互的类型、锚点和维度内权重（swing），把单人初稿换成团队结果，然后全部重跑。命令都已准备好。
2. **报告和 PPT 用图**：雷达图、贡献堆叠柱、DEMATEL 因果图、相关性热力图、SMAA 排名接受度图、地图。
3. **Gate 模块衔接**：组员上传的 `gates/virginia` 和 `gates/georgia` 如何接入流程。
4. **最终 README 整理**。
