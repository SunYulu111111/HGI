# 《Si Botak Desa》玩法与数值逻辑

本文分为玩家可感知的玩法介绍和服务器实现所需的定制数值逻辑。普通停轴、Cluster 查找、基础赔付及常规消除掉落沿用平台通用能力。

## 第一部分：玩法介绍

### 基础游戏

游戏使用 6 列 × 5 行盘面。相同图标在横向或纵向相邻时组成 Cluster，至少 5 个图标即可中奖；Cluster 越大，奖励越高。Wild 可以加入其他普通图标的 Cluster，但不能单独组成中奖。

中奖图标消除时，盘面上其他同 ID 的普通图标也一并消除；未参与中奖的 Wild 不扩展消除。保留图标维持相对顺序，再补充新图标。新盘面继续判断 Cluster，直到不再中奖。额外消除的位置不增加赔付，也不生成金色区域。

普通轴带不直接包含 Scatter 和 Bonus；盘面形成后，特殊图标替换不参与中奖或扩展消除的普通图标，因此不会破坏已有 Cluster。Scatter 可能转化为 Super Scatter。Base 有消除和无消除时都可能出现 Bonus；只有本次 Base 已产生金色区域且终盘仍有 Bonus，才触发金色玩法。没有消除时，Bonus 仅展示，不产生 Bonus 奖励。

Base 初始放入的 Scatter 数量不超过 2 个且仍有可替换位置时，才判断是否放置 Bonus。每轮消除掉落最多生成 1 个特殊图标；盘面已有 Bonus 或已有 3 个 Scatter 类图标时，不再生成掉落特殊图标。

### 免费游戏

- 最终盘面累计至少 3 个 Scatter 类图标且没有 Super Scatter时，进入普通免费游戏，获得 10 次 Free Spin。
- 最终盘面累计至少 3 个 Scatter 类图标且包含 Super Scatter 时，进入超级免费游戏，获得 10 次 Free Spin。
- Free Spin 中出现 2 个 Scatter 类图标追加 2 次；出现 3 个及以上追加 4 次。Super Scatter 计入 Scatter 类图标总数。
- 一轮完整 Free 至少尝试生成一次 Bonus；如果此前一直没有出现，则在最后一次 Free Spin 的全部消除结束后执行保底，初始盘面仍按正常概率生成。
- Free 的每轮消除掉落同样最多生成 1 个特殊图标；盘面已有 Bonus 或 Scatter 类图标达到 3 个时，本轮不再生成。

普通免费游戏中的金色区域会持续保留，触发金色玩法后清空。超级免费游戏中的金色区域在金色玩法触发后仍然保留，直到本轮超级免费结束。

### 金色玩法

普通图标实际参与中奖的消除位置会变为金色区域，扩展消除位置不生成金色区域。全部消除结束后，如果最终盘面仍有 Bonus，则触发金色玩法。

每个金色位置会生成以下一种结果：

- 金币：提供固定倍数奖励。
- 四叶草：放大以自身为中心九宫格内的金币和聚宝盆，不影响 JP。
- 聚宝盆：收集当前金币及已经结算的聚宝盆，不收集 JP，并触发其他位置重翻。
- JP：直接获得 MINI、MINOR、MAJOR 或 GRAND 奖励。

同一轮先结算全部四叶草，再按列从左到右、每列行下标从 4 到 0 的顺序结算聚宝盆。所有已结算聚宝盆都会保留，其余位置重新生成结果；如果再次出现聚宝盆，则继续重翻，直到没有新聚宝盆。

一整轮金色玩法累计最多出现 5 个聚宝盆、3 个四叶草；达到对应上限后不再生成该类型。首次翻牌及每次重翻的新图标至少有 1 个 coin，保留聚宝盆不计入。

金色玩法最终奖励为当前金币与聚宝盆金额之和，加上过程中获得的全部 JP 奖励。

## 第二部分：数值逻辑

