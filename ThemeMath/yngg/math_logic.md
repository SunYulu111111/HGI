# 《Si Botak Desa》数值逻辑

本文供数值策划、服务器程序和数值模拟共同走查，覆盖本机台定制的特殊图标生成、扩展消除、免费游戏状态和金色玩法。普通停轴、基础 Cluster 查找和通用结果下发沿用平台能力。

TYPE 0 Base 自身 Hit 目标为 30%，全部连消 RTP 目标为 40%；Base Bonus 以付费 Base 局数为分母，目标触发率约为 1.25%。初始有奖盘读取 `BaseWinBonusCountProbability` 决定是否放置 Bonus；初始无奖盘读取 `BaseNoWinBonusCountProbability`，可展示 Bonus，但本次 Base 没有实际消除时不触发金色玩法。

TYPE 0 的 Base Bonus RTP 目标为付费 Base 累计下注的 20%。金币中档奖励承担更大的常见概率，四叶草和聚宝盆的类型比例降低；500x 金币、20 倍四叶草及 GRAND 5000x 仍有正概率。波动同时按整轮 Bonus 奖励的绝对标准差与变异系数（标准差 / 均值）核对，不能只用均值增长说明波动降低。当前奖励权重由 Base、普通 Free、Super Free 共用，因此免费 Bonus 和总 RTP 也随之变化；当前实测见 `bonus_type_calibration.json`，不沿用历史免费分项及总 95% 结论。

金色玩法限制由所有 TYPE 共用：一整轮累计最多 5 个聚宝盆、3 个四叶草；首次翻牌及每次重翻的新图标至少有 1 枚普通金币。保留聚宝盆不计入金币保底。普通和超级免费初始次数均为 10 次。Python 仿真不启用服务器 GROUP 选择和砍分。

2026-10-22 的 TYPE 0 历史目标总 RTP 为 95%：Base Cluster / Bonus 为 45% / 20%；普通 Free Cluster / Bonus 约 7.3% / 18%；Super Free Cluster / Bonus 约 0.7% / 4%。Base Bonus、普通 Free、Super Free 的历史目标触发率分别为 1.25%、0.5%、0.05%。六项 RTP 均以付费 Base 累计下注为分母。`rtp_calibration.json`、`rtp_calibration_runs.json` 和 10 月 22 日性能数据均对应 2026-10-23 共享翻牌限制实施前的版本，不能作为当前规则已达到上述目标或性能水平的依据。实参以当前配置为准。

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

正常轴带不直接包含 Scatter 和 Bonus。正常轴 / 特殊轴初盘完成 Cluster 判断并得到全部实际消除位置后，再生成特殊图标。

TYPE 0 Base 使用 `BASE_RATE=8580,1420,0,0`，按 85.8% / 14.2% 选择 `NORMAL_ROLL` / `SP_ROLL`，选定的轴贯穿本次全部消除补牌。FIX、ZERO 的抽取权重均为 0，预设内容保留。Base Bonus 入口由初始特殊图标权重控制：有奖盘通过 `BaseWinBonusCountProbability` 校准实际触发率；无奖盘通过 `BaseNoWinBonusCountProbability` 展示 Bonus。

特殊图标生成与 Super Scatter 转化参数按 TYPE 读取：TYPE 0 读取 `special/yngg_game_server.conf` 的 `[Game Info]`，不读取该文件的 `[0]`；TYPE 4、8、12、17 读取各自数字节。Bonus 先读 `[GENERAL]`，仅 TYPE 0 再应用命名节 `[Type0]` 的四组权重；其他 TYPE 原权重保留，旧数字节不参与读取。

1. 读取当前 TYPE 的 `ScatterCountProbability`。数组下标 0–3 对应 0–3 个 Scatter；实际权重见当前 TYPE 配置。
2. 将抽取数量限制为候选位置数量，再从不属于实际消除位置的 ID 3–12 普通图标中随机选择不同位置放置 Scatter；Wild、Scatter、Bonus 均不作为候选。
3. 只有实际放入的 Scatter 为 0–2 个且仍有候选时才继续抽取 Bonus；实际放入 3 个或候选用完时跳过 Bonus 抽样。
4. 初始盘面无奖时读取 `BaseNoWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus。TYPE 0 的 `98,2` 表示满足此分支条件时有 2% 的展示概率；没有实际消除时不触发金色玩法。
5. 初始盘面有奖时读取 `BaseWinBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus。其条件概率需结合有奖盘占比、Scatter 互斥和候选数量，校准到每次付费 Base 约 1.25% 的实际触发率。
6. Bonus 在 Scatter 之后从剩余候选位置中随机放置。

