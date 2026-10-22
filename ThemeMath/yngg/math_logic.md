# 《Si Botak Desa》数值逻辑

本文供数值策划、服务器程序和数值模拟共同走查，覆盖本机台定制的特殊图标生成、扩展消除、免费游戏状态和金色玩法。普通停轴、基础 Cluster 查找和通用结果下发沿用平台能力。

TYPE 0 此前校准目标为 Base Cluster 55%、Base Bonus 10%、Free Cluster 13%、Free Bonus 20%，合计 98%。四项 RTP 统一使用付费 Base Spin 的累计下注作分母，Free 不增加下注分母。当前所有 GROUP/TYPE 共用 Bonus `[GENERAL]` 原有权重，需重新验证各分项；普通轴、免费轴与特殊图标生成概率仍按 TYPE 区分。

## 术语说明

- 中奖位置：实际组成中奖 Cluster 的普通图标和 Wild 位置，参与赔付。
- 扩展消除位置：与中奖普通图标同 ID、但未组成中奖 Cluster 的其他普通图标位置。
- 实际消除位置：中奖位置与扩展消除位置的并集。
- 金色区域：只由中奖位置生成，不包含扩展消除位置。
- Scatter 类图标：普通 Scatter 与 Super Scatter 的合计。

## 基础盘面与赔付

- 盘面为 6 列 × 5 行。
- 原始图标 ID 为 0–12：Scatter 为 0、Wild 为 1、主盘 Bonus 为 2、普通赔付图标为 3–12。
- Super Scatter 为普通 Scatter 的转化状态，仍使用 ID 0，通过 `super_scatter_positions` 记录其位置，不使用专门 Symbol ID。
- Cluster 仅按水平、垂直相邻判断，至少 5 个图标起奖。
- Wild 可以加入任意普通图标 Cluster，但不能单独中奖。
- `ITEM_PRIZES_3` 至 `ITEM_PRIZES_12` 的数组下标为 Cluster 数量减 1，奖值以万分之一下注为单位。

赔付倍数：

- H1（ID 3）：5 个 1x；6–7 个 2.5x；8–11 个 5x；12 个及以上 25x。
- H2（ID 4）：5 个 1x；6–7 个 2.5x；8–11 个 5x；12 个及以上 10x。
- H3（ID 5）：5 个 0.5x；6–7 个 1x；8–11 个 3x；12 个及以上 5x。
- M1/M2（ID 6/7）：5 个 0.3x；6–7 个 0.5x；8–11 个 1x；12 个及以上 3x。
- L1/L2（ID 8/9）：5 个 0.1x；6–7 个 0.2x；8–11 个 0.5x；12 个及以上 1x。
- L3/L4（ID 10/11）：5 个 0.1x；6–7 个 0.2x；8–11 个 0.3x；12 个及以上 0.6x。
- L5（ID 12）：5 个 0.1x；6–7 个 0.2x；8–11 个 0.3x；12 个及以上 0.5x。

## Cluster 扩展消除

每轮判奖后按以下顺序处理：

1. 找出所有中奖 Cluster，计算中奖位置、中奖普通图标 ID 和本轮赔付。
2. 对每个中奖普通图标 ID，查找盘面上其他相同 ID 的普通图标并加入扩展消除位置。
3. Wild 只有实际参与中奖 Cluster 时才消除；未参与中奖的 Wild 不加入扩展消除位置。
4. 赔付只使用中奖 Cluster 的图标数量，扩展消除位置不增加赔付。
5. 金色区域只加入中奖位置，扩展消除位置不生成金色区域。
6. 删除全部实际消除位置并执行掉落补牌。

初始特殊图标和掉落特殊图标的候选位置必须排除本轮全部实际消除位置，不能通过替换规避同 ID 扩展消除。

## 正向补牌与轴游标

对每列 `board[Col][Row]`，删除全部实际消除位置后，幸存图标维持原相对顺序并占据数组低下标；新图标占据其后的高下标，拼成 `NewColumn = Survivors + NewItems`。新图标从同一轴当前窗口后方沿正方向连续读取，而非从窗口前方反向读取。

`NextReelIndexes` 保存各列下一次正向补牌的轴下标。正常轴盘和特殊轴盘初始化为 `(StartIndex + 5) % ReelLength`；补入 `Count` 个图标后推进为 `(NextReelIndexes[Col] + Count) % ReelLength`。未删牌的列不推进。FIX、ZERO 从正常轴随机选择入口，随后沿正向连续补牌。显式注入初始盘只替换盘面，补牌延续原停轴状态的轴与游标，不重新随机选择入口。已有 `top_indexes` 保留初始停轴及旧接口语义。