TYPE 0 Base 自身 Hit 目标为 30%，全部连消 RTP 目标为 40%；Base Bonus 以付费 Base 局数为分母，目标触发率约为 1.25%。初始有奖盘读取 `BaseWinBonusCountProbability` 决定是否放置 Bonus；初始无奖盘读取 `BaseNoWinBonusCountProbability`，可展示 Bonus，但本次 Base 没有实际消除时不触发金色玩法。

TYPE 0 的 Base Bonus RTP 目标为付费 Base 累计下注的 20%。金币中档奖励承担更大的常见概率，四叶草和聚宝盆的类型比例降低；500x 金币、20 倍四叶草及 GRAND 5000x 仍有正概率。波动同时按整轮 Bonus 奖励的绝对标准差与变异系数（标准差 / 均值）核对，不能只用均值增长说明波动降低。当前奖励权重由 Base、普通 Free、Super Free 共用，因此免费 Bonus 和总 RTP 也随之变化；当前实测见 `bonus_type_calibration.json`，不沿用历史免费分项及总 95% 结论。

金色玩法限制由所有 TYPE 共用：一整轮累计最多 5 个聚宝盆、3 个四叶草；首次翻牌及每次重翻的新图标至少有 1 枚普通金币。保留聚宝盆不计入金币保底。普通和超级免费初始次数均为 10 次。Python 仿真不启用服务器 GROUP 选择和砍分。

2026-10-22 的 TYPE 0 历史目标总 RTP 为 95%：Base Cluster / Bonus 为 45% / 20%；普通 Free Cluster / Bonus 约 7.3% / 18%；Super Free Cluster / Bonus 约 0.7% / 4%。Base Bonus、普通 Free、Super Free 的历史目标触发率分别为 1.25%、0.5%、0.05%。六项 RTP 均以付费 Base 累计下注为分母。`rtp_calibration.json`、`rtp_calibration_runs.json` 和 10 月 22 日性能数据均对应 2026-10-23 共享翻牌限制实施前的版本，不能作为当前规则已达到上述目标或性能水平的依据。实参以当前配置为准。

### 基础数值

- 押注档位为 100,000 / 200,000 / 500,000 / 1,000,000 / 2,000,000 / 5,000,000 / 10,000,000 / 20,000,000。
- 原始图标 ID 为 0–12：Scatter 使用 0，Wild 使用 1，主盘 Bonus 使用 2，普通赔付图标使用 3–12。
- Super Scatter 由普通 Scatter 转化，仍使用 ID 0，通过 Super Scatter 位置状态区分。
- `ITEM_PRIZES_3` 至 `ITEM_PRIZES_12` 的数组下标为 Cluster 数量减 1，奖值以万分之一下注为单位。

普通图标赔付倍数：

- H1（ID 3）：5 个 1x；6–7 个 2.5x；8–11 个 5x；12 个及以上 25x。
- H2（ID 4）：5 个 1x；6–7 个 2.5x；8–11 个 5x；12 个及以上 10x。
- H3（ID 5）：5 个 0.5x；6–7 个 1x；8–11 个 3x；12 个及以上 5x。
- M1/M2（ID 6/7）：5 个 0.3x；6–7 个 0.5x；8–11 个 1x；12 个及以上 3x。
- L1/L2（ID 8/9）：5 个 0.1x；6–7 个 0.2x；8–11 个 0.5x；12 个及以上 1x。
- L3/L4（ID 10/11）：5 个 0.1x；6–7 个 0.2x；8–11 个 0.3x；12 个及以上 0.6x。
- L5（ID 12）：5 个 0.1x；6–7 个 0.2x；8–11 个 0.3x；12 个及以上 0.5x。

### Cluster 消除与补牌

每轮先按实际中奖 Cluster 计算赔付并记录中奖位置，再将全盘与中奖普通图标同 ID 的其他普通图标加入扩展消除。Wild 只有实际参与中奖时才消除；扩展位置只参与消除补牌，不增加赔付和金色区域。

补牌沿同一轴当前窗口后方的正方向继续取数。对 `board[Col][Row]` 的每一列，先将幸存图标按原相对顺序放到数组低下标，再将新图标放到高下标，即 `NewColumn = Survivors + NewItems`。Scatter 和 Super Scatter 状态随幸存图标一起移动。

