# 《Si Botak Desa》玩法与数值逻辑

本文分为玩家可感知的玩法介绍和服务器实现所需的定制数值逻辑。普通停轴、Cluster 查找、基础赔付及常规消除掉落沿用平台通用能力。

## 第一部分：玩法介绍

### 基础游戏

游戏使用 6 列 × 5 行盘面。相同图标在横向或纵向相邻时组成 Cluster，至少 5 个图标即可中奖；Cluster 越大，奖励越高。Wild 可以加入其他普通图标的 Cluster，但不能单独组成中奖。

中奖图标消除时，盘面上其他同 ID 的普通图标也一并消除；未参与中奖的 Wild 不扩展消除。保留图标维持相对顺序，再补充新图标。新盘面继续判断 Cluster，直到不再中奖。额外消除的位置不增加赔付，也不生成金色区域。

Scatter 和 Bonus 不直接存在于原始轴带，而是在盘面生成后替换未参与中奖的普通图标，因此不会破坏本轮已经形成的 Cluster。Scatter 可能转化为 Super Scatter。

Base 盘面中 Scatter 数量不超过 2 个时仍可出现 Bonus。每轮消除掉落最多生成 1 个特殊图标；本次 Base 一旦出现 Bonus，后续消除掉落不再生成新的 Scatter 或 Bonus。

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

一整轮金色玩法最多出现 5 个聚宝盆；达到上限后，后续位置不再生成聚宝盆。

金色玩法最终奖励为当前金币与聚宝盆金额之和，加上过程中获得的全部 JP 奖励。

## 第二部分：数值逻辑

此前 TYPE 0 的校准目标为 Base Cluster 55%、Base Bonus 10%、Free Cluster 13%、Free Bonus 20%，合计 98%。四项均以付费 Base Spin 的累计下注为分母，Free 不额外增加下注分母。当前所有 GROUP/TYPE 已统一使用 Bonus `[GENERAL]` 原有权重，此前独立权重下的实测不能作为当前版本结果，需重新仿真。

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

原始轴带不包含 Scatter 和 Bonus。完成初始盘面判奖后，先记录中奖位置及同 ID 扩展消除位置；候选只允许 ID 3–12 的普通图标，且必须排除这两类位置。Wild、Scatter、Bonus 均不作为候选。

特殊图标生成及 Super Scatter 转化参数按服务器配置位置读取：TYPE 0 使用 `special/yngg_game_server.conf` 的 `[Game Info]`，不读取该文件的 `[0]`；TYPE 4、8、12、17 使用各自数字节。初始特殊图标、掉落替换和轴带仍按 TYPE 配置；统一使用一套参数的范围仅为金色玩法内部的结果类型与奖励档位权重。

Base 按以下顺序处理：

1. 读取当前 TYPE 的 `ScatterCountProbability`，数组下标 0–3 对应生成 0–3 个 Scatter；TYPE 0 权重为 10000/1000/500/107，其他 TYPE 保留 10000/1000/500/57。
2. 将抽取数量限制为候选位置数量，再依次从候选位置中随机放置 Scatter。
3. 只有实际放入的 Scatter 数量为 0–2 且仍有候选位置时，才继续抽取 Bonus；实际放入 3 个 Scatter 或候选已用完时不抽取 Bonus：
   - 初始盘面无奖时读取 `BaseNoWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 98/2。
   - 初始盘面有奖时读取 `BaseWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus；TYPE 0 权重为 964/36，其他 TYPE 保留 92/8。
4. Bonus 在 Scatter 之后从剩余候选位置中随机放置。

Free 先按 `FreeScatterCountProbability` 抽取 Scatter 数量；数组下标 0–3 对应生成 0–3 个，当前权重为 10000/1000/500/57。先将数量限制为可用候选数量并完成放置，再检查实际放入数量。只有实际放入不超过 2 个 Scatter 且仍有候选位置时，才判断 Bonus：

- Spin 开始时已有金色区域，读取 `FreeGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 60/40。
- Spin 开始时没有金色区域，读取 `FreeNoGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 30/70。

实际放入 3 个 Scatter 或候选已用完时，不读取 Free 初始 Bonus 权重。最后一次 Free Spin 也使用此流程，不在初始盘面强制生成 Bonus。

### 消除掉落中的特殊图标

Base 和 Free 每轮消除补牌后使用相同流程检查最终补牌盘面：

- 盘面已有 Bonus：本轮不生成特殊图标。
- Scatter 与 Super Scatter 总数达到 3 个：本轮不生成特殊图标。
- 其余情况只对本轮新补入且符合替换条件的普通图标，按列、列内下标顺序逐格读取掉落权重，直到首次抽中特殊图标或全部候选检查结束。

Base 读取 `DropSpecialSymbolProbability`，Free 读取 `FreeDropSpecialSymbolProbability`；两者当前权重均为：

- 下标 0：不替换，当前权重 998。
- 下标 1：生成 Scatter，当前权重 1。
- 下标 2：生成 Bonus，当前权重 1。

替换候选仅限本轮新补入、ID 为 3–12、且不属于新盘面中奖位置或同 ID 扩展消除位置的图标。每个候选只抽一次；抽中特殊图标后立即替换当前扫描格并停止，不再随机选择另一个位置。无候选时不读取权重。每次掉落过程最多出现 1 个特殊图标，替换不会破坏新盘面已经形成的 Cluster，也不会规避扩展消除。

如果掉落生成 Scatter：