以上顺序保证 Base 不会同时触发免费游戏和金色玩法：3 个 Scatter 时不生成 Bonus；Bonus 出现时 Scatter 类图标最多为 2 个，且后续掉落不再生成特殊图标。

## Base 消除掉落特殊图标

每轮消除补牌后先检查：

- 盘面存在 Bonus：本轮不读取掉落特殊图标权重。
- Scatter 类图标总数达到 3 个：本轮不读取掉落特殊图标权重。
- 其余情况继续执行掉落特殊图标判断。

在补牌后的新盘面重新计算中奖位置与扩展消除位置。只对本轮新补入、ID 为 3–12、且不属于这两类位置的候选，按列、列内下标顺序逐格读取 `DropSpecialSymbolProbability`：

- 下标 0：不替换。
- 下标 1：生成 Scatter。
- 下标 2：生成 Bonus；TYPE 0 Base 的此项权重为 0，其他 TYPE 保留原值。

实际权重见当前 TYPE 的 `DropSpecialSymbolProbability`。

每个候选只抽一次，首次抽中 Scatter 或 Bonus 后直接替换当前扫描格并停止，因此一次掉落过程最多生成 1 个特殊图标。未中奖 Wild 不参与抽样；没有候选时不读取权重，也不放置。

Base 掉落生成 Scatter 且盘面没有 Super Scatter 时，立即读取当前 TYPE 的 `SuperScatterProbability`，按万分比计算。命中后从全盘现存普通 Scatter 中随机选择 1 个转化，允许选中此前已有的 Scatter。盘面已有 Super Scatter 时，不再执行转化判断。Free 不执行转化。

## Base Super Scatter

Base 初始特殊图标放置完成后，如果存在普通 Scatter 且尚无 Super Scatter，读取一次 `SuperScatterProbability`；命中后从普通 Scatter 中随机选择 1 个转化。

后续掉落 Scatter 按上一节即时判断。一旦盘面已有 Super Scatter，后续 Scatter 保持普通 Scatter，因此单次 Base Spin 最多出现 1 个 Super Scatter。

转化仅更新 `super_scatter_positions`，盘面 Symbol 仍为 Scatter ID 0。发生消除掉落时，该位置随 Scatter 一起移动并更新坐标；最终盘面、日志和客户端结果均通过位置状态识别 Super Scatter。

Base 最终 Scatter 类图标最多为 3 个，只允许以下免费触发结果：

- 3 个普通 Scatter：普通免费。
- 2 个普通 Scatter和 1 个 Super Scatter：超级免费。

## Free 初始特殊图标

Free 不生成也不转化 Super Scatter，单次 Spin 最多出现 3 个普通 Scatter。