`NextReelIndexes` 保存各列下一次补牌的正向轴游标；正常盘和特殊轴盘的初始游标为初始窗口起点加 5 后对轴长取模。每次取 `Count` 个图标后，游标正向推进 `Count`；FIX、ZERO 使用正常轴的随机入口。显式注入初始盘只替换盘面，补牌仍延续原停轴状态的轴与游标。原有 `top_indexes` 保留初始停轴及旧接口语义，不再承担反向补牌游标。

### 初始特殊图标生成

正常轴带不包含 Scatter 和 Bonus。完成初始盘面判奖后，先记录中奖位置及同 ID 扩展消除位置；候选只允许 ID 3–12 的普通图标，且必须排除这两类位置。Wild、Scatter、Bonus 均不作为候选。

特殊图标生成及 Super Scatter 转化参数按 TYPE 读取：TYPE 0 使用 `special/yngg_game_server.conf` 的 `[Game Info]`，不读取该文件的 `[0]`；TYPE 4、8、12、17 使用各自数字节。TYPE 0 的 Bonus 四组权重由命名节 `[Type0]` 覆盖；其他 TYPE 保留 `[GENERAL]` 原权重。

TYPE 0 Base 使用 `BASE_RATE=8580,1420,0,0`，按 85.8% / 14.2% 选择 `NORMAL_ROLL` / `SP_ROLL`，选定的轴贯穿本次全部消除补牌。FIX、ZERO 的抽取权重均为 0，预设内容保留。Base Bonus 入口由初始特殊图标权重控制：有奖盘通过 `BaseWinBonusCountProbability` 校准实际触发率；无奖盘通过 `BaseNoWinBonusCountProbability` 展示 Bonus。

正常轴 / 特殊轴初始特殊图标按以下顺序处理：

1. 读取当前 TYPE 的 `ScatterCountProbability`，数组下标 0–3 对应生成 0–3 个 Scatter；实际权重读取当前 TYPE 的配置。
2. 将抽取数量限制为候选位置数量，再依次从候选位置中随机放置 Scatter。
3. 只有实际放入的 Scatter 数量为 0–2 且仍有候选位置时，才继续抽取 Bonus；实际放入 3 个 Scatter 或候选已用完时不抽取 Bonus：
   - 初始盘面无奖时读取 `BaseNoWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus；TYPE 0 为 `98,2`，即满足此分支条件时有 2% 的 Bonus 展示概率。
   - 初始盘面有奖时读取 `BaseWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus。该条件概率与有奖盘占比、Scatter 互斥及候选数量共同决定实际 Base Bonus 触发率，不能直接填成 1.25%。
4. Bonus 在 Scatter 之后从剩余候选位置中随机放置。

Free 先按 `FreeScatterCountProbability` 抽取 Scatter 数量；数组下标 0–3 对应生成 0–3 个，权重取当前 TYPE 配置。先将数量限制为可用候选数量并完成放置，再检查实际放入数量。只有实际放入不超过 2 个 Scatter 且仍有候选位置时，才判断 Bonus：

- Spin 开始时已有金色区域，读取 `FreeGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，权重取当前 TYPE 配置。
- Spin 开始时没有金色区域，读取 `FreeNoGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，权重取当前 TYPE 配置。

实际放入 3 个 Scatter 或候选已用完时，不读取 Free 初始 Bonus 权重。最后一次 Free Spin 也使用此流程，不在初始盘面强制生成 Bonus。

### 消除掉落中的特殊图标

Base 和 Free 每轮消除补牌后使用相同流程检查最终补牌盘面：

- 盘面已有 Bonus：本轮不生成特殊图标。
- Scatter 与 Super Scatter 总数达到 3 个：本轮不生成特殊图标。
- 其余情况只对本轮新补入且符合替换条件的普通图标，按列、列内下标顺序逐格读取掉落权重，直到首次抽中特殊图标或全部候选检查结束。

