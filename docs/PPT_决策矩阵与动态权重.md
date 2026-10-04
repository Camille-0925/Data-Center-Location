# PPT 素材：决策矩阵与客户需求驱动的动态权重

> 用途：给负责做 PPT 的组员。每一节对应一页幻灯片，包括 **建议标题（英文，直接放到幻灯片上）**、**页面要点**、**公式**、**建议配图** 和 **讲稿要点（中文）**。
> 文中所有数字都来自 repo 的实际运行结果（默认客户、单人初稿判断）。团队打分后需要重跑并更新数字，见最后一节。
> 代码位置：`src/dc_locator/decision/`、`dimension_weights/`、`interactions/`、`validation/`。

---

## 符号表（放在附录页或第一次出现公式时）

| 符号 | 含义 | 取值 |
|---|---|---|
| i | 县（county） | VA 133 个，GA 159 个 |
| k, l | 维度 | 8 个 |
| D_ik | 县 i 在维度 k 上的分数 | 0–1，越高越好 |
| w0_k | 团队判断的基准权重（AHP） | Σ = 1 |
| M_k | 客户需求作用在维度 k 上的乘数 | > 0，默认为 1 |
| φ_k | 最终维度权重，也就是 Choquet 中的重要性 | Σ = 1 |
| I_kl | 维度 k 与 l 的交互指数 | [−1, 1]；> 0 互补，< 0 重复 |
| κ | 交互强度 | 0–1，默认 0.5 |

8 个维度：Climate risk、Water、Land & ecology、Fiber、Workforce & community、Cooling climate、Transportation、Energy & carbon。

---

## 第 1 页：整体框架

**建议标题**：*From customer needs to a county ranking*

**页面要点（流程图）**：

```
Customer needs (4 questions) ──► dynamic weights φ (8)
Team judgment (DEMATEL) ─┐
County data (correlation) ┴──► interaction matrix I (8 × 8)
County data (18 indicators) ──► dimension scores D (n × 8)
                                         │
                       Choquet decision matrix: D, φ, I ──► score, rank, robustness
```

**讲稿要点**：
- 三类输入各管一件事：客户需求决定"什么重要"（φ）；团队判断加上数据决定"维度之间怎么互相影响"（I）；县的数据决定"每个县各维度表现如何"（D）。
- 三者在决策矩阵里汇合，得到每个县的分数。

**建议配图**：上面这张流程图，三种输入用三种颜色区分。

---

## 第 2 页：决策矩阵

**建议标题**：*The decision matrix: n counties × 8 dimensions*

**页面要点**：
- 输入：一张 n × 8 的维度分表，加上 8 个权重和一个 8 × 8 交互矩阵。
- 输出：每个县的分数（0–100）、排名、Pareto 状态，以及和第一名在各维度上的差距。

**公式（大字号放在页面中央）**：

$$
\text{Score}_i = 100 \times \Big[\underbrace{\sum_{k} \varphi_k D_{ik}}_{\text{each dimension on its own}} \;-\; \underbrace{\tfrac{1}{2}\sum_{k<l} I_{kl}\,\lvert D_{ik}-D_{il}\rvert}_{\text{interactions between dimensions}}\Big]
$$

**讲稿要点**：
- 这是 **2-additive Choquet 积分**（Grabisch 1997），多准则决策领域处理"准则之间不独立"的标准方法。
- 第一项就是常见的加权求和；第二项是我们加入的交互修正。
- 所有 I = 0 时，公式**退化为加权求和**。所以加权求和是我们模型的一个特例，传统方法完全被包含在内。

**建议配图**：一张 n × 8 的热力图表格（行为县，列为维度，颜色表示 D），旁边放一行 8 个权重，箭头指向"Score"。

---

## 第 3 页：创新点 ①：不假设维度相互独立

**建议标题**：*Dimensions interact: synergy and overlap*

**页面要点**：

