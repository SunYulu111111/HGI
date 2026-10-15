# 恐龙世界数值逻辑

## 盘面与图标

盘面为 6 列，每列物理高度 2～6 格。普通图标和 Wild 高度为 1～4 格，Scatter 为 1～2 格。高图标按一个逻辑图标参与判奖，Ways 数量为各列逻辑图标数的乘积，最高 46,656。

Scatter ID 为 0，Wild ID 为 1，普通图标 ID 为 2～12。Wild 仅出现在第 2～5 列，可替代普通图标，无独立赔付；Scatter 不参与普通赔付。

初始盘面和补牌均按列抽取布局，随机打乱图标高度顺序。每个获准生成的物理 Scatter 计数一次，留在盘面并继续掉落的 Scatter 不重复计数。

第 2～5 列新生成的普通图标，自身高度为 2、3、4 格时独立抽取银框。已有图标不重抽，Wild 和 Scatter 不附框。银框中奖后，在原位置生成随机普通图标并变为金框；金框再次中奖后变为 Wild。转换保留高度，框随图标掉落，每手结束清除。`FrameStage` 的 0／1／2 分别表示无框／银框／金框。

金色底板用于银框转金框的表现，尺寸为 2／3／4 行，无图标 ID，不参与判奖或计数。

## Scatter 生成控制

每轮初始奖励与追加免费次数合计最多 50。生成阶段按剩余次数额度控制新 Scatter；Scatter 触发的次数足额发放，所有已发放次数正常玩完。

- 主游戏单手可生成的 Scatter 总数上限为 `FreeTriggerScatterCount + floor((FreeMaxTimes − BaseFreeSpins) / MainExtraFreeSpinsPerScatter)`，当前为 25。该额度由六列初始盘面和本手全部补牌共享。
- 免费本手可生成的新 Scatter 数为 `FreeMaxTimes − FreeSpinNumber − FreeSpinsRemaining`。每个新 Scatter 固定追加 1 次。`FreeSpinNumber` 包含本手，`FreeSpinsRemaining` 为扣除本手后的已发放待玩次数；额度由本手六列初始盘面及全部补牌共享。

`floor` 表示向下取整。六列按列号顺序生成；每列原布局中的全部候选先使用额度，拆分后的额外位置随后使用余额。生成顺序如下：

1. 图标与高度配对后，先判断 Scatter 候选是否还有生成额度；获准时消耗一个额度。
2. 获准的 3／4 格 Scatter 保留为 2 格，剩余 1／2 格在其上方按本列、本模式的补牌权重生成新图标。额外位置也属于新生成，若再抽到 Scatter，同样使用共享额度。
3. 超额度 Scatter 候选从本次实际来源轴带的同列普通图标池中重新抽取。池中保留重复图标，按出现频次抽取，不含 Wild／Scatter。普通盘使用普通轴，特殊盘使用特殊轴，固定盘和零奖盘使用其普通补牌轴。
4. 替换后的普通图标保留原高度，按普通图标规则抽银框；原高度为 3／4 格时直接保留。该替换不额外推进 `top index`，不改变其他已配对图标或整列物理高度。

| 情况 | 处理 |
|---|---|
| 已有 Scatter 留在盘面或掉落 | 正常保留，不重新计数或消耗额度 |
| 新 Scatter 生成额度为 0 | 新 Scatter 候选生成普通图标，已发放免费次数仍正常玩完 |
| `BaseFreeSpins > FreeMaxTimes` | 配置错误 |
| 需要替换时，实际来源轴带同列没有普通图标候选 | 配置错误 |

## 判奖与赔付

普通图标从最左列起连续命中至少 3 列时中奖。每条路径只结算最高奖项；共享 Wild 前缀不重复派奖。同一图标每轮只处理一次消除或转换。

以下为单条路径相对本手总投注的赔付倍数。

| ID | 图标 | 3 连 | 4 连 | 5 连 | 6 连 |
|---:|---|---:|---:|---:|---:|
| 2 | H1 霸王龙 | 3 | 4 | 6 | 15 |
| 3 | H2 三角龙 | 2 | 2.5 | 5 | 8 |
| 4 | H3 甲龙 | 1 | 2.5 | 4 | 6 |
| 5 | H4 雷龙 | 0.8 | 1.5 | 2 | 3 |
| 6 | H5 克氏龙 | 0.6 | 1 | 1.2 | 1.5 |
| 7 | H6 始祖鸟 | 0.6 | 1 | 1.2 | 1.5 |
| 8 | L1 A | 0.4 | 0.6 | 0.8 | 1 |
| 9 | L2 K | 0.4 | 0.6 | 0.8 | 1 |
| 10 | L3 Q | 0.1 | 0.2 | 0.3 | 0.4 |
| 11 | L4 J | 0.1 | 0.2 | 0.3 | 0.4 |
| 12 | L5 10 | 0.1 | 0.2 | 0.3 | 0.4 |