Scatter 和 Super Scatter 随幸存图标移动；金色区域固定在盘面坐标，不随图标移动。扩展消除只增加补牌数量，不改变本轮已计算的赔付和金色区域。

## Base 初始特殊图标

原始轴带不直接包含 Scatter 和 Bonus。初始盘面完成 Cluster 判断并得到全部实际消除位置后，再生成特殊图标。

特殊图标生成与 Super Scatter 转化参数均按服务器配置位置读取：TYPE 0 读取 `special/yngg_game_server.conf` 的 `[Game Info]`，不读取该文件的 `[0]`；TYPE 4、8、12、17 读取各自数字节。Bonus 奖励权重则统一读取独立文件的 `[GENERAL]`，所有 GROUP/TYPE 共用，不合并数字节。

1. 读取当前 TYPE 的 `ScatterCountProbability`。数组下标 0–3 对应 0–3 个 Scatter；TYPE 0 权重为 10000/1000/500/107，其他 TYPE 保留 10000/1000/500/57。
2. 将抽取数量限制为候选位置数量，再从不属于实际消除位置的 ID 3–12 普通图标中随机选择不同位置放置 Scatter；Wild、Scatter、Bonus 均不作为候选。
3. 只有实际放入的 Scatter 为 0–2 个且仍有候选时才继续抽取 Bonus；实际放入 3 个或候选用完时跳过 Bonus 抽样。
4. 初始盘面无奖时读取 `BaseNoWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 98/2。
5. 初始盘面有奖时读取 `BaseWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus；TYPE 0 权重为 964/36，其他 TYPE 保留 92/8。
6. Bonus 在 Scatter 之后从剩余候选位置中随机放置。

以上顺序保证 Base 不会同时触发免费游戏和金色玩法：3 个 Scatter 时不生成 Bonus；Bonus 出现时 Scatter 类图标最多为 2 个，且后续掉落不再生成特殊图标。

## Base 消除掉落特殊图标

每轮消除补牌后先检查：

- 盘面存在 Bonus：本轮不读取掉落特殊图标权重。
- Scatter 类图标总数达到 3 个：本轮不读取掉落特殊图标权重。
- 其余情况继续执行掉落特殊图标判断。

在补牌后的新盘面重新计算中奖位置与扩展消除位置。只对本轮新补入、ID 为 3–12、且不属于这两类位置的候选，按列、列内下标顺序逐格读取 `DropSpecialSymbolProbability`：

- 下标 0：不替换，当前权重 998。
- 下标 1：生成 Scatter，当前权重 1。
- 下标 2：生成 Bonus，当前权重 1。

每个候选只抽一次，首次抽中 Scatter 或 Bonus 后直接替换当前扫描格并停止，因此一次掉落过程最多生成 1 个特殊图标。未中奖 Wild 不参与抽样；没有候选时不读取权重，也不放置。

Base 掉落生成 Scatter 且盘面没有 Super Scatter 时，立即读取 `SuperScatterProbability`；当前值 200，按万分比计算为 1/50。命中后从全盘现存普通 Scatter 中随机选择 1 个转化，允许选中此前已有的 Scatter。盘面已有 Super Scatter 时，不再执行转化判断。Free 不执行转化。

## Base Super Scatter

Base 初始特殊图标放置完成后，如果存在普通 Scatter 且尚无 Super Scatter，读取一次 `SuperScatterProbability`；命中后从普通 Scatter 中随机选择 1 个转化。

后续掉落 Scatter 按上一节即时判断。一旦盘面已有 Super Scatter，后续 Scatter 保持普通 Scatter，因此单次 Base Spin 最多出现 1 个 Super Scatter。

转化仅更新 `super_scatter_positions`，盘面 Symbol 仍为 Scatter ID 0。发生消除掉落时，该位置随 Scatter 一起移动并更新坐标；最终盘面、日志和客户端结果均通过位置状态识别 Super Scatter。

Base 最终 Scatter 类图标最多为 3 个，只允许以下免费触发结果：

- 3 个普通 Scatter：普通免费。
- 2 个普通 Scatter和 1 个 Super Scatter：超级免费。

## Free 初始特殊图标

Free 不生成也不转化 Super Scatter，单次 Spin 最多出现 3 个普通 Scatter。

