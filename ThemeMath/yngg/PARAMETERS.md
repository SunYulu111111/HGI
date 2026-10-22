# yngg 参数与功能实现说明

本文只描述配置参数、脚本参数与功能实现之间的对应关系。玩法规则见 `LOGIC.md`。

TYPE 0 此前设定的目标分项如下，均以付费 Base Spin 的累计下注为分母，Free 不增加下注分母。当前所有 GROUP/TYPE 已改为共用 Bonus `[GENERAL]` 原有权重，下表目标需重新仿真核验，历史实测不代表当前结果。轴带和特殊图标生成参数仍按 TYPE 区分。

| 分项 | RTP 目标 |
| --- | ---: |
| Base Cluster | 55% |
| Base Bonus | 10% |
| Free Cluster | 13% |
| Free Bonus | 20% |
| 合计 | 98% |

## 1. 盘面与图标

`special/yngg_game_config.conf` 提供基础盘面和赔付参数：

- 使用 `COL_COUNT=6` 和 `ROW_COUNT=5` 生成 6 列 × 5 行盘面。
- 使用 `ITEM_COUNT=13` 定义 0–12 共 13 个原始图标。
- 使用 `USE_WILDS` 决定哪些普通图标允许 Wild 参与。
- 使用 `BASE_NUMS` 指定普通图标至少需要 5 个才能起奖。
- 使用 `ITEM_PRIZES_3` 至 `ITEM_PRIZES_12` 根据 Cluster 数量计算赔付。
- 使用 `LINE_MODE`、`BOTH_SIDES`、`FULL_WILD_LINE`、`RULE_COUNT` 和可选的 `LINE_RULES_N` 保留通用 Pay Line 格式。
- 使用 `SCATTER_MODE`、`SCATTER_ID`、`SCATTER_COLS`、`SCATTER_SERIAL`、`SCATTER_MULTIPLES` 和 `SCATTER_PRIZES` 保留通用 Scatter 格式。
- 使用 `GRID_DISABLES` 和 `GRID_DISABLES_FREE` 决定主游戏、免费游戏的有效格子。

`ThemeMath.cal_item_list()` 读取以上参数，完成 Cluster 查找、Wild 参与判断和赔付计算。

`special/yngg_game_server.conf` 的 `[Game Info]` 保存通用玩法参数及 TYPE 0 的特殊图标生成、Scatter 转化参数。TYPE 0 只读取该节，不读取该文件的 `[0]`；TYPE 4、8、12、17 则读取各自数字节。此位置规则与服务器一致，初始和掉落特殊图标概率仍按 TYPE 区分；金色玩法内部的奖励参数统一使用 Bonus 文件的 `[GENERAL]`。Wild ID 1、主盘 Bonus ID 2、Scatter 与 Super Scatter 共用 ID 0；Super Scatter 通过 `super_scatter_positions` 位置状态区分，不使用专门 ID：

- 使用 `SuperScatterProbability=200` 设置每个 Spin 的转化概率；概率单位为万分比，200/10000 等于 1/50。
- 使用 `coin_multi_1=5`、`coin_multi_2=25` 将金币倍数划分为铜币、银币和金币。
- 使用 `bonus_max_round=5` 限制整轮 Bonus 累计最多生成 5 个聚宝盆；达到上限后排除 pot 并按其他类型权重重抽。

Base 初始特殊图标生成后执行一次转化判断；Base 后续掉落生成 Scatter 且盘面没有 Super Scatter 时，也执行一次转化判断，成功后从全盘现存普通 Scatter 中随机选择 1 个，不限于本次掉落的 Scatter。Free 不生成 Super Scatter。

转化不会修改盘面 Symbol ID。消除掉落时同步更新 `super_scatter_positions` 中的位置，最终通过 `spin_info.super_scatter_positions` 返回给调用方。

以下初始特殊图标及掉落替换权重，TYPE 0 来自 `[Game Info]`，其他 TYPE 来自对应数字节；本次仅调整 TYPE 0，其他 TYPE 保留原值：