`ITEM_PRIZES_N` 存储奖值，10000 表示 1 倍。单条路径基础奖励为 `BaseBet × 奖值 ÷ 10000 ÷ PRIZE_RATE`，向下取整；本轮奖励为各有效路径基础奖励之和乘以 `Multiplier`，本手总奖励为各轮奖励之和。`BaseBet` 为本手总投注。

## 主游戏流程

1. 设置本手共享 Scatter 生成额度，生成盘面、抽取新图标银框，统计初始 Scatter。
2. 第一次中奖按 x1 结算。
3. 无框中奖图标消除；银框转换为普通金框图标，金框转换为 Wild。
4. 剩余图标下落，按空缺物理高度补牌，按剩余额度处理新 Scatter，抽取新图标银框并累计新 Scatter。
5. 补牌后继续中奖则重复结算，倍数依次为 x1、x2、x3、x4、x5、x5……；无中奖时结束。
6. 本手 Scatter 累计不少于 4 个时，足额奖励 `8 + 2 ×（ScatterCount − 4）` 次免费 Spin；结束后清理本手框状态和倍数。

## 免费游戏流程

每轮免费游戏最多实际进行 50 次，包含初始奖励和追加次数。新 Scatter 的生成额度保证已玩次数与已发放待玩次数之和不超过 `FreeMaxTimes`。达到总额度后，后续新 Scatter 候选按上述规则生成普通图标。

1. 首手 `FreeStartMultiplier=1`；后续为上一手 `FreeEndMultiplier+1`。`FreeSpinNumber` 记录本轮手数并参与 Scatter 额度计算，不决定起始倍数。
2. 设置本手新 Scatter 共享额度；生成盘面、判奖、框转换、消除和补牌与主游戏相同。本轮倍数为 `FreeStartMultiplier + min(CascadeIndex − 1, 4)`，`CascadeIndex` 从 1 开始。
3. 手内最多增加 4，达到后继续按该倍数正常派奖，直到无中奖。
4. 本手每出现一个新 Scatter，固定追加 1 次免费 Spin，不重新发放基础 8 次。
5. `FreeEndMultiplier` 取本手最后实际派奖的倍数；无中奖时等于本手起始倍数。清理框状态和手内进度，下一手从该倍数加 1 开始。
6. 追加免费次数延续累计倍数，所有已发放次数正常玩完后结束。第 50 手仍完整执行判奖、消除、补牌和奖励结算。新一轮免费游戏重新从 x1 开始；累计倍数不另设独立上限。

示例：本手按 x3、x4、x5、x6、x7、x7……结算，下一手从 x8 开始；若下一手结算至 x12，再下一手从 x13 开始。

## 配置参数

| 字段 | 作用或值 |
|---|---|
| `ReelHeightWeights1`～`ReelHeightWeights6` | 六列物理高度 2～6 格的权重 |
| `base_height_weight_1`～`base_height_weight_6` | 主游戏初始 6 格布局权重 |
| `free_height_weight_1`～`free_height_weight_6` | 免费游戏初始 6 格布局权重 |
| `base_elim_height_weight_{Col}_{Height}` | 主游戏补牌布局权重 |
| `free_elim_height_weight_{Col}_{Height}` | 免费游戏补牌布局权重 |
| `SilverFrameChance` | 银框概率，当前为 1200／10000 |
| `SilverUpgradeSymbolWeights` | 银框转换图标权重，依次对应 H1～H6、L1～L5 |
| `MainMultiplierCap` | 5 |
| `FreeSpinMultiplierIncrementCap` | 4 |
| `Free_Max_Times` | 50；内部属性为 `FreeMaxTimes`，用于计算新 Scatter 生成额度 |
| `FreeTriggerScatterCount`／`BaseFreeSpins` | 4／8 |
| `MainExtraFreeSpinsPerScatter` | 2；必须为正数 |
| `FreeExtraSpinsPerScatter` | 固定为 1，其他值报配置错误 |
| `BaseMaxEliTimes`／`Free_Max_EliTimes` | 各 100；超过连续消除保护次数时返回异常 |

`Col` 为列号 1～6，`Height` 为补牌高度 2～6；1 格固定补一个图标。初始列高不足 6 格时，使用对应高度的补牌布局权重。轴带、布局权重和银框概率为流程验证参数。

押注共 9 档：100,000、200,000、500,000、1,000,000、2,000,000、5,000,000、10,000,000、20,000,000、25,000,000。大奖展示使用 `BigWinGrade`／`NewBigWinGrade` 分档；大奖条件仅作为数值目标，不触发额外奖励或结果替换。
