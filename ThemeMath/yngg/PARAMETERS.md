# yngg 参数与功能实现说明

本文只描述配置参数、脚本参数与功能实现之间的对应关系。玩法规则见 `LOGIC.md`。

TYPE 0 Base 自身 Hit 目标为 30%，全部连消 RTP 目标为 40%；Base Bonus 以付费 Base 局数为分母，目标触发率约为 1.25%。初始有奖盘读取 `BaseWinBonusCountProbability` 决定是否放置 Bonus；初始无奖盘读取 `BaseNoWinBonusCountProbability`，可展示 Bonus，但本次 Base 没有实际消除时不触发金色玩法。

TYPE 0 的 Base Bonus RTP 目标为付费 Base 累计下注的 20%。金币中档奖励承担更大的常见概率，四叶草和聚宝盆的类型比例降低；500x 金币、20 倍四叶草及 GRAND 5000x 仍有正概率。波动同时按整轮 Bonus 奖励的绝对标准差与变异系数（标准差 / 均值）核对，不能只用均值增长说明波动降低。当前奖励权重由 Base、普通 Free、Super Free 共用，因此免费 Bonus 和总 RTP 也随之变化；当前实测见 `bonus_type_calibration.json`，不沿用历史免费分项及总 95% 结论。

金色玩法限制由所有 TYPE 共用：一整轮累计最多 5 个聚宝盆、3 个四叶草；首次翻牌及每次重翻的新图标至少有 1 枚普通金币。保留聚宝盆不计入金币保底。普通和超级免费初始次数均为 10 次。Python 仿真不启用服务器 GROUP 选择和砍分。

2026-10-22 的 TYPE 0 历史目标总 RTP 为 95%：Base Cluster / Bonus 为 45% / 20%；普通 Free Cluster / Bonus 约 7.3% / 18%；Super Free Cluster / Bonus 约 0.7% / 4%。Base Bonus、普通 Free、Super Free 的历史目标触发率分别为 1.25%、0.5%、0.05%。六项 RTP 均以付费 Base 累计下注为分母。`rtp_calibration.json`、`rtp_calibration_runs.json` 和 10 月 22 日性能数据均对应 2026-10-23 共享翻牌限制实施前的版本，不能作为当前规则已达到上述目标或性能水平的依据。实参以当前配置为准。

| 分项 | 2026-10-22 历史 RTP 目标 |
| --- | ---: |
| Base Cluster | 45% |
| Base Bonus | 20% |
| 普通 Free Cluster | 约 7.3% |
| 普通 Free Bonus | 18% |
| Super Free Cluster | 约 0.7% |
| Super Free Bonus | 4% |
| 合计 | 95% |

普通 Free 两项合计约 25.3%，Super Free 两项合计约 4.7%，对应约 25% / 5% 的分配。触发率分别指每次付费 Base 出现 Base Bonus、普通 Free 或 Super Free 的概率；普通与超级免费触发率合计约 0.55%。

### 2026-10-22 扩大分组后的历史校准结果（新规则之前）

以下结果使用没有四叶草整轮上限、没有逐批 coin 保底的旧规则，仅作历史参考。当前 Base Bonus 奖励校准及免费分项变化另见 `bonus_type_calibration.json`，不能混用两套参数和样本。

该次校准中，TYPE 0 将最低金币概率分散到0.2/0.5/1，将最高金币概率分散到100/250/500；四叶草低倍组扩大为2/3/4/5，高倍组为10/20，各组内等概率。金币中间档保留正权重，全部奖励档位保留。这里使用分组离散分布，不假设连续平滑的概率密度。

| 内容 | 档位 | 每档概率 |
| --- | --- | ---: |
| 金币低倍组 | 0.2、0.5、1 | 33.3137% |
| 金币高倍组 | 100、250、500 | 0.0185% |
| 四叶草低倍组 | 2、3、4、5 | 23% |
| 四叶草高倍组 | 10、20 | 4% |