Base 读取 `DropSpecialSymbolProbability`，Free 读取 `FreeDropSpecialSymbolProbability`，下标 0 / 1 / 2 依次表示不替换、生成 Scatter、生成 Bonus。TYPE 0 Base 的 Bonus 分量为 0，Free 及其他 TYPE 仍读取各自有效配置；具体权重不在本文硬编码。

替换候选仅限本轮新补入、ID 为 3–12、且不属于新盘面中奖位置或同 ID 扩展消除位置的图标。每个候选只抽一次；抽中特殊图标后立即替换当前扫描格并停止，不再随机选择另一个位置。无候选时不读取权重。每次掉落过程最多出现 1 个特殊图标，替换不会破坏新盘面已经形成的 Cluster，也不会规避扩展消除。

如果掉落生成 Scatter：

- Base 牌面尚无 Super Scatter 时，立即读取 `SuperScatterProbability`；命中后从全盘现存普通 Scatter 中随机选择 1 个转化，可能选中新补入或此前已存在的 Scatter。
- 牌面已经存在 Super Scatter 时，不再执行转化判断，本次图标保持普通 Scatter。
- Free 不执行 Super Scatter 转化。

### Super Scatter 转化

- Base 初始特殊图标放置结束后，若存在普通 Scatter 且尚无 Super Scatter，则读取一次 `SuperScatterProbability`；命中后随机转化 1 个。
- Base 后续掉落 Scatter 按上一节规则即时判断；一旦盘面已有 Super Scatter，后续 Scatter 不再转化。
- Free 不生成或转化 Super Scatter。
- `SuperScatterProbability` 按万分比计算；TYPE 0 调整其实际值以配合约 0.05% 的 Super Free 入口目标，最终值见 `[Game Info]`。

Super Scatter 不使用专门 Symbol ID，盘面仍保留 Scatter ID 0，通过 Super Scatter 位置状态区分并在消除掉落时同步更新坐标。

### 免费游戏触发与状态

完成全部消除、掉落替换和 Super Scatter 转化后，统计最终盘面的 Scatter 与 Super Scatter：

- Scatter 类图标总数达到 3 个及以上且 Super Scatter 数量为 0：使用 `FreeSpinCounts` 第 1 项，当前为 10 次普通免费。
- Scatter 类图标总数达到 3 个及以上且 Super Scatter 数量至少为 1：使用 `FreeSpinCounts` 第 2 项，当前为 10 次超级免费。
- Free 中总数为 2 时，使用 `FreeSpinRetrigger` 下标 2，追加 2 次。
- Free 中总数达到 3 个及以上时，使用 `FreeSpinRetrigger` 最后一档，追加 4 次。

Base 触发免费游戏时不带入任何初始金色区域；Base 消除产生的金色区域也不带入 Free。

每轮 Free 维护“是否已经出现 Bonus”的状态，初始为否，任意 Spin 出现 Bonus 后更新为是，Free 结束时清理。最后一次 Free Spin 的初始盘面不强制放置 Bonus。若此前及本次正常生成流程均未出现 Bonus，则等待全部消除结束，在最终不再中奖的盘面从可替换普通图标中随机放置 1 个 Bonus；如果最终盘面没有候选，则本次不放置。

### 金色玩法触发与状态

每次 Cluster 消除后，只将实际中奖位置加入金色区域，扩展消除位置不加入。全部消除结束后，最终盘面存在 Bonus 且金色区域非空时进入金色玩法。每次 Base 的金色区域从空集合开始，不继承之前的 Base；因此无消除的 Base 即使出现 Bonus，也不触发金色玩法、不产生 Bonus 奖励。

- Base 和普通免费完成金色玩法后清空金色区域。
- 超级免费完成金色玩法后保留金色区域。
- Free 结束时清理本轮保留的金色区域。

### 金色位置结果生成

`special/yngg_bonus.conf` 的 `[GENERAL]` 保留共用奖值档位和默认权重。TYPE 0 按 `[GENERAL]` → `[Type0]` 读取，`[Type0]` 只允许以下四个 PascalCase 权重字段；缺失项继承 `[GENERAL]`：