1. 读取 `FreeScatterCountProbability`，下标 0–3 对应 0–3 个 Scatter，当前权重为 10000/1000/500/57；先把抽取数量限制为可用候选数量，再随机放置。
2. 只有实际放入的 Scatter 不超过 2 个且仍有剩余候选时，才抽取 Bonus。实际放入 3 个或候选已用完时，不读取 Bonus 权重。
3. Spin 开始时已有金色区域，读取 `FreeGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 60/40。
4. Spin 开始时没有金色区域，读取 `FreeNoGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，当前权重为 30/70。
5. Scatter 和 Bonus 均从不属于实际消除位置的 ID 3–12 普通图标中随机选择位置，不替换 Wild；Scatter 先放，Bonus 只使用剩余候选。
6. 最后一次 Free Spin 的初始盘面仍执行以上正常流程，不因此前未出现 Bonus 而强制生成。

## Free 消除掉落特殊图标

Free 使用与 Base 相同的单次掉落限制：

- 盘面存在 Bonus，或普通 Scatter 已达到 3 个时，本轮不读取掉落权重。
- 其余情况对新补入且符合条件的候选逐格读取 `FreeDropSpecialSymbolProbability`，扫描顺序与 Base 相同。
- 下标 0/1/2 分别表示不替换、Scatter、Bonus，当前权重为 998/1/1。
- 首次抽中特殊图标后直接替换当前扫描格并停止，一次掉落过程最多生成 1 个。
- 候选位置仅限本轮新补入、ID 3–12、且不属于下一轮中奖或扩展消除位置的普通图标；Wild 不作为候选，无候选时不读取权重。
- Free 中不执行 Super Scatter 转化。

## 免费触发、再触发与状态

- Base 最终为 3 个普通 Scatter 时，使用 `FreeSpinCounts` 第 1 项，获得 10 次普通免费。
- Base 最终为 2 个普通 Scatter和 1 个 Super Scatter 时，使用 `FreeSpinCounts` 第 2 项，获得 10 次超级免费。
- Free 最终出现 2 个普通 Scatter 时，使用 `FreeSpinRetrigger` 下标 2，追加 2 次。
- Free 最终出现 3 个普通 Scatter时，使用 `FreeSpinRetrigger` 下标 3，追加 4 次。

Base 的特殊图标生成顺序保证免费触发和 Bonus 不会同中。Free 正常生成流程允许 2 个 Scatter 的再触发与 Bonus 同中；初盘实际放入 3 个 Scatter 时跳过正常 Bonus 抽取。若满足末局终盘保底条件，则由保底流程另行尝试补入 Bonus。

Base 触发免费游戏时不带入 Scatter 位置或 Base 消除位置产生的金色区域，Free 初始金色区域为空。普通免费中的金色区域跨 Spin 保留，触发金色玩法后清空。超级免费中的金色区域跨 Spin 保留，触发金色玩法后不清空，直到本轮超级免费结束。

每轮 Free 维护“是否出现过 Bonus”的状态，初始为否，任意 Spin 出现 Bonus 后更新为是，Free 结束时清理。最后一次 Free Spin 的初始盘面不强制生成 Bonus；此前及本次正常生成流程均未出现 Bonus 时，才在全部消除结束、不再中奖的终盘尝试放置 1 个 Bonus。没有可替换普通图标时不放置、不替换中奖位置，也不额外增加 Free Spin。

## 金色玩法触发

每次 Cluster 消除后，将中奖位置加入金色区域，扩展消除位置不加入。全部消除结束后，最终盘面存在 Bonus 且金色区域非空时触发金色玩法。

- Base 触发后清空本次金色区域。
- 普通免费触发后清空已累积金色区域。
- 超级免费触发后保留金色区域。
- Free 结束时清理所有保留状态。

## 金色位置结果生成

Bonus 参数只读取 `special/yngg_bonus.conf` 的 `[GENERAL]`。所有 GROUP/TYPE 的主游戏、免费游戏与重翻共用同一套结果类型、金币、四叶草和 JP 参数；数字节不参与读取，不再维护 TYPE 专属 Bonus 权重。TYPE 切换不会改变金色玩法内部的奖励分布，但轴带和初始、掉落特殊图标概率仍按 TYPE 区分。

每个金色位置先抽取结果类型，再抽取对应档位：