- Base 牌面尚无 Super Scatter 时，立即读取 `SuperScatterProbability`；命中后从全盘现存普通 Scatter 中随机选择 1 个转化，可能选中新补入或此前已存在的 Scatter。
- 牌面已经存在 Super Scatter 时，不再执行转化判断，本次图标保持普通 Scatter。
- Free 不执行 Super Scatter 转化。

### Super Scatter 转化

- Base 初始特殊图标放置结束后，若存在普通 Scatter 且尚无 Super Scatter，则读取一次 `SuperScatterProbability`；命中后随机转化 1 个。
- Base 后续掉落 Scatter 按上一节规则即时判断；一旦盘面已有 Super Scatter，后续 Scatter 不再转化。
- Free 不生成或转化 Super Scatter。
- `SuperScatterProbability` 当前值为 200，按万分比计算，即 1/50。

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

每次 Cluster 消除后，只将实际中奖位置加入金色区域，扩展消除位置不加入。全部消除结束后，最终盘面存在 Bonus 且金色区域非空时进入金色玩法。

- Base 和普通免费完成金色玩法后清空金色区域。
- 超级免费完成金色玩法后保留金色区域。
- Free 结束时清理本轮保留的金色区域。

### 金色位置结果生成

`special/yngg_bonus.conf` 仅使用 `[GENERAL]`。所有 GROUP/TYPE 的主游戏、免费游戏与重翻共用这一套结果类型、金币、四叶草和 JP 参数，不读取数字节覆盖，也不制作 TYPE 专属 Bonus 版本。切换 TYPE 不改变 Bonus 奖励分布；普通轴、免费轴及特殊图标生成概率仍按各自 TYPE 读取。

每个金色位置先读取 `BONUS_SYMBOL_TYPE_PROBABILITY` 抽取结果类型，再读取该类型的档位权重：

- 类型下标固定为 coin、clover、pot、jackpot，不读取 `BONUS_SYMBOL_TYPE`；该字段缺失、注释或更改顺序均不影响类型映射。
- `BONUS_SYMBOL_TYPE_PROBABILITY`：所有 GROUP/TYPE 共用 `[GENERAL]` 的 1000/80/6/2。
- coin：`BONUS_COIN_MULTIPLE` 与 `BONUS_COIN_MULTIPLE_PROBABILITY` 按下标对应。
- clover：`BONUS_CLOVER_MULTIPLE` 与 `BONUS_CLOVER_MULTIPLE_PROBABILITY` 按下标对应。
- jackpot：`BONUS_JP_MULTIPLE` 与 `BONUS_JP_TYPE_PROBABILITY` 按 MINI、MINOR、MAJOR、GRAND 顺序对应。
- pot 不再抽取具体档位。

金币倍数为 0.2/0.5/1/2/3/4/5/10/15/20/25/50/100/250/500。所有 GROUP/TYPE 共用 `[GENERAL]` 金币权重 1560/1240/1030/860/720/545/415/320/228/165/110/62/31/10/3，总权重 7299，抽中金币后的条件平均倍数约 4.516646x。所有档位保留正权重。

小于 `coin_multi_1=5` 显示为铜币；大于等于 5 且小于 `coin_multi_2=25` 显示为银币；大于等于 25 显示为金币。四叶草倍数为 2/3/4/5/10/20，权重为 40/28/16/10/5/1。JP 倍数为 MINI 10x、MINOR 25x、MAJOR 100x、GRAND 5000x，四档权重为 80/25/8/1。四叶草和 JP 档位同样由所有 GROUP/TYPE 共用 `[GENERAL]`。

### 金色玩法结算顺序

1. 生成本轮所有金色位置的结果。
2. 先结算全部四叶草。每个四叶草放大中心九宫格内当前金币和已结算聚宝盆；多个四叶草效果依次累乘，JP 不受影响。
3. 再按 `(Col 升序, Row 降序)` 结算聚宝盆，即先列 0 的 Row 4、3、2、1、0，再列 1 的 Row 4、3、2、1、0，依次到列 5；与服务器 `g_iPotScan` 顺序一致。每个聚宝盆收集当前全部金币及此前已结算聚宝盆；后结算的聚宝盆包含先结算聚宝盆的结果，JP 不参与收集。
4. 所有已结算聚宝盆位置保留，其余位置按“类型 → 具体档位”的顺序重新生成。
5. 重复四叶草、聚宝盆和重翻流程，直到本轮没有新聚宝盆。
6. 每次出现 JP 时立即累计对应 JP 奖励。玩法结束时，再结算当前金币与聚宝盆金额之和。

以上列与行的排序只用于聚宝盆收集结算。翻牌位置、四叶草处理顺序及输出 `cells` 仍按 `(Row, Col)` 升序，类型及档位继续使用原配置权重。

`bonus_max_round=5` 限制整轮金色玩法累计最多生成 5 个聚宝盆。达到上限后，后续类型抽取排除 pot，并按 coin、clover、jackpot 的原相对权重重新抽取。

### 特殊情况处理

- 特殊图标候选位置不足：按抽取顺序使用全部可用位置，超出数量丢弃。
- Base 或 Free 的本轮新补入图标没有可用候选位置：不读取掉落权重，也不放置特殊图标。
- Free Bonus 保底没有候选位置：最终盘面没有可替换普通图标时，本次不放置，不替换中奖位置，也不额外增加 Free Spin。
- Base 或 Free 已有 Bonus，或 Scatter 类图标达到 3 个：本轮掉落不再读取特殊图标权重。