| TYPE 0 覆盖字段 | 对应 `[GENERAL]` 字段 | 作用 |
| --- | --- | --- |
| `BonusSymbolTypeProbability` | `BONUS_SYMBOL_TYPE_PROBABILITY` | coin / clover / pot / jackpot 类型权重 |
| `BonusCoinMultipleProbability` | `BONUS_COIN_MULTIPLE_PROBABILITY` | 金币档位权重 |
| `BonusCloverMultipleProbability` | `BONUS_CLOVER_MULTIPLE_PROBABILITY` | 四叶草档位权重 |
| `BonusJpTypeProbability` | `BONUS_JP_TYPE_PROBABILITY` | MINI / MINOR / MAJOR / GRAND 权重 |

TYPE 4、8、12、17 继续读取 `[GENERAL]` 原权重，不使用 `[Type0]`；数字节 `[0]` 等旧覆盖不生效。每次切换 TYPE 使用其对应的有效权重，Base、普通 Free、Super Free 和重翻使用同一 TYPE 的权重。奖值数组、图标映射及四叶草/聚宝盆结算顺序保持不变。新翻格先应用共享上限与 coin 保底；非强制 coin 时仍先抽允许的类型，再抽对应档位。

每个新翻位置先应用共享累计上限与 coin 保底；非强制 coin 时，先按当前 TYPE 的有效权重抽取允许类型，再按对应档位权重抽取具体奖励：

- 类型下标固定为 coin、clover、pot、jackpot，不读取 `BONUS_SYMBOL_TYPE`；该字段缺失、注释或更改顺序均不影响类型映射。
- 类型权重：TYPE 0 使用 `[Type0].BonusSymbolTypeProbability`，其他 TYPE 保留 `[GENERAL]` 的 1000/80/6/2。
- coin：`BONUS_COIN_MULTIPLE` 与 `BONUS_COIN_MULTIPLE_PROBABILITY` 按下标对应。
- clover：`BONUS_CLOVER_MULTIPLE` 与 `BONUS_CLOVER_MULTIPLE_PROBABILITY` 按下标对应。
- jackpot：`BONUS_JP_MULTIPLE` 与 `BONUS_JP_TYPE_PROBABILITY` 按 MINI、MINOR、MAJOR、GRAND 顺序对应。
- pot 不再抽取具体档位。

金币倍数保留 0.2/0.5/1/2/3/4/5/10/15/20/25/50/100/250/500。TYPE 0 使用 `[Type0].BonusCoinMultipleProbability`；其他 TYPE 保留 `[GENERAL]` 原权重及金币条件均值。TYPE 0 增加常见中档金币的概率，并减少四叶草和聚宝盆的放大频率；所有高倍档位仍保留正权重。

TYPE 0 的类型权重为 `10081,40,6,5`，顺序为金币、四叶草、聚宝盆、JP。金币低组 0.2/0.5/1 各占金币档位抽样的 16.2%，高组 100/250/500 各占 0.0185%，中间档保留正权重；金币条件均值为 1.99034x。四叶草档位权重仍为 `23,23,23,23,4,4`，JP 档位权重仍为 `80,25,8,1`。具体权重、波动及尾部对照见 `PARAMETERS.md` 与 `bonus_type_calibration.json`。2026-10-22 的旧金币均值、ZERO 大金格及条件奖励不用于当前入口计算。

小于 `coin_multi_1=5` 显示为铜币；大于等于 5 且小于 `coin_multi_2=25` 显示为银币；大于等于 25 显示为金币。四叶草倍数保留 2/3/4/5/10/20，JP 倍数保留 MINI 10x、MINOR 25x、MAJOR 100x、GRAND 5000x。TYPE 0 分别使用 `[Type0].BonusCloverMultipleProbability`、`BonusJpTypeProbability`；其他 TYPE 保留公共权重 40/28/16/10/5/1、80/25/8/1。

### 金色玩法结算顺序

