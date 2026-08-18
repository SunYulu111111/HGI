# 《Si Botak Desa》玩法与数值逻辑

本文分为玩家可感知的玩法介绍和服务器实现所需的定制数值逻辑。普通停轴、Cluster 查找、基础赔付及常规消除掉落沿用平台通用能力。

## 第一部分：玩法介绍

### 基础游戏

游戏使用 6 列 × 5 行盘面。相同图标在横向或纵向相邻时组成 Cluster，至少 5 个图标即可中奖；Cluster 越大，奖励越高。Wild 可以加入其他普通图标的 Cluster，但不能单独组成中奖。

中奖图标消除后，上方图标依次掉落并补充新图标。新盘面继续判断 Cluster，直到不再中奖。

Scatter 和 Bonus 不直接存在于原始轴带，而是在盘面生成后替换未参与中奖的普通图标，因此不会破坏本轮已经形成的 Cluster。Scatter 可能转化为 Super Scatter。

Base 盘面中 Scatter 数量不超过 2 个时仍可出现 Bonus。每轮消除掉落最多生成 1 个特殊图标；本次 Base 一旦出现 Bonus，后续消除掉落不再生成新的 Scatter 或 Bonus。

### 免费游戏

- 最终盘面累计至少 3 个 Scatter 类图标且没有 Super Scatter时，进入普通免费游戏，获得 10 次 Free Spin。
- 最终盘面累计至少 3 个 Scatter 类图标且包含 Super Scatter 时，进入超级免费游戏，获得 10 次 Free Spin。
- Free Spin 中出现 2 个 Scatter 类图标追加 2 次；出现 3 个及以上追加 4 次。Super Scatter 计入 Scatter 类图标总数。
- 触发免费游戏的 Scatter 和 Super Scatter 位置在进入 Free 时直接成为金色区域。
- 一轮完整 Free 至少尝试生成一次 Bonus；如果此前一直没有出现，则在最后一次 Free Spin 执行保底。

普通免费游戏中的金色区域会持续保留，触发金色玩法后清空。超级免费游戏中的金色区域在金色玩法触发后仍然保留，直到本轮超级免费结束。

### 金色玩法

普通图标每次消除的位置都会变为金色区域。全部消除结束后，如果最终盘面仍有 Bonus，则触发金色玩法。

每个金色位置会生成以下一种结果：

- 金币：提供固定倍数奖励。
- 四叶草：放大以自身为中心九宫格内的金币和聚宝盆，不影响 JP。
- 聚宝盆：收集当前金币及已经结算的聚宝盆，不收集 JP，并触发其他位置重翻。
- JP：直接获得 MINI、MINOR、MAJOR 或 GRAND 奖励。

同一轮先结算全部四叶草，再按从上到下、从左到右的顺序结算聚宝盆。所有已结算聚宝盆都会保留，其余位置重新生成结果；如果再次出现聚宝盆，则继续重翻，直到没有新聚宝盆。

金色玩法最终奖励为当前金币与聚宝盆金额之和，加上过程中获得的全部 JP 奖励。

## 第二部分：数值逻辑

### 基础数值

- 押注档位为 100,000 / 200,000 / 500,000 / 1,000,000 / 2,000,000 / 5,000,000 / 10,000,000 / 20,000,000。
- 原始图标 ID 为 0–12：Scatter 使用 0，Wild 使用 1，主盘 Bonus 使用 2，普通赔付图标使用 3–12。
- Super Scatter 由 Scatter 转化，结果 ID 为 13，不计入原始图标数量。
- `ITEM_PRIZES_3` 至 `ITEM_PRIZES_12` 的数组下标为 Cluster 数量减 1，奖值以万分之一下注为单位。

普通图标赔付倍数：