| 交互类型 | 含义 | 例子 | 对分数的影响 |
|---|---|---|---|
| **互补**（I > 0） | 两个维度要同时好才有价值 | 炎热气候会抬高冷却用水，恰好在水资源紧张的地方 | 两个维度失衡时扣分 |
| **重复**（I < 0） | 两个维度部分测的是同一件事 | 交通便利和劳动力充足都反映"靠近城市" | 两个维度同时高时，不重复加分 |

**数字例子（建议做成两个县的对比柱状图）**：两个维度权重各 0.5，I = +0.4（互补）

| 县 | 水 | 制冷 | 加权求和 | Choquet |
|---|---|---|---|---|
| 均衡县 | 0.5 | 0.5 | 50 | **50** |
| 失衡县 | 0.9 | 0.1 | 50 | **34** |

**讲稿要点**：
- 加权求和认为这两个县一样好。但对数据中心来说，"水很充足却极度炎热"的地方，冷却需求会集中压在水资源上，风险是叠加的。Choquet 能体现这一点。
- 同一个例子如果设 I = −0.4（重复），失衡县反而得 66 分：两个维度测的是同一件事时，一项强就足够了，不应重复奖励。

---

## 第 4 页：完备性 ①：数学保证

**建议标题**：*Guaranteed properties*

**页面要点（打勾清单）**：

| 性质 | 含义 | 怎么保证 |
|---|---|---|
| ✅ 单调性 | 任何一个维度变好，总分都不会下降 | 充要条件 **φ_k ≥ ½ Σ_l \|I_kl\|**，不满足时系统拒绝运行 |
| ✅ 有界 | 全部维度为 0 时得 0 分，全部为 1 时得 100 分 | Σφ = 1，再加上单调性 |
| ✅ 等值不变 | 所有维度分都是 c 时，总分为 100c | 交互项只作用于维度之间的差距 |
| ✅ 精确分解 | 总分 = 8 个维度贡献 + 各交互贡献，逐项相加正好等于总分 | 输出中逐项列出 |
| ✅ 包含加权求和 | I = 0 时与传统方法完全一致 | 有测试验证 |
| ✅ 实现正确 | 与 Grabisch 的另一种等价公式（min/max 形式）独立实现，结果一致 | 20 个随机县，8 维 |

**单调性条件的推导**（放附录页）：Möbius 表示下 m_k = φ_k − ½ Σ_l I_kl，m_kl = I_kl。单调的充要条件是：对任意 k 和任意不含 k 的集合 S，m_k + Σ_{l∈S} m_kl ≥ 0。最坏情况取 S = {l : I_kl < 0}，代入化简后正好得到 φ_k − ½ Σ_l |I_kl| ≥ 0。

**讲稿要点**：引入交互项最大的风险是出现"某个维度变好、总分反而下降"的反常结果。我们推导出了这个风险的充要条件并在代码中强制检查，另外用 200 次随机测试验证了单调性。

---

## 第 5 页：基准权重：团队判断（AHP）

**建议标题**：*Base weights from team judgment (AHP)*

**页面要点**：
- 团队对 8 个维度做 28 次两两比较（Saaty 1–9 标度）。
- 权重取比较矩阵的最大特征向量；用行几何平均法交叉核对。
- 一致性检验：CR = CI/RI，必须 < 0.10。
- 多人打分时，逐格取几何平均后再计算（Forman & Peniwati 1998）。

**公式**：

$$
A\,w^{0} = \lambda_{\max}\, w^{0}, \qquad CI = \frac{\lambda_{\max}-n}{n-1}, \qquad CR = \frac{CI}{RI(8)=1.41} < 0.10
$$

**当前结果（单人初稿）**：λ_max = 8.080，**CR = 0.008**，两种方法最大差距 0.0009。