扩组提高了金币和四叶草的一阶矩，因此同步将类型权重调整为5000/58/6/2，ZERO初始中奖区域由22格改为17格；主盘混合权重为7945/0/1930/125。TYPE 0 Scatter权重尾项改为77、Super转化概率880/10000，已有金框/无金框时的Free Bonus数量权重分别改为57/43与97/3。Base Bonus入口仍为1.25%，免费次数仍为10/10，抽取与结算算法不变。

当时配置按4个种子累计运行1亿局付费Base；另按4个种子、5000万局作条件期望校验。条件模式将独立金币、四叶草和JP档位按权重取期望，仍随机抽取盘面、类型、位置、聚宝盆及重翻路径，用于降低奖励长尾对RTP估计的噪声。两批使用相同种子，属于相关的两种估计器，不能作为相互独立的重复实验。全部RTP按Base总下注归一化：

| 分项 | 目标 | 完整随机实测（1亿局） | 条件期望校验（5000万局） |
| --- | ---: | ---: | ---: |
| Base Cluster | 0.4500 | 0.449940 | 0.449972 |
| Base Bonus | 0.2000 | 0.200001 | 0.199825 |
| 普通 Free Cluster | 0.0730 | 0.072924 | 0.073042 |
| 普通 Free Bonus | 0.1800 | 0.180272 | 0.180029 |
| Super Free Cluster | 0.0070 | 0.007241 | 0.007276 |
| Super Free Bonus | 0.0400 | 0.040121 | 0.040476 |
| 合计 | 0.9500 | 0.950498 | 0.950620 |

完整随机模拟的Base Bonus / 普通Free / Super Free触发率分别为 **1.2495230% / 0.4962150% / 0.0493360%**，接近1.25% / 0.5% / 0.05%目标。普通与超级免费初始次数保持 **10 / 10**。

完整随机总RTP标准误为0.001340，近似95%区间为0.947871–0.953125；条件期望估计标准误为0.000750，区间为0.949151–0.952089。这是对应估计器的采样误差，不代表单个玩家波动，也不是精确理论RTP。

Base Bonus完整随机样本共1,249,523次触发，条件均值约16.0062x、标准差约80.5822x、变异系数约5.03；样本最高单次Bonus为30,118.6x，并非理论封顶。分散两端概率后，波动较更早方案（标准差约197.13x）有所收敛，该版本仍为高波动。500x金币、20x四叶草、5000x Grand及5盆尾部保留。各批分位数单独记录，不把批次分位数平均为总样本分位数。

本地原生采样器以20,000局、306,419次随机调用逐项回放到实际ThemeMath，六项奖金、总奖、免费模式及Base Bonus标记全部一致；71项单元测试通过。相对更早的端点集中方案，该次仅修改3份配置，其他32份配置及6份运行/校准源文件不变。其他TYPE的轴、参数段及Bonus GENERAL保留原值。

历史数据、标准误、区间、当时参数及文件指纹见 `rtp_calibration.json`；8个批次完整记录见 `rtp_calibration_runs.json`。这些指纹记录的是采样时版本；当前新增的规则字段与运行逻辑不属于该次校准。更早结果归档在 `calibration_history/20261022_endpoint_weights/`。`simulate_result.csv` 中 `CalibrationRevision=NaturalGroupsExpanded` 的两条聚合记录同为旧规则历史数据；未采集的金额和命中字段留空。

以下为历史校准命令记录；复现旧结果需使用当时的源码和配置。当前采样及文件指纹以 `bonus_type_calibration.json` 为准：

```sh
python3 calibrate_rtp.py --spins 25000000 --runs 4 --workers 4 --seed 2026102251 --output /tmp/yngg-natural-full.json
python3 calibrate_rtp.py --spins 12500000 --runs 4 --workers 4 --seed 2026102251 --expected-rewards --output /tmp/yngg-natural-expectation.json
python3 verify_calibration_sampler.py --spins 20000 --seed 2026102250
```

上述历史验证针对当时的本地规则，未执行 Linux 服务器二进制，也不代表当前新规则的验证结果。此前提供的server尚不读取新增 `[Type0]` 权重，服务器衔接项见 `yngg_服务器逻辑修改说明.md`。