1. 读取 `FreeScatterCountProbability`，下标 0–3 对应 0–3 个 Scatter，权重见当前 TYPE 配置；先把抽取数量限制为可用候选数量，再随机放置。
2. 只有实际放入的 Scatter 不超过 2 个且仍有剩余候选时，才抽取 Bonus。实际放入 3 个或候选已用完时，不读取 Bonus 权重。
3. Spin 开始时已有金色区域，读取 `FreeGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，权重见当前 TYPE 配置。
4. Spin 开始时没有金色区域，读取 `FreeNoGoldenBonusCountProbability`，下标 0/1 对应 0/1 个 Bonus，权重见当前 TYPE 配置。
5. Scatter 和 Bonus 均从不属于实际消除位置的 ID 3–12 普通图标中随机选择位置，不替换 Wild；Scatter 先放，Bonus 只使用剩余候选。
6. 最后一次 Free Spin 的初始盘面仍执行以上正常流程，不因此前未出现 Bonus 而强制生成。

## Free 消除掉落特殊图标

Free 使用与 Base 相同的单次掉落限制：

- 盘面存在 Bonus，或普通 Scatter 已达到 3 个时，本轮不读取掉落权重。
- 其余情况对新补入且符合条件的候选逐格读取 `FreeDropSpecialSymbolProbability`，扫描顺序与 Base 相同。
- 下标 0/1/2 分别表示不替换、Scatter、Bonus，具体权重见当前 TYPE 配置。
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

每次 Cluster 消除后，将中奖位置加入金色区域，扩展消除位置不加入。全部消除结束后，最终盘面存在 Bonus 且金色区域非空时触发金色玩法。每次 Base 的金色区域从空集合开始，不继承前一局；本次没有实际消除时，Bonus 仅展示，不触发金色玩法，也不产生 Bonus 奖励。

- Base 触发后清空本次金色区域。
- 普通免费触发后清空已累积金色区域。
- 超级免费触发后保留金色区域。
- Free 结束时清理所有保留状态。

## 金色位置结果生成

`special/yngg_bonus.conf` 的 `[GENERAL]` 保留共用奖值档位和默认权重。TYPE 0 按 `[GENERAL]` → `[Type0]` 读取，`[Type0]` 只允许以下四个 PascalCase 权重字段；缺失项继承 `[GENERAL]`：

| TYPE 0 覆盖字段 | 对应 `[GENERAL]` 字段 | 作用 |
| --- | --- | --- |
| `BonusSymbolTypeProbability` | `BONUS_SYMBOL_TYPE_PROBABILITY` | coin / clover / pot / jackpot 类型权重 |
| `BonusCoinMultipleProbability` | `BONUS_COIN_MULTIPLE_PROBABILITY` | 金币档位权重 |
| `BonusCloverMultipleProbability` | `BONUS_CLOVER_MULTIPLE_PROBABILITY` | 四叶草档位权重 |
| `BonusJpTypeProbability` | `BONUS_JP_TYPE_PROBABILITY` | MINI / MINOR / MAJOR / GRAND 权重 |

TYPE 4、8、12、17 继续读取 `[GENERAL]` 原权重，不使用 `[Type0]`；数字节 `[0]` 等旧覆盖不生效。每次切换 TYPE 使用其对应的有效权重，Base、普通 Free、Super Free 和重翻使用同一 TYPE 的权重。奖值数组、图标映射及四叶草/聚宝盆结算顺序保持不变。新翻格先应用共享上限与 coin 保底；非强制 coin 时仍先抽允许的类型，再抽对应档位。

每个新翻位置先应用共享上限与 coin 保底，再按以下配置抽取；强制 coin 时仅抽取金币档位：

- 类型下标固定为 coin、clover、pot、jackpot，不依赖 `BONUS_SYMBOL_TYPE`。该字段缺失、注释或改写不会改变映射。
- 类型权重：TYPE 0 使用 `[Type0].BonusSymbolTypeProbability`，其他 TYPE 保留 `[GENERAL]` 的 1000/80/6/2。
- coin 使用 `BONUS_COIN_MULTIPLE` 和 `BONUS_COIN_MULTIPLE_PROBABILITY`，两个数组按下标对应。
- clover 使用 `BONUS_CLOVER_MULTIPLE` 和 `BONUS_CLOVER_MULTIPLE_PROBABILITY`，两个数组按下标对应。
- jackpot 使用 `BONUS_JP_MULTIPLE` 和 `BONUS_JP_TYPE_PROBABILITY`，按 MINI、MINOR、MAJOR、GRAND 顺序对应。
- pot 不再抽取具体档位。

金币倍数保留 0.2/0.5/1/2/3/4/5/10/15/20/25/50/100/250/500，四叶草倍数保留 2/3/4/5/10/20。TYPE 0 使用 `[Type0]` 的金币、四叶草权重；其他 TYPE 保留 `[GENERAL]` 原权重。TYPE 0 提高中档金币概率、降低放大型图标比例，并保留全部最高档位的正概率。

TYPE 0 的类型权重为 `10081,40,6,5`，顺序为金币、四叶草、聚宝盆、JP。金币低组 0.2/0.5/1 各占金币档位抽样的 16.2%，高组 100/250/500 各占 0.0185%，金币条件均值为 1.99034x；四叶草均值仍为 4.42，JP 档位权重仍为 `80,25,8,1`。类型比例、金币档位与当前实测见 `PARAMETERS.md`。金币均值 0.7238369x、类型 5000/58/6/2 及 ZERO 大金格属于历史数值，不作为当前 Base Bonus 分布。

金币显示类型由 `coin_multi_1` 和 `coin_multi_2` 分档：

- 倍数小于 `coin_multi_1=5`：铜币。
- 倍数大于等于 5 且小于 `coin_multi_2=25`：银币。
- 倍数大于等于 25：金币。

JP 倍数保持 MINI 10x、MINOR 25x、MAJOR 100x、GRAND 5000x。TYPE 0 的有效权重见 `[Type0].BonusJpTypeProbability`；其他 TYPE 的公共权重保留 80/25/8/1。

`BONUS_1` 至 `BONUS_10` 依次表示彩虹 Bonus、铜币、银币、金币、四叶草、聚宝盆、MINI、MINOR、MAJOR、GRAND 的服务端结果类型。

## 金色玩法结算

1. 按共享上限与本批 coin 保底规则，逐格生成本批金色位置的类型和具体档位。
2. 先结算全部四叶草。四叶草放大中心九宫格内当前金币和已结算聚宝盆；多个四叶草效果累乘，JP 不受影响。
3. 再按 `(Col 升序, Row 降序)` 结算聚宝盆，即先列 0 的 Row 4、3、2、1、0，再列 1 的 Row 4、3、2、1、0，依次到列 5。展平下标顺序为服务器 `g_iPotScan` 的 `4,3,2,1,0,9,8,7,6,5,...`。每个聚宝盆收集当前全部金币和此前已结算聚宝盆；后结算的聚宝盆包含先结算聚宝盆的结果，JP 不参与收集。
4. 所有已结算聚宝盆位置保留，其余位置按上述上限与金币保底规则重新生成；非强制金币时按“类型 → 具体档位”抽取。
5. 如果重翻再次出现聚宝盆，重复四叶草、聚宝盆和重翻流程，直到没有新聚宝盆。
6. 每次出现 JP 时立即累计对应奖励。玩法结束时，再结算当前金币与聚宝盆金额之和。

聚宝盆的收集顺序按服务器实现执行。翻牌位置、四叶草处理顺序及输出 `cells` 继续使用 `(Row, Col)` 升序；类型及档位权重不变。

所有 TYPE 的 Base、普通 Free、Super Free 均共用 `special/yngg_game_server.conf` 的 `[Game Info]` 限制，不从数字 TYPE 节或 Bonus `[Type0]` 读取：

| 字段 | 当前值 | 作用 |
| --- | ---: | --- |
| `BonusMaxPotCount` | 5 | 整轮金色玩法累计可生成的聚宝盆上限 |
| `BonusMaxCloverCount` | 3 | 整轮金色玩法累计可生成的四叶草上限 |
| `BonusRevealMinCoinCount` | 1 | 每批新翻图标必须包含的最少 coin 数 |

`BonusMaxPotCount` 缺失时，读取旧字段 `bonus_max_round`，两者都缺失时默认 5；新字段存在时优先使用新字段。四叶草与 coin 字段缺失时分别默认 3 和 1。Pot、Clover 计数跨首次翻牌及全部重翻累计，已结算或被后续翻牌覆盖的四叶草仍计入累计数；保留 Pot 不重复计数，也不计入 coin 保底。计数只覆盖单次金色玩法触发及其全部重翻，结束后重置；Super Free 仅保留金格，下次独立 Bonus 重新计数，不跨整轮 Free session 共用上限。

每批新翻格按 `(Row, Col)` 升序逐格生成。每翻出一格便立即更新累计 Pot、Clover 及本批 coin 数；达到任一累计上限后，在后续格抽类型前将对应类型排除，按剩余允许类型的原相对权重抽取。剩余未翻格数（包含当前格）等于仍需补足的 coin 数时，直接生成 coin，仅按金币档位权重抽取具体奖值，跳过类型随机抽取。配置最少 coin 数大于 0、且合法类型的权重已全部归零时，也直接抽取 coin 档位。其他情况仍先抽允许的类型，再抽该类型的档位。

首次翻牌的本批范围为全部金色位置；聚宝盆结算后重翻的本批范围仅为需要重新生成的非 Pot 位置。保留 Pot 即使已有金额，也不能代替本批新 coin。不能先抽出整批再删除超限结果，也不通过整批重抽实现保底。待翻位置少于配置要求的 coin 数时视为无效。外部 `golden_rounds` 同样逐批校验 coin 最少数及整轮 Pot、Clover 上限；允许已有接口支持的部分位置回放，但每个提供的批次必须满足限制。

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
- 金色玩法累计聚宝盆达到 5 个或四叶草达到 3 个：后续格抽取前排除对应类型；每批新翻图标仍满足 coin 保底。