| 维度 | 基准权重 w0 |
|---|---|
| Energy & carbon | 0.245 |
| Water | 0.237 |
| Climate risk | 0.137 |
| Fiber | 0.130 |
| Land & ecology | 0.080 |
| Cooling climate | 0.070 |
| Workforce & community | 0.060 |
| Transportation | 0.041 |

**讲稿要点**："碳和水哪个更重要"是价值判断，数据回答不了，所以由团队判断，并用一致性检验确保判断前后自洽。

**建议配图**：8 个维度的横向条形图。

---

## 第 6 页：客户需求 → 动态权重（核心页）

**建议标题**：*Customer needs reshape the weights*

**页面要点：客户只回答 4 个选择题，全部有默认值**

| 客户问题 | 选项（**粗体**为默认） | 作用 |
|---|---|---|
| 冷却方式 | 蒸发冷却 / 风冷 / 闭式液冷 / **不确定** | 蒸发：水 ×1.5；风冷：水 ×0.6、制冷 ×1.5；液冷：水 ×0.5、制冷 ×0.5 |
| 业务延迟敏感度 | 低 / **一般** / 高 | 光纤 ×0.6 / ×1 / ×1.6 |
| 可靠性要求 | **标准** / 高（Tier IV 或 30 年以上） | 气候风险 ×1.5 |
| 优先目标 | **均衡** / 可持续优先 / 运营优先 | 可持续：水、制冷、土地（州间比较时含能源）×2；运营：光纤、劳动力、交通 ×2 |

**公式（三步）**：

$$
\varphi_k = \frac{w^{0}_k \, M_k}{\sum_l w^{0}_l \, M_l}
\quad\longrightarrow\quad
\text{within a state: } \varphi_{\text{energy}} = 0,\ \text{renormalize}
\quad\longrightarrow\quad
\varphi_k \le 0.40\ \text{(excess shared pro rata)}
$$

其中 M_k 是客户所选选项作用在维度 k 上的乘数之积。

**讲稿要点**：
- **分工清楚**："维度之间谁更重要"由团队判断一次定下来（AHP），"这个项目需要什么"由客户回答。客户的回答只是在团队判断的基础上做调整，不会推翻它。
- **每个乘数都有物理依据**：蒸发冷却直接耗水；风冷依赖外部气温；液冷几乎不耗水；延迟敏感的业务依赖网络；运营期越长，气候风险累积越多。
- **比例尺度不变**：乘法调整等价于把 AHP 的每个比值 w_k/w_l 乘以 M_k/M_l，调整后的结果仍然是有意义的比例尺度权重。例如选"高延迟敏感"后，光纤与水的权重之比恰好变为原来的 1.6 倍。
- **单维度上限 0.40**：防止多个选项叠加后某个维度压倒一切，退化成只看一个指标的排序。
- **州内排名时能源权重为 0**：电价、SAIDI、碳强度都是州级数据，同一州内所有县的值相同，所以能源只用于"选 VA 还是 GA"的比较。

---

## 第 7 页：动态权重示例

**建议标题**：*Same counties, different customer, different weights*

**页面要点（建议做成分组条形图：默认客户 vs 蒸发冷却加可持续优先）**：

| 维度 | 默认客户（州内） | 蒸发冷却 + 可持续优先 |
|---|---|---|
| Water | 0.313 | **0.400**（上限前为 0.515，被截到 0.40） |
| Climate risk | 0.182 | 0.123 |
| Fiber | 0.172 | 0.117 |
| Land & ecology | 0.106 | 0.144 |
| Cooling climate | 0.093 | 0.126 |
| Workforce & community | 0.079 | 0.054 |
| Transportation | 0.054 | 0.037 |
| Energy & carbon | 0 | 0 |

**排名会怎么变（VA，每次只改一个选项；完整表见 `outputs/validation_VA/customer_input_response.csv`）**：
- 风冷、高延迟敏感、运营优先：第一名从 Loudoun 变为 **Washington County**；
- 闭式液冷：第一名变为 **Louisa County**；
- 每个选项都会让前 10 名换掉 0 到 2 个县。