| 字段 | TYPE 0 | TYPE 4、8、12、17 | 含义 |
| --- | --- | --- | --- |
| `ScatterCountProbability` | 10000,1000,500,107 | 10000,1000,500,57 | Base 下标 0–3 对应生成 0–3 个 Scatter |
| `FreeScatterCountProbability` | 10000,1000,500,57 | 10000,1000,500,57 | Free 下标 0–3 对应生成 0–3 个 Scatter |
| `BaseNoWinBonusCountProbability` | 98,2 | 98,2 | Base Scatter 不超过 2 个且无奖时生成 0/1 个 Bonus |
| `BaseWinBonusCountProbability` | 964,36 | 92,8 | Base Scatter 不超过 2 个且有奖时生成 0/1 个 Bonus |
| `FreeGoldenBonusCountProbability` | 60,40 | 60,40 | Free 实际放入不超过 2 个 Scatter 且仍有候选、开始时已有金框，生成 0/1 个 Bonus |
| `FreeNoGoldenBonusCountProbability` | 30,70 | 30,70 | Free 实际放入不超过 2 个 Scatter 且仍有候选、开始时没有金框，生成 0/1 个 Bonus |
| `DropSpecialSymbolProbability` | 998,1,1 | 998,1,1 | Base 每个合格新格的“不替换/Scatter/Bonus”权重 |
| `FreeDropSpecialSymbolProbability` | 998,1,1 | 998,1,1 | Free 每个合格新格的“不替换/Scatter/Bonus”权重 |

`ThemeMath.place_special_symbols()` 先计算当前中奖位置与同 ID 扩展消除位置，再从排除这两类位置的 ID 3–12 普通图标中随机选择并替换。Wild、Scatter、Bonus 均不作为候选，因此不会破坏已有 Cluster 或规避扩展消除。

Base 和 Free 初始盘面均先抽取 Scatter 数量，将数量限制为可用候选数量后放置；只有实际放入不超过 2 个 Scatter 且仍有剩余候选时，才读取对应的 Bonus 权重。实际放入 3 个或候选用完时跳过 Bonus 抽样。最后一次 Free Spin 初盘也执行正常概率流程，不强制生成 Bonus。

Base 和 Free 每轮掉落最多放置 1 个特殊图标，并在放置前检查：

- 盘面存在 Bonus 时，本轮不读取对应模式的掉落权重。
- Scatter 与 Super Scatter 总数达到 3 个时，本轮不读取对应模式的掉落权重。
- 其余情况仅对符合条件的新补入普通图标逐格抽取，按列、列内下标顺序扫描；首次抽中 Scatter 或 Bonus 后直接替换当前格并停止。
- 候选位置仅限本轮新补入、ID 3–12、且不属于补牌后新盘面中奖或扩展消除位置的普通图标。Wild 不作为候选，无候选时不读取掉落权重。

## 2. 普通轴与免费轴

普通游戏使用：

- `reel_config/yngg_rand_main.conf`
- `reel_config/yngg_rand_ex_<TYPE>.conf`，当前 TYPE 为 0、4、8、12、17。

免费游戏使用：

- `free_reel_config/yngg_free_rand_main.conf`
- `free_reel_config/yngg_free_rand_ex_<TYPE>.conf`，当前 TYPE 同上。

轴参数与功能对应关系：