## 当前 TYPE 0 Base Bonus 入口

主轴为 `BASE_RATE=8580,1420,0,0`，即 NORMAL 85.8%、SP 14.2%；FIX、ZERO 当前不参与抽取。普通轴与特殊轴使用相同的初始特殊图标流程。

| 字段 | 当前权重 | 条件分支及单位 |
| --- | --- | --- |
| `BaseWinBonusCountProbability` | `9581,419` | 初盘已有中奖、实际放入 0–2 个 Scatter 且仍有候选时，0 / 1 个 Bonus 的相对权重；条件放置概率 4.19% |
| `BaseNoWinBonusCountProbability` | `98,2` | 初盘无中奖、实际放入 0–2 个 Scatter 且仍有候选时，0 / 1 个 Bonus 的相对权重；条件展示概率 2% |
| `DropSpecialSymbolProbability` | `999,1,0` | Base 补牌的不替换 / Scatter / Bonus 权重；不通过掉落新增 Bonus |

4.19% 仅作用于符合放置条件的有奖初盘，不是所有付费 Base 的触发率。实际触发率以 `BaseBonusTriggerCount / PaidBaseSpinCount` 统计，目标约 1.25%；它由有奖合格初盘占比与上述条件概率共同决定，应以完整 Spin 采样核对。奖励权重调整前的入口校准使用相同入口参数，2,000 万局完整流程样本实测为 1.24634%，满足放置条件的有奖初盘占比为 29.84024%；该占比乘 4.19% 为 1.250306056%。无消除局内展示率，即无奖 Bonus 展示次数 / 全部无消除 Base 次数，实测为 1.9888%；该分母包含因 3 个 Scatter 或无剩余候选而跳过 Bonus 抽样的局，因此低于合格无奖分支的配置概率 2%。样本中未发生无消除 Base 触发。采样范围及误差见 `yngg_服务器逻辑修改说明.md`。

每次 Base 的金色区域从空集合开始。只有本次实际中奖消除产生了金色区域、且全部消除结束后终盘仍有 Bonus，才执行金色玩法。无消除时出现 Bonus 只展示图标，不生成金色玩法奖励，也不继承前一局金色区域。此限制不改变 Free / Super Free 各自的金色区域保留规则。

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

`special/yngg_game_server.conf` 的 `[Game Info]` 保存通用玩法参数及 TYPE 0 的特殊图标生成、Scatter 转化参数。TYPE 0 只读取该节，不读取该文件的 `[0]`；TYPE 4、8、12、17 则读取各自数字节。初始和掉落特殊图标概率按 TYPE 区分；金色玩法奖值档位保留在 Bonus 文件的 `[GENERAL]`，TYPE 0 的四组权重由 `[Type0]` 覆盖，其他 TYPE 保留公共权重。Wild ID 1、主盘 Bonus ID 2、Scatter 与 Super Scatter 共用 ID 0；Super Scatter 通过 `super_scatter_positions` 位置状态区分，不使用专门 ID：

- 使用当前 TYPE 的 `SuperScatterProbability` 设置转化概率，单位为万分比；TYPE 0 的实际值见 `[Game Info]`，不等同于最终 Super Free 触发概率。
- 使用 `coin_multi_1=5`、`coin_multi_2=25` 将金币倍数划分为铜币、银币和金币。
- 使用 `[Game Info]` 的 `BonusMaxPotCount=5`、`BonusMaxCloverCount=3`、`BonusRevealMinCoinCount=1`，分别限制整轮 Pot/Clover 累计数与每批新翻 coin 数；所有 TYPE 共用。旧 `bonus_max_round` 仅在 `BonusMaxPotCount` 缺失时作为 fallback。

Base 初始特殊图标生成后执行一次转化判断；Base 后续掉落生成 Scatter 且盘面没有 Super Scatter 时，也执行一次转化判断，成功后从全盘现存普通 Scatter 中随机选择 1 个，不限于本次掉落的 Scatter。Free 不生成 Super Scatter。