- H1（ID 3）：5 个 1x；6–7 个 2.5x；8–11 个 5x；12 个及以上 25x。
- H2（ID 4）：5 个 1x；6–7 个 2.5x；8–11 个 5x；12 个及以上 10x。
- H3（ID 5）：5 个 0.5x；6–7 个 1x；8–11 个 3x；12 个及以上 5x。
- M1/M2（ID 6/7）：5 个 0.3x；6–7 个 0.5x；8–11 个 1x；12 个及以上 3x。
- L1/L2（ID 8/9）：5 个 0.1x；6–7 个 0.2x；8–11 个 0.5x；12 个及以上 1x。
- L3/L4（ID 10/11）：5 个 0.1x；6–7 个 0.2x；8–11 个 0.3x；12 个及以上 0.6x。
- L5（ID 12）：5 个 0.1x；6–7 个 0.2x；8–11 个 0.3x；12 个及以上 0.5x。

### 初始特殊图标生成

原始轴带不包含 Scatter 和 Bonus。完成初始盘面判奖后，先记录所有参与中奖的位置，只有未参与中奖的普通图标可以成为特殊图标候选。

Base 按以下顺序处理：

1. 读取 `ScatterCountProbability`，数组下标 0–3 对应生成 0–3 个 Scatter，当前权重为 1000/100/50/5。
2. 按抽取数量依次从候选位置中随机放置 Scatter。
3. 当 Scatter 数量为 0–2 时继续判断 Bonus；Scatter 数量为 3 时不生成 Bonus：
   - 初始盘面无奖时读取 `BaseNoWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 80/20。
   - 初始盘面有奖时读取 `BaseWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 90/10。
4. Bonus 在 Scatter 之后放置。候选位置不足时按 Scatter、Bonus 的抽取顺序放满可用位置，超出数量丢弃。

Free 先按 `ScatterCountProbability` 生成 Scatter，再独立判断 Bonus：

- Spin 开始时已有金色区域，读取 `FreeGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 60/40。
- Spin 开始时没有金色区域，读取 `FreeNoGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 30/70。

### 消除掉落中的特殊图标

Base 每轮消除补牌后先检查最终补牌盘面：

- 盘面已有 Bonus：本轮不生成特殊图标。
- Scatter 与 Super Scatter 总数达到 3 个：本轮不生成特殊图标。
- 其余情况才对本轮新掉落图标依次读取 `DropSpecialSymbolProbability`，直到首次抽中特殊图标或全部检查结束。

`DropSpecialSymbolProbability` 的结果为：

- 下标 0：不替换，当前权重 998。
- 下标 1：生成 Scatter，当前权重 1。
- 下标 2：生成 Bonus，当前权重 1。

替换候选仅限本轮新掉落、当前不参与中奖的普通图标位置。抽中特殊图标后，从候选中随机替换 1 个并停止本轮判断，因此每次掉落过程最多出现 1 个特殊图标；没有候选位置时不放置。替换不会改变本轮已经形成的 Cluster。

如果 Base 掉落生成 Scatter：

- 牌面尚无 Super Scatter 时，立即读取 `SuperScatterProbability`；命中后将本次掉落的 Scatter 转化为 Super Scatter。
- 牌面已经存在 Super Scatter 时，不再执行转化判断，本次图标保持普通 Scatter。

Free 不使用 Base 的单次掉落限制，仍对每个新掉落图标分别读取 `DropSpecialSymbolProbability`，并只替换本轮新掉落的非中奖位置。

### Super Scatter 转化

- Base 初始特殊图标放置结束后，若存在普通 Scatter 且尚无 Super Scatter，则读取一次 `SuperScatterProbability`；命中后随机转化 1 个。
- Base 后续掉落 Scatter 按上一节规则即时判断；一旦盘面已有 Super Scatter，后续 Scatter 不再转化。
- Free 在全部消除和掉落结束后，对最终盘面读取一次 `SuperScatterProbability`；命中后随机转化 1 个。
- `SuperScatterProbability` 当前值为 200，按万分比计算，即 1/50。

### 免费游戏触发与状态

完成全部消除、掉落替换和 Super Scatter 转化后，统计最终盘面的 Scatter 与 Super Scatter：