**讲稿要点**：客户每改一个答案，权重就按公式重新计算，排名随之更新；系统会逐条说明是哪个选项改变了哪个维度的权重。

---

## 第 8 页：交互矩阵 I：团队判断与数据融合（创新点 ②）

**建议标题**：*Interaction matrix: judgment proposes, data can veto*

**页面要点**：

| 来源 | 捕捉什么 | 方法 |
|---|---|---|
| **B：团队判断** | 维度 k 是否驱动维度 l，强度多大，包括间接链条 | **DEMATEL**：T = X(I − X)⁻¹ |
| **A：数据** | 全州各县的维度分是否同起同落 | Spearman 相关矩阵 |

**融合规则（本页重点）**：

| 交互类型 | 强度 s（0–1） | 理由 |
|---|---|---|
| 互补（I > 0） | s = DEMATEL 强度 | 互补是偏好和因果判断，数据的相关性看不出来 |
| 重复（I < 0） | s = ½·DEMATEL + ½·max(ρ, 0)；**ρ ≤ 0 时取消** | 重复是经验事实，必须在数据中表现为正相关 |

**DEMATEL 结果（建议画因果图：横轴为中心度 r + c，纵轴为原因度 r − c）**：
- **原因**：Climate risk（r − c = +1.15）、Cooling climate（+0.60）、Transportation（+0.31）。
- **结果**：Water（−1.32）、Energy & carbon（−0.48）、Fiber（−0.34）。
- 一句话：**气候是根源，水和能源是它的影响落点。**

**"数据否决"的实例（建议单独做一个醒目的框）**：
> 我们原本假设光纤和劳动力都反映城市化、属于重复。但两州数据显示商业光纤覆盖率和劳动力规模**负相关**（VA ρ = −0.20，GA ρ = −0.17），系统自动取消了这一对交互。

**当前交互矩阵（默认客户）**：

| 交互 | 类型 | VA | GA |
|---|---|---|---|
| Climate ↔ Water | 互补 | +0.078 | +0.048 |
| Cooling ↔ Water | 互补 | +0.064 | +0.040 |
| Transport ↔ Workforce | 重复 | −0.054 | −0.037 |
| Fiber ↔ Transport | 重复 | 取消（ρ < 0） | −0.017 |
| Fiber ↔ Workforce | 重复 | 取消 | 取消 |

---

## 第 9 页：交互强度如何随客户权重自适应

**建议标题**：*Interactions scale with the customer's weights*

**公式**：

$$
I_{kl} = \kappa \cdot \lambda_{\max}(\varphi)\cdot \operatorname{sign}_{kl}\, s_{kl},
\qquad
\lambda_{\max}(\varphi) = \min_k \frac{\varphi_k}{\tfrac12 \sum_l s_{kl}}
$$

**页面要点**：
- λ_max 是在**当前客户权重**下仍能保证单调性的最大交互规模。客户权重一变，λ_max 自动重新计算，**不论客户怎么选，模型都保持单调**。
- κ ∈ [0, 1] 是交互强度占允许最大值的比例：默认 0.5，κ = 0 时就是加权求和。稳健性分析中 κ 在 0 到 1 之间随机抽样。
- 只做一次整体缩放，保留 A 和 B 给出的各交互之间的相对大小。

**讲稿要点**：动态的不只是权重，交互项也随客户需求自动调整，而且始终满足数学条件。

---

## 第 10 页：完备性 ②：稳健性检验

**建议标题**：*Is the answer robust?*

**页面要点**：