转化不会修改盘面 Symbol ID。消除掉落时同步更新 `super_scatter_positions` 中的位置，最终通过 `spin_info.super_scatter_positions` 返回给调用方。

以下初始特殊图标及掉落替换权重，TYPE 0 来自 `[Game Info]`，其他 TYPE 来自对应数字节；本次仅调整 TYPE 0，其他 TYPE 保留原值：

| 字段 | TYPE 0 参数来源与作用 | TYPE 4、8、12、17 |
| --- | --- | --- |
| `ScatterCountProbability` | `[Game Info]`；下标 0–3 对应 Base 生成 0–3 个 Scatter | 对应数字节原值 |
| `FreeScatterCountProbability` | `[Game Info]`；下标 0–3 对应 Free 生成 0–3 个 Scatter | 对应数字节原值 |
| `BaseNoWinBonusCountProbability` | `[Game Info]`；初始无奖且满足放置条件时生成 0/1 个 Bonus，`98,2` 对应条件展示概率 2% | 对应数字节原值 |
| `BaseWinBonusCountProbability` | `[Game Info]`；初始有奖且满足放置条件时生成 0/1 个 Bonus，校准实际付费 Base 触发率约 1.25% | 对应数字节原值 |
| `FreeGoldenBonusCountProbability` | `[Game Info]`；已有金框时生成 0/1 个 Bonus | 对应数字节原值 |
| `FreeNoGoldenBonusCountProbability` | `[Game Info]`；没有金框时生成 0/1 个 Bonus | 对应数字节原值 |
| `DropSpecialSymbolProbability` | `[Game Info]`；当前 Base 掉落 Bonus 分量禁用，Scatter 分量仍按配置 | 对应数字节原值 |
| `FreeDropSpecialSymbolProbability` | `[Game Info]`；Free 每个合格新格的不替换 / Scatter / Bonus 权重 | 对应数字节原值 |

以上可调权重的最终数字以配置为准。

`ThemeMath.place_special_symbols()` 先计算当前中奖位置与同 ID 扩展消除位置，再从排除这两类位置的 ID 3–12 普通图标中随机选择并替换。Wild、Scatter、Bonus 均不作为候选，因此不会破坏已有 Cluster 或规避扩展消除。

正常盘 / 特殊轴盘的 Base 和 Free 初始盘面均先抽取 Scatter 数量，将数量限制为可用候选数量后放置；只有实际放入不超过 2 个 Scatter 且仍有剩余候选时，才读取对应的 Bonus 权重。实际放入 3 个或候选用完时跳过 Bonus 抽样。最后一次 Free Spin 初盘也执行正常概率流程，不强制生成 Bonus。FIX、ZERO 预设初盘不执行这一步特殊图标替换。

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
- 结果数组从最左列起，列内由下到上填写，每条包含 6 × 5 = 30 个图标。TYPE 0 主游戏 ZERO 预设扩大实际中奖区域以形成较大的金框集合，并保留 Bonus ID 2；具体盘面及金框数量以 `ZERO_RESULT_N` 为准。
- `FIX_NUM`、`ZERO_NUM` 决定只从对应前 n 条结果中等概率抽取；`FIX_DISORDER`、`ZERO_DISORDER` 为 `1` 时随机打乱每列内部顺序。当前两个乱序开关均为 `0`。
- 固定结果发生消除后，从该 GENERAL 的 `NORMAL_ROLL` 各列随机入口沿轴正方向连续补牌。

`ThemeMath.ng_spin()` 使用普通轴，`ThemeMath.fg_spin()` 使用免费轴。

TYPE 0 Base 使用 `BASE_RATE=8580,1420,0,0`，按 85.8% / 14.2% 选择 `NORMAL_ROLL` / `SP_ROLL`，选定的轴贯穿本次全部消除补牌。FIX、ZERO 的抽取权重均为 0，预设内容保留。Base Bonus 入口由初始特殊图标权重控制：有奖盘通过 `BaseWinBonusCountProbability` 校准实际触发率；无奖盘通过 `BaseNoWinBonusCountProbability` 展示 Bonus。