1. 按共享上限与本批 coin 保底规则，逐格生成本批金色位置的结果。
2. 先结算全部四叶草。每个四叶草放大中心九宫格内当前金币和已结算聚宝盆；多个四叶草效果依次累乘，JP 不受影响。
3. 再按 `(Col 升序, Row 降序)` 结算聚宝盆，即先列 0 的 Row 4、3、2、1、0，再列 1 的 Row 4、3、2、1、0，依次到列 5；与服务器 `g_iPotScan` 顺序一致。每个聚宝盆收集当前全部金币及此前已结算聚宝盆；后结算的聚宝盆包含先结算聚宝盆的结果，JP 不参与收集。
4. 所有已结算聚宝盆位置保留，其余位置按上述上限与金币保底规则重新生成；非强制金币时按“类型 → 具体档位”抽取。
5. 重复四叶草、聚宝盆和重翻流程，直到本轮没有新聚宝盆。
6. 每次出现 JP 时立即累计对应 JP 奖励。玩法结束时，再结算当前金币与聚宝盆金额之和。

以上列与行的排序只用于聚宝盆收集结算。翻牌位置、四叶草处理顺序及输出 `cells` 仍按 `(Row, Col)` 升序，类型及档位使用当前 TYPE 的有效配置权重。

所有 TYPE 的 Base、普通 Free、Super Free 均共用 `special/yngg_game_server.conf` 的 `[Game Info]` 限制，不从数字 TYPE 节或 Bonus `[Type0]` 读取：

| 字段 | 当前值 | 作用 |
| --- | ---: | --- |
| `BonusMaxPotCount` | 5 | 整轮金色玩法累计可生成的聚宝盆上限 |
| `BonusMaxCloverCount` | 3 | 整轮金色玩法累计可生成的四叶草上限 |
| `BonusRevealMinCoinCount` | 1 | 每批新翻图标必须包含的最少 coin 数 |

`BonusMaxPotCount` 缺失时，读取旧字段 `bonus_max_round`，两者都缺失时默认 5；新字段存在时优先使用新字段。四叶草与 coin 字段缺失时分别默认 3 和 1。Pot、Clover 计数跨首次翻牌及全部重翻累计，已结算或被后续翻牌覆盖的四叶草仍计入累计数；保留 Pot 不重复计数，也不计入 coin 保底。计数只覆盖单次金色玩法触发及其全部重翻，结束后重置；Super Free 仅保留金格，下次独立 Bonus 重新计数，不跨整轮 Free session 共用上限。

每批新翻格按 `(Row, Col)` 升序逐格生成。每翻出一格便立即更新累计 Pot、Clover 及本批 coin 数；达到任一累计上限后，在后续格抽类型前将对应类型排除，按剩余允许类型的原相对权重抽取。剩余未翻格数（包含当前格）等于仍需补足的 coin 数时，直接生成 coin，仅按金币档位权重抽取具体奖值，跳过类型随机抽取。配置最少 coin 数大于 0、且合法类型的权重已全部归零时，也直接抽取 coin 档位。其他情况仍先抽允许的类型，再抽该类型的档位。

首次翻牌的本批范围为全部金色位置；聚宝盆结算后重翻的本批范围仅为需要重新生成的非 Pot 位置。保留 Pot 即使已有金额，也不能代替本批新 coin。不能先抽出整批再删除超限结果，也不通过整批重抽实现保底。待翻位置少于配置要求的 coin 数时视为无效。外部 `golden_rounds` 同样逐批校验 coin 最少数及整轮 Pot、Clover 上限；允许已有接口支持的部分位置回放，但每个提供的批次必须满足限制。

### 特殊情况处理

- 特殊图标候选位置不足：按抽取顺序使用全部可用位置，超出数量丢弃。
- Base 或 Free 的本轮新补入图标没有可用候选位置：不读取掉落权重，也不放置特殊图标。
- Free Bonus 保底没有候选位置：最终盘面没有可替换普通图标时，本次不放置，不替换中奖位置，也不额外增加 Free Spin。
- Base 或 Free 已有 Bonus，或 Scatter 类图标达到 3 个：本轮掉落不再读取特殊图标权重。