- 使用 `BASE_RATE` 决定正常盘、特殊盘、固定盘、零概率盘的选择权重。
- 使用 `NORMAL_ROLL_1` 至 `NORMAL_ROLL_6` 生成正常盘面。
- 使用 `SP_ROLL_1` 至 `SP_ROLL_6` 生成特殊盘面。
- 使用 `FIX_NUM=10` 和 `FIX_RESULT_1` 至 `FIX_RESULT_10` 提供 10 个无奖盘面。
- 使用 `ZERO_NUM=10` 和 `ZERO_RESULT_1` 至 `ZERO_RESULT_10` 提供 10 个可触发 Bonus 的盘面；零盘并不表示零奖励。
- 结果数组从最左列起，列内由下到上填写，每条包含 6 × 5 = 30 个图标。当前 ZERO 结果的前五列底部组成 5 连 Cluster，并保留一个 Bonus ID 2。
- `FIX_NUM`、`ZERO_NUM` 决定只从对应前 n 条结果中等概率抽取；`FIX_DISORDER`、`ZERO_DISORDER` 为 `1` 时随机打乱每列内部顺序。当前两个乱序开关均为 `0`。
- 固定结果发生消除后，从该 GENERAL 的 `NORMAL_ROLL` 各列随机入口沿轴正方向连续补牌。

`ThemeMath.ng_spin()` 使用普通轴，`ThemeMath.fg_spin()` 使用免费轴。

本次 TYPE 0 普通轴与免费轴配置版本均为 `VERSION=102`，两者 `BASE_RATE=100,0,0,0`；通过各自正常轴生成盘面，其他 TYPE 的轴文件保持原值。

正常轴、特殊轴均限制为每条最多 200 个物件、轴值的 UTF-8 编码长度小于 400 字节（不含字段名与 `=`）。生成脚本按原始图标占比分配保留数量，在同类图标的出现位置中均匀删减，保留相对顺序和每种已有图标；超限时继续减少长度。当前所有 TYPE 的轴值最长为 399 字节。缩短轴带会改变停轴和相邻图标分布，需重新仿真确认 RTP 与触发率。

## 3. 消除与补牌

`ng_spin()` 和 `fg_spin()` 的主要参数：

- 使用 `index` 选择 TYPE 0、4、8、12 或 17；同一次玩法的 Base 和 Free 应使用相同的 `index`。仿真读取对应的服务器参数段、普通轴和免费轴；TYPE 0 参数段为 `[Game Info]`，其余为对应数字节。缺少参数段或轴文件时报错，不回退到 TYPE 0。
- 使用 `general_index` 选择配置中的 `GENERAL_<index>`。
- 使用 `max_cascades` 限制单次 Spin 的最大连续消除次数。
- 使用 `return_detail` 决定是否返回每轮消除明细。

每次中奖后：

- 删除实际中奖位置，以及全盘与中奖普通图标同 ID 的扩展消除位置。未中奖 Wild 不扩展消除；扩展位置不增加赔付和金框。
- 幸存图标保持原相对顺序，放在列数组低下标；新图标从同轴当前窗口后方沿正方向取出，放在高下标，结果为 `Survivors + NewItems`。
- 使用新增 `NextReelIndexes` 保存每列下一次正向取牌游标；正常盘、特殊轴盘的初始游标为窗口起点加行数后对轴长取模，FIX、ZERO 使用正常轴随机入口。显式注入初始盘只替换盘面，延续原停轴状态的轴与游标。每补入一个图标，游标沿正方向推进一个位置。
- 原有状态字段 `top_indexes` 保留初始停轴语义、不再随补牌推进。结果字段 `final_top_indexes` 与明细字段 `refill_items.top_index_before`、`refill_items.top_index_after` 保留旧名称，但值改为正向 `NextReelIndexes` 的最终游标及每次补牌前后游标。Scatter 和 Super Scatter 位置随幸存图标同步移动。
- 明细 `remove_positions` 返回中奖与扩展位置的并集，新增 `ExtendedRemovePositions` 仅返回扩展消除位置，便于核对额外消除未增加赔付和金框。
- 使用补牌后的盘面继续判断下一轮 Cluster。
- 直到盘面不再中奖或达到 `max_cascades`。

## 4. 免费游戏状态