TYPE 0 的 NORMAL 两项指标低于 Base Hit 30% / 消除 RTP 40% 的基准，SP 两项高于基准，再按上述权重混合。Base 消除 RTP 包含全部连消，按付费 Base 总下注归一化；Base 自身 Hit 不包含随后免费游戏的收益。现有报表 `Hit率` 包含触发后的整段免费收益。免费轴内容以 `free_reel_config/yngg_free_rand_ex_0.conf` 为准。

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

## 当前 TYPE 0 Bonus 奖励权重

`[Type0]` 的有效权重由 Base、普通 Free、Super Free 及其重翻共用；其他 TYPE 保留 `[GENERAL]`。奖励档位金额、Base Bonus 入口权重、轴带、免费次数、聚宝盆/四叶草累计上限及每批新金币保底不变。

| 类型 | 权重 |
| --- | ---: |
| 金币 | 10081 |
| 四叶草 | 40 |
| 聚宝盆 | 6 |
| JP | 5 |

类型总权重为 10132。以上是未受累计上限及强制金币干预时的名义类型比例；达到上限后按剩余允许类型重新归一化，强制金币分支跳过类型抽样。

| 金币倍数 | 权重 | 抽中金币后的档位概率 |
| --- | ---: | ---: |
| 0.2 / 0.5 / 1 | 各 162000 | 各 16.2% |
| 2 | 253845 | 25.3845% |
| 3 | 145000 | 14.5% |
| 4 | 70000 | 7% |
| 5 | 30000 | 3% |
| 10 | 10000 | 1% |
| 15 | 3000 | 0.3% |
| 20 | 1000 | 0.1% |
| 25 | 400 | 0.04% |
| 50 | 200 | 0.02% |
| 100 / 250 / 500 | 各 185 | 各 0.0185% |

金币总权重为 1000000，条件均值为 1.99034x。金币高组三档的条件概率保持，四叶草档位仍为 `23,23,23,23,4,4`，JP 档位仍为 `80,25,8,1`。JP 名义类型概率为 `5/10132`，相对于奖励调整前 `2/5066` 提高 25%。保留这些概率不等于整轮 ≥1000x 或 ≥5000x 的概率完全相同；整轮大奖须与实际金格数、重翻和放大路径共同统计。

Base Bonus RTP 目标为 20%，分母为付费 Base 累计下注。1 亿局完整随机样本实测 Base Bonus RTP 为 20.0337%（标准误 0.04527 个百分点），触发率 1.251033%；独立 5,000 万局条件期望校验为 20.0738%。三模式共用奖励参数后，普通 Free Bonus / Super Free Bonus / 总 RTP 分别为 53.3718% / 11.5945% / 134.8976%，不沿用历史免费分项及总 95% 结论。

标准差按一次触发后的整轮 Bonus 倍率计算，变异系数为标准差除以条件均值。在相同经验金格分布下，两组各 2,000 万次 Feature 抽样的绝对标准差由 42.6206x 降至 39.7261x，变异系数由 6.6251 降至 2.4800；≥5000x 频率分别为 0.00351% / 0.003345%，差异处于采样误差范围。详细样本口径、误差及尾部对照见 `bonus_type_calibration.json` 和 `yngg_服务器逻辑修改说明.md`；10 月 22 日旧样本与奖励调整前约 7.93% 的 Base Bonus 样本均保留为历史基准。

## 5. Bonus 类型选择

`special/yngg_bonus.conf` 的 `[GENERAL]` 保留共用奖值档位和默认权重。TYPE 0 按 `[GENERAL]` → `[Type0]` 读取，`[Type0]` 只允许以下四个 PascalCase 权重字段；缺失项继承 `[GENERAL]`：