- Scatter 类图标总数达到 3 个及以上且 Super Scatter 数量为 0：使用 `FreeSpinCounts` 第 1 项，当前为 10 次普通免费。
- Scatter 类图标总数达到 3 个及以上且 Super Scatter 数量至少为 1：使用 `FreeSpinCounts` 第 2 项，当前为 10 次超级免费。
- Free 中总数为 2 时，使用 `FreeSpinRetrigger` 下标 2，追加 2 次。
- Free 中总数达到 3 个及以上时，使用 `FreeSpinRetrigger` 最后一档，追加 4 次。

触发位置作为 Free 初始金色区域。Base 同一 Spin 同时满足金色玩法和免费游戏时，先完成金色玩法结算，再进入免费游戏；Base 消除产生的其他金色区域不带入 Free。

每轮 Free 维护“是否已经出现 Bonus”的状态，初始为否，任意 Spin 出现 Bonus 后更新为是，Free 结束时清理。最后一次 Free Spin 仍未出现 Bonus 时，等待全部消除结束，再从最终无奖盘面的普通图标中随机替换 1 个 Bonus；如果最终盘面没有可替换普通图标，则本次不放置。

### 金色玩法触发与状态

每次 Cluster 消除后，将实际消除位置加入金色区域。全部消除结束后，最终盘面存在 Bonus 且金色区域非空时进入金色玩法。

- Base 和普通免费完成金色玩法后清空金色区域。
- 超级免费完成金色玩法后保留金色区域。
- Free 结束时清理本轮保留的金色区域。

### 金色位置结果生成

每个金色位置先读取 `BONUS_SYMBOL_TYPE_PROBABILITY` 抽取结果类型，再读取该类型的档位权重：

- `BONUS_SYMBOL_TYPE` 依次为 coin、clover、pot、jackpot。
- `BONUS_SYMBOL_TYPE_PROBABILITY` 当前权重为 1000/100/10/1。
- coin：`BONUS_COIN_MULTIPLE` 与 `BONUS_COIN_MULTIPLE_PROBABILITY` 按下标对应。
- clover：`BONUS_CLOVER_MULTIPLE` 与 `BONUS_CLOVER_MULTIPLE_PROBABILITY` 按下标对应。
- jackpot：`BONUS_JP_MULTIPLE` 与 `BONUS_JP_TYPE_PROBABILITY` 按 MINI、MINOR、MAJOR、GRAND 顺序对应。
- pot 不再抽取具体档位。

金币倍数为 0.2/0.5/1/2/3/4/5/10/15/20/25/50/100/250/500，当前各档权重均为 1。四叶草倍数为 2/3/4/5/10/20，当前各档权重均为 1。JP 倍数为 MINI 10x、MINOR 25x、MAJOR 100x、GRAND 5000x，当前四档权重均为 1。

### 金色玩法结算顺序

1. 生成本轮所有金色位置的结果。
2. 先结算全部四叶草。每个四叶草放大中心九宫格内当前金币和已结算聚宝盆；多个四叶草效果依次累乘，JP 不受影响。
3. 再按从上到下、从左到右结算聚宝盆。每个聚宝盆收集当前全部金币及此前已结算聚宝盆；后结算的聚宝盆包含先结算聚宝盆的结果，JP 不参与收集。
4. 所有已结算聚宝盆位置保留，其余位置按“类型 → 具体档位”的顺序重新生成。
5. 重复四叶草、聚宝盆和重翻流程，直到本轮没有新聚宝盆。
6. 每次出现 JP 时立即累计对应 JP 奖励。玩法结束时，再结算当前金币与聚宝盆金额之和。

### 特殊情况处理

- 特殊图标候选位置不足：按抽取顺序使用全部可用位置，超出数量丢弃。
- Base 掉落抽中特殊图标但没有可用候选位置：本轮不放置特殊图标。
- Free Bonus 保底没有候选位置：最终盘面没有可替换普通图标时，本次不放置，不替换中奖位置，也不额外增加 Free Spin。
- Base 已有 Bonus 或 Scatter 类图标达到 3 个：后续掉落不再读取特殊图标权重。