`[Game Info]` 中的 `FreeSpinCounts=10,10` 按普通免费、超级免费顺序读取，两项必须为正整数。`FreeSpinRetrigger=0,0,2,4` 按 Scatter 总数 0–3 索引，四项必须为非负整数；3 个及以上使用最后一项。两组字段在创建 `ThemeMath` 时加载，修改配置后需重新创建实例。

`fg_spin()` 的免费玩法参数：

- Base 触发 Free 后，第一次调用 `fg_spin()` 时使用空的 `golden_squares`，不传入 Scatter 位置或 Base 消除位置。
- 使用 `free_mode="free"` 执行普通免费游戏。
- 使用 `free_mode="super_free"` 执行超级免费游戏。
- 使用 `golden_squares` 传入上一轮保留的金色格位置。
- 使用返回值 `golden_squares` 作为下一次普通免费或超级免费 Spin 的状态。
- 使用 `retrigger_spins` 返回本次追加的免费次数。
- 使用 `remaining_spins` 传入包含当前 Spin 在内的剩余免费次数。
- 使用 `bonus_seen` 表示本轮 Free 之前是否已经出现过 Bonus。
- 使用返回值 `free_bonus_seen` 传递更新后的 Bonus 出现状态。

普通免费触发 Bonus 后清空金色格；超级免费保留金色格到玩法结束。

当 `remaining_spins=1` 且 `bonus_seen=False` 时，初盘仍正常抽取 Scatter 和 Bonus，不强制生成 Bonus。只有本次正常生成流程结束后仍没有 Bonus，且全部消除已经结束、终盘不再中奖时，才从终盘可替换的 ID 3–12 普通图标中随机选择一个位置补入 Bonus。没有候选时不放置。

## 5. Bonus 类型选择

`special/yngg_bonus.conf` 只读取 `[GENERAL]`。所有 GROUP/TYPE 的主游戏、免费游戏及重翻共用其中的结果类型、金币、四叶草和 JP 参数，不读取数字节覆盖，也不再制作 TYPE 专属 Bonus 版本。切换 TYPE 不重新选择 Bonus 权重。

本次保留 `[GENERAL]` 原有数值，不将原 TYPE 0 的独立低权重移入公共段。共享范围仅为金色玩法内部的结果类型和奖励档位；普通轴、免费轴、初始特殊图标及掉落替换概率仍按各自 TYPE 配置。

每个金色位置分两步抽取：

1. 使用 `BONUS_SYMBOL_TYPE_PROBABILITY` 抽取类型。
2. 根据类型读取对应的档位和档位权重。

类型下标固定为 `coin`、`clover`、`pot`、`jackpot`。`BONUS_SYMBOL_TYPE` 为兼容保留的可选文本，不参与类型选择；缺失、注释或改变其内容均不改变以下权重下标映射：

| 类型 | 所有 GROUP/TYPE 共用的 `[GENERAL]` 权重 |
| --- | ---: |
| `coin` | 1000 |
| `clover` | 80 |
| `pot` | 6 |
| `jackpot` | 2 |

权重为相对权重，不要求合计为 10000。

## 6. 金币档位

金币使用两个按下标对应的数组：

- `BONUS_COIN_MULTIPLE` 提供金币倍数档位。
- `BONUS_COIN_MULTIPLE_PROBABILITY` 提供每个档位的抽取权重。

先按权重抽取下标，再从同一下标读取金币倍数。各 TYPE 均保留 0.2、0.5、1、2、3、4、5、10、15、20、25、50、100、250、500 共 15 档。

- 所有 GROUP/TYPE 共用 `[GENERAL]` 金币权重 `1560,1240,1030,860,720,545,415,320,228,165,110,62,31,10,3`，总权重 7299，抽中金币后的条件平均倍数约 4.516646x。
- 所有金币档位保留正权重，金币倍数值与金额单位保持不变。

## 7. 四叶草档位

四叶草使用两个按下标对应的数组：

- `BONUS_CLOVER_MULTIPLE` 提供四叶草倍数档位。
- `BONUS_CLOVER_MULTIPLE_PROBABILITY` 提供每个档位的抽取权重。