| 检验 | VA | GA |
|---|---|---|
| Choquet 与加权求和对比 | 第一名相同，前 10 名重合 9 个，ρ = 0.995 | 第一名相同，前 10 名重合 9 个，ρ = 0.992 |
| SMAA-2（10,000 组权重，κ 随机） | Loudoun 排第一的概率 57%，Washington 36%；两者进入前 10 的概率 > 98% | Dade 38%、Candler 20%；进入前 10 的概率在 75%–79% 之间 |
| 6 种权重方法对比 | AHP 和 ROC 选 Loudoun；等权、CRITIC、熵权、DEMATEL 选 Washington | 方法之间分歧很大（ρ 0.19–0.94） |
| 有效权重（对分数差异的实际贡献） | 水 0.49、光纤 0.33 | **水 0.66** |
| 效用函数形状（指数形状 ρ = ±2） | 前 10 名重合 8–9 个，第一名不变 | 前 10 名重合 8 个 |

**讲稿要点**：
- **VA 是稳健的**：Loudoun 和 Washington County 是两个稳健的领先者，客户输入可以说明在什么条件下 Washington 会反超。
- **GA 对权重敏感**：分数差异主要由水资源驱动，所以给出候选名单（Dade、Candler、Sumter），而不是唯一的第一名。我们不隐藏这种不确定性。
- 方法依据：SMAA-2（Lahdelma & Salminen 2001）；CRITIC（Diakoulaki 等 1995）；ROC（Barron & Barrett 1996）。

**建议配图**：SMAA 排名接受度堆叠条形图（每个县排第 1、2、3… 的概率），数据见 `outputs/validation_<州>/smaa_rank_acceptability.csv`。

---

## 第 11 页：创新点总结

**建议标题**：*What is new*

1. **客户需求驱动的动态权重**：4 个选择题 → 有物理依据的乘数 → 权重，保持比例尺度；团队判断和客户需求分工明确。
2. **不假设维度独立**：用 Choquet 积分建模互补与重复，传统加权求和只是其中一个特例。
3. **团队判断与数据融合，数据可以否决**：DEMATEL 捕捉因果关系，相关矩阵检验重复；数据不支持的假设会被自动取消。
4. **有数学保证的可解释性**：单调性有充要条件并强制检查；每个分数都能精确分解到维度和交互。
5. **透明说明不确定性**：用概率（SMAA）而不是单一排名表达结论，并说明结论在什么条件下成立、在什么条件下会变。

---

## 第 12 页：局限（可放附录）

- AHP、DEMATEL 和交互类型目前是**单人初稿**，团队打分后需要重跑。
- 能源和碳数据是州级的，无法区分同一州内的县；需要 utility 级数据。
- 2-additive 模型只捕捉两两之间的交互，不包括三个维度之间的交互。这是表达能力和参数可解释性之间的标准权衡：8 个维度共 28 对。
- 本模型是区域初筛，不代表具体地块可以建设；Gate 模块负责电力、供电时间和许可等风险检查。

---

## 附：数字的来源（团队打分后重跑）

```bash
cd final
PYTHONPATH=src python3 -m dc_locator.dimension_weights                     # 第 5–7 页的权重
PYTHONPATH=src python3 -m dc_locator.dimension_weights --cooling_type evaporative --priority sustainability
PYTHONPATH=src python3 -m dc_locator.interactions dematel                  # 第 8 页的 DEMATEL
PYTHONPATH=src python3 -m dc_locator.pipeline --state VA                   # 第 8–9 页的交互矩阵和排名
PYTHONPATH=src python3 -m dc_locator.validation --state VA                 # 第 7、10 页（GA 同理）
```

文献（凭记忆整理，放进 PPT 前请核对）：Grabisch (1997) *Fuzzy Sets and Systems* 92(2)；Marichal (2000) *IEEE Trans. Fuzzy Systems* 8(6)；Saaty (1980) *The Analytic Hierarchy Process*；Forman & Peniwati (1998) *EJOR* 108(1)；Gabus & Fontela (1972) Battelle Geneva；Lahdelma & Salminen (2001) *Operations Research* 49(3)；Diakoulaki et al. (1995) *Computers & OR* 22(7)；Barron & Barrett (1996) *Management Science* 42(11)。