| TYPE 0 覆盖字段 | 对应 `[GENERAL]` 字段 | 作用 |
| --- | --- | --- |
| `BonusSymbolTypeProbability` | `BONUS_SYMBOL_TYPE_PROBABILITY` | coin / clover / pot / jackpot 类型权重 |
| `BonusCoinMultipleProbability` | `BONUS_COIN_MULTIPLE_PROBABILITY` | 金币档位权重 |
| `BonusCloverMultipleProbability` | `BONUS_CLOVER_MULTIPLE_PROBABILITY` | 四叶草档位权重 |
| `BonusJpTypeProbability` | `BONUS_JP_TYPE_PROBABILITY` | MINI / MINOR / MAJOR / GRAND 权重 |

TYPE 4、8、12、17 继续读取 `[GENERAL]` 原权重，不使用 `[Type0]`；数字节 `[0]` 等旧覆盖不生效。每次切换 TYPE 使用其对应的有效权重，Base、普通 Free、Super Free 和重翻使用同一 TYPE 的权重。奖值数组、图标映射及四叶草/聚宝盆结算顺序保持不变。新翻格先应用共享上限与 coin 保底；非强制 coin 时仍先抽允许的类型，再抽对应档位。

每个新翻位置先应用共享 Pot/Clover 上限与本批 coin 保底。非强制 coin 时，使用当前 TYPE 的有效类型权重抽取允许的类型，再读取对应档位权重；TYPE 0 的类型覆盖字段为 `BonusSymbolTypeProbability`。强制 coin 时跳过类型随机抽取，只按有效金币档位权重抽取奖值。

类型下标固定为 `coin`、`clover`、`pot`、`jackpot`。`BONUS_SYMBOL_TYPE` 为兼容保留的可选文本，不参与类型选择；缺失、注释或改变其内容均不改变以下权重下标映射：

| 类型 | TYPE 4、8、12、17 保留的 `[GENERAL]` 默认权重 |
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

- TYPE 4、8、12、17 保留 `[GENERAL]` 金币权重 `1560,1240,1030,860,720,545,415,320,228,165,110,62,31,10,3`；其总权重 7299、金币条件均值约 4.516646x。TYPE 0 的有效权重见 `[Type0].BonusCoinMultipleProbability`，不能沿用该公共均值。
- 所有金币档位保留正权重，金币倍数值与金额单位保持不变。

## 7. 四叶草档位

四叶草使用两个按下标对应的数组：

- `BONUS_CLOVER_MULTIPLE` 提供四叶草倍数档位。
- `BONUS_CLOVER_MULTIPLE_PROBABILITY` 提供每个档位的抽取权重。

先按权重抽取下标，再从同一下标读取四叶草倍数。TYPE 4、8、12、17 保留 `[GENERAL]` 权重 `40,28,16,10,5,1`；TYPE 0 有效权重见 `[Type0].BonusCloverMultipleProbability`。20 倍档位保留。

## 8. JP 档位

JP 使用两个按下标对应的数组：

- `BONUS_JP_MULTIPLE` 按 MINI、MINOR、MAJOR、GRAND 顺序提供固定倍数。
- `BONUS_JP_TYPE_PROBABILITY` 提供四个 JP 档位的抽取权重。

先按权重抽取 JP 下标，再从同一下标读取 JP 倍数。TYPE 4、8、12、17 保留 `[GENERAL]` 四档权重 `80,25,8,1`；TYPE 0 有效权重见 `[Type0].BonusJpTypeProbability`。四档仍保留，GRAND 5000x 与最高 500x 金币均保留正概率；是否降低波动以整轮 Bonus 的标准差与变异系数实测为准。

## 9. 聚宝盆重翻

`resolve_golden_feature()` 对本轮新增聚宝盆按 `(Col 升序, Row 降序)` 逐个结算：先列 0 的 Row 4 至 0，再列 1 的 Row 4 至 0，依次到列 5，与服务器 `g_iPotScan=4,3,2,1,0,9,8,7,6,5,...` 一致。后结算的盆会收集先结算盆的金额。

此排序只控制聚宝盆收集。翻牌、四叶草及输出 `cells` 的顺序仍为 `(Row, Col)` 升序；每格先执行以下限制，再使用当前 TYPE 的有效权重抽取。