先按权重抽取下标，再从同一下标读取四叶草倍数。所有 GROUP/TYPE 共用 `[GENERAL]` 权重 `40,28,16,10,5,1`。

## 8. JP 档位

JP 使用两个按下标对应的数组：

- `BONUS_JP_MULTIPLE` 按 MINI、MINOR、MAJOR、GRAND 顺序提供固定倍数。
- `BONUS_JP_TYPE_PROBABILITY` 提供四个 JP 档位的抽取权重。

先按权重抽取 JP 下标，再从同一下标读取 JP 倍数。所有 GROUP/TYPE 共用 `[GENERAL]` 四档权重 `80,25,8,1`，四档均保留正权重。

## 9. 聚宝盆重翻

`resolve_golden_feature()` 对本轮新增聚宝盆按 `(Col 升序, Row 降序)` 逐个结算：先列 0 的 Row 4 至 0，再列 1 的 Row 4 至 0，依次到列 5，与服务器 `g_iPotScan=4,3,2,1,0,9,8,7,6,5,...` 一致。后结算的盆会收集先结算盆的金额。

此排序只控制聚宝盆收集。翻牌、四叶草及输出 `cells` 的顺序仍为 `(Row, Col)` 升序；类型及档位继续按现有权重抽取。

当某个位置抽到 `pot`：

- 当前聚宝盆位置保留。
- 其余非聚宝盆位置重新执行“先抽类型，再抽具体档位”。
- 新一轮仍可产生金币、四叶草、聚宝盆或 JP。
- 持续重翻，直到没有产生新的聚宝盆。

## 10. 外部结果与调试参数

`ng_spin()`、`fg_spin()` 支持通过 `feature_outcome` 提供指定结果：

- 使用 `initial_board` 指定初始盘面。
- 使用 `scatter_count`、`super_scatter_count`、`bonus_count` 指定功能图标数量。
- 使用 `super_scatter_positions` 指定共用 Scatter ID 0 的 Super Scatter 位置；数量需与 `super_scatter_count` 一致。
- 使用 `golden_rounds` 指定各轮金色位置结果。
- 使用 `feature_win` 或 `feature_win_multiple` 指定额外 Bonus 奖励。

传入完整 Bonus 结果时使用外部结果；没有传入结果且满足 Bonus 触发条件时，使用 `yngg_bonus.conf` 的权重生成结果。

## 11. 配置生成

运行以下命令可依据参考数据初始化缺失资源，并维护已有 yngg 配置：

```powershell
python -B ThemeMath\yngg\build_from_demo.py --demo-dir <参考数据目录>
```

生成内容包括游戏配置、Bonus 配置、普通轴、免费轴以及 FIX/ZERO 固定结果。Bonus 统一使用 `[GENERAL]`，不生成 TYPE 专属版本，并保留现有公共权重。TYPE 0 已有普通轴和免费轴文件保留当前校准内容，TYPE 4、8、12、17 的已有轴文件也保留；仅对超限轴值执行长度压缩，不用参考轴覆盖已有校准盘面或固定结果。缺少 TYPE 0 轴文件时，脚本才依据参考轴创建；其他 TYPE 轴文件缺失时，以 TYPE 0 内容创建待校准模板，不能将模板视为独立数值成果。

`source_math.json` 的 TYPE 0 特殊图标概率和共享 Bonus 权重从保留后的实际配置读取：特殊图标与 Scatter 转化参数读取服务器配置的 `[Game Info]`；Bonus 只读取 `[GENERAL]`，类型顺序固定为 coin、clover、pot、jackpot，确保元数据反映当前生效值。文件中的四项 RTP 仍为上述校准目标，不代表实测结果。