- 类型下标固定为 coin、clover、pot、jackpot，不依赖 `BONUS_SYMBOL_TYPE`。该字段缺失、注释或改写不会改变映射。
- `BONUS_SYMBOL_TYPE_PROBABILITY` 为对应类型权重，所有 GROUP/TYPE 共用 `[GENERAL]` 的 1000/80/6/2。
- coin 使用 `BONUS_COIN_MULTIPLE` 和 `BONUS_COIN_MULTIPLE_PROBABILITY`，两个数组按下标对应。
- clover 使用 `BONUS_CLOVER_MULTIPLE` 和 `BONUS_CLOVER_MULTIPLE_PROBABILITY`，两个数组按下标对应。
- jackpot 使用 `BONUS_JP_MULTIPLE` 和 `BONUS_JP_TYPE_PROBABILITY`，按 MINI、MINOR、MAJOR、GRAND 顺序对应。
- pot 不再抽取具体档位。

金币倍数为 0.2/0.5/1/2/3/4/5/10/15/20/25/50/100/250/500。所有 GROUP/TYPE 共用 `[GENERAL]` 金币权重 1560/1240/1030/860/720/545/415/320/228/165/110/62/31/10/3，总权重 7299，抽中金币后的条件平均倍数约 4.516646x。四叶草倍数为 2/3/4/5/10/20，所有 GROUP/TYPE 共用权重 40/28/16/10/5/1。

金币显示类型由 `coin_multi_1` 和 `coin_multi_2` 分档：

- 倍数小于 `coin_multi_1=5`：铜币。
- 倍数大于等于 5 且小于 `coin_multi_2=25`：银币。
- 倍数大于等于 25：金币。

JP 倍数应配置为 MINI 10x、MINOR 25x、MAJOR 100x、GRAND 5000x，四档当前权重为 80/25/8/1。

`BONUS_1` 至 `BONUS_10` 依次表示彩虹 Bonus、铜币、银币、金币、四叶草、聚宝盆、MINI、MINOR、MAJOR、GRAND 的服务端结果类型。

## 金色玩法结算

1. 为本轮需要生成的全部金色位置抽取类型和具体档位。
2. 先结算全部四叶草。四叶草放大中心九宫格内当前金币和已结算聚宝盆；多个四叶草效果累乘，JP 不受影响。
3. 再按 `(Col 升序, Row 降序)` 结算聚宝盆，即先列 0 的 Row 4、3、2、1、0，再列 1 的 Row 4、3、2、1、0，依次到列 5。展平下标顺序为服务器 `g_iPotScan` 的 `4,3,2,1,0,9,8,7,6,5,...`。每个聚宝盆收集当前全部金币和此前已结算聚宝盆；后结算的聚宝盆包含先结算聚宝盆的结果，JP 不参与收集。
4. 所有已结算聚宝盆位置保留，其余位置重新执行“类型 → 具体档位”抽取。
5. 如果重翻再次出现聚宝盆，重复四叶草、聚宝盆和重翻流程，直到没有新聚宝盆。
6. 每次出现 JP 时立即累计对应奖励。玩法结束时，再结算当前金币与聚宝盆金额之和。

聚宝盆的收集顺序按服务器实现执行。翻牌位置、四叶草处理顺序及输出 `cells` 继续使用 `(Row, Col)` 升序；类型及档位权重不变。

`bonus_max_round=5` 表示一整轮金色玩法最多生成 5 个聚宝盆。聚宝盆计数跨全部重翻轮次累计；达到 5 个后，后续类型抽取排除 pot，并按 coin、clover、jackpot 的原相对权重重新抽取。外部指定结果若包含超过 5 个聚宝盆，视为无效结果。

## 押注档位

使用 `BaseScore=10000` 和 `BBetScopes` 计算总押注。最终使用 8 档：

- 10 → 100,000
- 20 → 200,000
- 50 → 500,000
- 100 → 1,000,000
- 200 → 2,000,000
- 500 → 5,000,000
- 1000 → 10,000,000
- 2000 → 20,000,000

## 特殊情况处理

- 初始特殊图标候选不足：按 Scatter、Bonus 顺序使用全部可用位置，超出数量丢弃。
- 本轮新补入图标没有可用候选：不读取掉落权重，也不放置。
- Base 或 Free 已有 Bonus，或 Scatter 达到上限：本轮不再读取掉落特殊图标权重。
- Free Bonus 保底没有候选：本次不放置，不替换中奖位置，也不追加额外 Free Spin。
- Base 同一 Spin 的 Super Scatter 数量上限为 1；Free 中 Super Scatter 数量固定为 0。
- 金色玩法聚宝盆达到 5 个：后续抽中 pot 时排除 pot 并按其余类型权重重抽。