所有 TYPE 的 Base、普通 Free、Super Free 均共用 `special/yngg_game_server.conf` 的 `[Game Info]` 限制，不从数字 TYPE 节或 Bonus `[Type0]` 读取：

| 字段 | 当前值 | 作用 |
| --- | ---: | --- |
| `BonusMaxPotCount` | 5 | 整轮金色玩法累计可生成的聚宝盆上限 |
| `BonusMaxCloverCount` | 3 | 整轮金色玩法累计可生成的四叶草上限 |
| `BonusRevealMinCoinCount` | 1 | 每批新翻图标必须包含的最少 coin 数 |

`BonusMaxPotCount` 缺失时，读取旧字段 `bonus_max_round`，两者都缺失时默认 5；新字段存在时优先使用新字段。四叶草与 coin 字段缺失时分别默认 3 和 1。三项均为非负整数：Pot/Clover 上限为 0 时禁止生成对应类型，coin 最少数为 0 时关闭该保底；`BonusRevealMinCoinCount` 不得超过盘面总格数，且具体一批待翻位置少于该值时会报错。Pot、Clover 计数跨首次翻牌及全部重翻累计，已结算或被后续翻牌覆盖的四叶草仍计入累计数；保留 Pot 不重复计数，也不计入 coin 保底。计数只覆盖单次金色玩法触发及其全部重翻，结束后重置；Super Free 仅保留金格，下次独立 Bonus 重新计数，不跨整轮 Free session 共用上限。

每批新翻格按 `(Row, Col)` 升序逐格生成。每翻出一格便立即更新累计 Pot、Clover 及本批 coin 数；达到任一累计上限后，在后续格抽类型前将对应类型排除，按剩余允许类型的原相对权重抽取。剩余未翻格数（包含当前格）等于仍需补足的 coin 数时，直接生成 coin，仅按金币档位权重抽取具体奖值，跳过类型随机抽取。配置最少 coin 数大于 0、且合法类型的权重已全部归零时，也直接抽取 coin 档位。其他情况仍先抽允许的类型，再抽该类型的档位。

首次翻牌的本批范围为全部金色位置；聚宝盆结算后重翻的本批范围仅为需要重新生成的非 Pot 位置。保留 Pot 即使已有金额，也不能代替本批新 coin。不能先抽出整批再删除超限结果，也不通过整批重抽实现保底。待翻位置少于配置要求的 coin 数时视为无效。外部 `golden_rounds` 同样逐批校验 coin 最少数及整轮 Pot、Clover 上限；允许已有接口支持的部分位置回放，但每个提供的批次必须满足限制。

当某个位置抽到 `pot`：

- 当前聚宝盆位置保留。
- 其余非聚宝盆位置按上述上限与金币保底规则重新生成；非强制金币时先抽允许类型，再抽具体档位。
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

生成内容包括游戏配置、Bonus 配置、普通轴、免费轴以及 FIX/ZERO 固定结果。已有 Bonus `[GENERAL]` 和命名节 `[Type0]` 均保留，只移除旧数字节；不会把 TYPE 0 调优权重写回公共段。TYPE 0 已有普通轴和免费轴文件保留既有数值内容，TYPE 4、8、12、17 的已有轴文件也保留；仅对超限轴值执行长度压缩，不用参考轴覆盖已有盘面或固定结果。缺少 TYPE 0 轴文件时，脚本才依据参考轴创建；其他 TYPE 轴文件缺失时，以 TYPE 0 内容创建待校准模板，不能将模板视为独立数值成果。