生成脚本同时维护控制组配置、TYPE 0 的 `[Game Info]` 参数、其他 TYPE 数字段和回放金币门槛。当前控制组为 GROUP 0、4、8、12、17，控制值分别为 `1`、`401`、`801`、`1201`、`1701`，按 `control_type * 100 + control_num` 编码。两组砍分数组按 GROUP 0–17 排列，GROUP 0/4/8/12/17 的阈值分别为 5000/12000/1000/20/1000；没有配置的 GROUP 下标为 `0`。GROUP 13、14 仍缺少对应控制组，本次未补齐。

`special/yngg_control.conf` 中原为 `80000` 的控制押注已调整为当前最低有效押注 `100000`。此前仅校准 TYPE 0 的普通轴、免费轴和特殊图标参数；TYPE 4、8、12、17 的轴与特殊图标参数保留原值。当前各 GROUP/TYPE 的 Bonus 奖励统一使用 `[GENERAL]`，各 TYPE RTP 需重新仿真确认。Python 仿真尚不执行 GROUP 选择和服务器砍分。GROUP 17 的免费道具卡还缺少各道具的押注索引与品质，按本次要求暂不修改 `special/slot_prop_config.conf`。`replay_min_win_money` 按金币单位设置为 `3000000000`，回放开关仍由全局配置控制。

## 12. TYPE 0 RTP 历史校准记录（2026-10-15，服务器逻辑对齐前）

本节保留此前校准使用的旧逻辑与旧 TYPE 0 Bonus `[0]` 覆盖权重记录。此后已按新版服务器修改参数段读取、固定 Bonus 类型顺序以及 Free 初盘和终盘保底流程，并取消所有数字节 Bonus 覆盖、统一使用原 `[GENERAL]`。以下数值不代表修改后逻辑或共享权重的验证结果，当前版本需重新仿真。

当时仅调整 GROUP 0 对应的 TYPE 0；GENERAL 1，正常盘权重 `100,0,0,0`。从当时已保存的实际配置启动四个独立仿真，每个随机种子运行25万次付费 Base，共100万次；每次包含其触发的全部 Free 和重触发结算。四项 RTP 均以付费 Base 的累计下注为分母。

| 分项 | 大致目标 | 旧逻辑百万局实测 |
| --- | ---: | ---: |
| Base 消除 | 55.00% | 55.20% |
| Base Bonus | 10.00% | 10.10% |
| Free 消除 | 13.00% | 12.93% |
| Free Bonus | 20.00% | 20.75% |
| 合计 | 98.00% | 98.98% |

旧样本中 Free 合计为 33.69%，接近33%的目标。Free 触发率为 0.9302%，Base Bonus 触发率为 2.2838%。样本中包含 GRAND 等低概率大奖，实测结果会随种子波动；当时保留了所有奖励档位及其正权重。

当时校准通过 TYPE 0 主盘及免费轴调整消除占比，通过服务器配置 `[0]` 的 Scatter / Base 有奖 Bonus 生成权重调整触发，并以当时的 Bonus `[0]` 类型、金币档位权重控制奖励期望。当前 TYPE 0 特殊图标参数已改为读取 `[Game Info]`，Bonus `[0]` 覆盖已取消；所有 GROUP/TYPE 共用原 `[GENERAL]`。其他 TYPE 的轴、特殊图标参数及公共赔率均保留。

随机种子为20261015、20261016、20261017、20261018，当时使用 `simulation.simulation(spin_times=250000, index=0, general_index=1, report_interval=0, seed=Seed)` 逐组运行；复现旧结果需使用记录对应的代码和配置版本。分组明细、标准误、35份配置指纹及运行代码指纹见 [`rtp_calibration.json`](rtp_calibration.json)，原始证据未改写。当时56项测试通过，31份非目标配置文件完整哈希不变，TYPE 往返切换验证无权重串用。

上述数据为旧逻辑的 Python 自然概率仿真，未执行服务器 GROUP 选择及砍分。新版服务器已修复档位权重抽取和金币字段、单位问题；当前本地与服务器均只读取共享 Bonus `[GENERAL]`，无需按 TYPE 合并 Bonus 权重。