`source_math.json` 的 TYPE 0 特殊图标概率从 `[Game Info]` 读取；Bonus 元数据按 `[GENERAL]` → `[Type0]` 记录 TYPE 0 的有效权重，并以 `GeneralSharedWeights` 单独保留其他 TYPE 的公共原权重。有 `[Type0]` 时 `SharedAcrossTypes=false`、`ConfigSectionOrder=[GENERAL,Type0]`。三项限制从 `[Game Info]` 读取并记录为所有 TYPE 共享；`maximum_pot_count` 保留兼容，新规则字段使用 PascalCase。六项 RTP 与三项触发率保留为 2026-10-22 历史目标，`CalibrationStatus=HistoricalFullTargetsNotRetuned` 表明这些历史全量目标没有按当前参数重新追平，不表示当前参数未经采样；`rtp_calibration.json` 保留旧规则历史记录，`bonus_generation.CurrentCalibrationReport=bonus_type_calibration.json` 指向当前 Base Bonus 奖励及完整流程报告。当前入口另记录 `BaseBonusRequiresBaseCascade=true`、`BaseNoWinBonusIsDisplayOnly=true`、`BaseBonusTriggerDenominator=PaidBaseSpins`，并从实际轴读取 `BaseSourceWeights` 和 `BaseBonusEntrance`。

生成脚本同时维护控制组配置、TYPE 0 的 `[Game Info]` 参数、其他 TYPE 数字段和回放金币门槛。当前控制组为 GROUP 0、4、8、12、17，控制值分别为 `1`、`401`、`801`、`1201`、`1701`，按 `control_type * 100 + control_num` 编码。两组砍分数组按 GROUP 0–17 排列，GROUP 0/4/8/12/17 的阈值分别为 5000/12000/1000/20/1000；没有配置的 GROUP 下标为 `0`。GROUP 13、14 仍缺少对应控制组，本次未补齐。

`special/yngg_control.conf` 中原为 `80000` 的控制押注已调整为当前最低有效押注 `100000`。2026-10-22 仅校准 TYPE 0 的混合盘、免费轴、特殊图标参数和 `[Type0]` Bonus 权重；当前使用所有 TYPE 共用的翻牌限制，TYPE 0 Base 轴和初始 Bonus 权重按当前配置生效。Python 仿真不执行 GROUP 选择和服务器砍分。GROUP 17 的免费道具卡还缺少各道具的押注索引与品质，按本次要求暂不修改 `special/slot_prop_config.conf`。`replay_min_win_money` 按金币单位设置为 `3000000000`，回放开关仍由全局配置控制。

## 12. 历史目标与当前统计口径

当前规则范围以本文开头为准，实参见配置。当前 Base Bonus 奖励校准及三种模式的完整流程结果见 `bonus_type_calibration.json`；它不表示历史免费分项及总 95% 目标仍然成立。`rtp_calibration.json` 中实测、随机种子、样本数、误差与文件指纹仅代表 2026-10-22 旧规则，旧 Bonus `[0]` 覆盖下的记录同样不用于当前验收。

`simulation.py` 保留旧 `free_rtp`、`free_cluster_rtp`、`free_bonus_rtp` 的普通加超级免费合并口径，同时增加以下分模式字段：

- 普通免费：`NormalFreeRtp`、`NormalFreeClusterRtp`、`NormalFreeBonusRtp`、`NormalFreeFrequency`。
- 超级免费：`SuperFreeRtp`、`SuperFreeClusterRtp`、`SuperFreeBonusRtp`、`SuperFreeFrequency`。
- `ModeStats.Free` 和 `ModeStats.SuperFree` 分别记录入口次数、Spin 次数、Cluster / Bonus 奖金与重触发次数。

两种 Free 的 RTP 使用付费 Base 累计下注作分母，两种触发频率使用付费 Base 次数作分母；普通与超级免费分项之和必须等于旧合并指标。所有免费重触发奖励归入进入该玩法时确定的模式。Base Bonus 保留稀有大奖，样本期内的长尾会影响 RTP 与标准差，因此应连同误差、样本数及变异系数核对，不只比较一个点估计。

## 本地 Spin 性能优化

2026-10-22 旧规则版本的同机 5000 局×3批完整 Python Spin 平均由 9.222 秒降至 2.491 秒，约加速 3.70 倍；当时的配置对照、79 项测试及 2 万局全结果/随机流差分均属该次历史验证。本次新增的 Pot/Clover 上限与 coin 保底会改变随机流和执行路径，以上数据不表示当前规则的性能。历史结构调整和复现说明见 `PERFORMANCE.md`，原始计时见 `spin_performance.json`。
