# yngg 参数与功能实现说明

本文只描述配置参数、脚本参数与功能实现之间的对应关系。玩法规则见 `LOGIC.md`。

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

`special/yngg_game_server.conf` 提供特殊图标 ID 和 Scatter 转化参数：

- 使用 `WILD_ID=1` 指定 Wild。
- 使用 `FEATURE_ID`、`BONUS_ID`、`COIN_ID`、`CLOVER_ID`、`POT_ID`、`MULTIPLIER_ID`、`COLLECTOR_ID`、`JACKPOT_ID` 指定金色玩法相关图标。
- 使用 `SUPER_SCATTER_ID=13` 表示完成转化后的 Super Scatter；该动态结果不计入原始图标数量。
- 使用 `SuperScatterSourceId=0` 指定 Super Scatter 的原始图标与 Scatter 相同。
- 使用 `SuperScatterProbability=200` 设置独立转化概率；概率单位为万分比，200/10000 等于 1/50。

初始盘面和每次消除补牌后，所有新出现的 Scatter 都会分别执行一次转化判断。

同一配置文件还提供初始特殊图标及掉落替换权重：

- `ScatterCountProbability=1000,100,50,5`：下标 0–3 分别表示生成 0–3 个 Scatter。
- `BaseNoWinBonusCountProbability=80,20`：Base 无 Scatter、无奖时生成 0/1 个 Bonus 的权重。
- `BaseWinBonusCountProbability=90,10`：Base 无 Scatter、有奖时生成 0/1 个 Bonus 的权重。
- `FreeGoldenBonusCountProbability=60,40`：Free 已有金框时生成 0/1 个 Bonus 的权重。
- `FreeNoGoldenBonusCountProbability=30,70`：Free 没有金框时生成 0/1 个 Bonus 的权重。
- `DropSpecialSymbolProbability=998,1,1`：每个掉落图标对应“不替换/Scatter/Bonus”的权重。

`ThemeMath.place_special_symbols()` 先计算当前中奖位置，再从不参与中奖的候选位置中随机选择并替换，因此不会破坏已有 Cluster。

## 2. 普通轴与免费轴

普通游戏使用：

- `reel_config/yngg_rand_main.conf`
- `reel_config/yngg_rand_ex_0.conf`

免费游戏使用：

- `free_reel_config/yngg_free_rand_main.conf`
- `free_reel_config/yngg_free_rand_ex_0.conf`

轴参数与功能对应关系：

- 使用 `BASE_RATE` 决定正常盘、特殊盘、固定盘、零概率盘的选择权重。
- 使用 `NORMAL_ROLL_1` 至 `NORMAL_ROLL_6` 生成正常盘面。
- 使用 `SP_ROLL_1` 至 `SP_ROLL_6` 生成特殊盘面。
- 使用 `FIX_NUM=10` 和 `FIX_RESULT_1` 至 `FIX_RESULT_10` 提供 10 个完全无奖盘面。
- 使用 `ZERO_NUM=10` 和 `ZERO_RESULT_1` 至 `ZERO_RESULT_10` 提供 10 个必定触发 Bonus 的盘面。
- `FIX_DISORDER`、`ZERO_DISORDER` 作为通用配置兼容字段保留；当前 Python 数学逻辑不对固定结果额外乱序。

`ThemeMath.ng_spin()` 使用普通轴，`ThemeMath.fg_spin()` 使用免费轴。

## 3. 消除与补牌

`ng_spin()` 和 `fg_spin()` 的主要参数：

- 使用 `index` 选择对应的 `rand_ex_<index>.conf`；缺失时回退到 index 0。
- 使用 `general_index` 选择配置中的 `GENERAL_<index>`。
- 使用 `max_cascades` 限制单次 Spin 的最大连续消除次数。
- 使用 `return_detail` 决定是否返回每轮消除明细。

每次中奖后：

- 使用中奖位置删除实际参与赔付的图标。
- 使用本次停轴的 `top_indexes` 从各列上方继续补牌。
- 使用补牌后的盘面继续判断下一轮 Cluster。
- 直到盘面不再中奖或达到 `max_cascades`。

## 4. 免费游戏状态

`fg_spin()` 的免费玩法参数：

- 使用 `free_mode="free"` 执行普通免费游戏。
- 使用 `free_mode="super_free"` 执行超级免费游戏。
- 使用 `golden_squares` 传入上一轮保留的金色格位置。
- 使用返回值 `golden_squares` 作为下一次普通免费或超级免费 Spin 的状态。
- 使用 `retrigger_spins` 返回本次追加的免费次数。
- 使用 `remaining_spins` 传入包含当前 Spin 在内的剩余免费次数。
- 使用 `bonus_seen` 表示本轮 Free 之前是否已经出现过 Bonus。
- 使用返回值 `free_bonus_seen` 传递更新后的 Bonus 出现状态。

普通免费触发 Bonus 后清空金色格；超级免费保留金色格到玩法结束。

当 `remaining_spins=1` 且 `bonus_seen=False` 时，如果盘面仍没有 Bonus，会在最终无奖盘面随机选择一个非中奖位置强制放置 Bonus。

## 5. Bonus 类型选择

`special/yngg_bonus.conf` 的 `[GENERAL]` 段负责 Bonus 结果生成。

每个金色位置分两步抽取：

1. 使用 `BONUS_SYMBOL_TYPE_PROBABILITY` 抽取类型。
2. 根据类型读取对应的档位和档位权重。

类型与 `BONUS_SYMBOL_TYPE` 按相同下标对应：

- `coin` 使用权重 1000。
- `clover` 使用权重 100。
- `pot` 使用权重 10。
- `jackpot` 使用权重 1。

权重为相对权重，不要求合计为 10000。

## 6. 金币档位

金币使用两个按下标对应的数组：

- `BONUS_COIN_MULTIPLE` 提供金币倍数档位。
- `BONUS_COIN_MULTIPLE_PROBABILITY` 提供每个档位的抽取权重。

先按权重抽取下标，再从同一下标读取金币倍数。当前各档位权重均为 1，后续只需调整权重数组。

## 7. 四叶草档位

四叶草使用两个按下标对应的数组：

- `BONUS_CLOVER_MULTIPLE` 提供四叶草倍数档位。
- `BONUS_CLOVER_MULTIPLE_PROBABILITY` 提供每个档位的抽取权重。

先按权重抽取下标，再从同一下标读取四叶草倍数。当前各档位权重均为 1。

## 8. JP 档位

JP 使用两个按下标对应的数组：

- `BONUS_JP_MULTIPLE` 按 MINI、MINOR、MAJOR、GRAND 顺序提供固定倍数。
- `BONUS_JP_TYPE_PROBABILITY` 提供四个 JP 档位的抽取权重。

先按权重抽取 JP 下标，再从同一下标读取 JP 倍数。当前四档权重均为 1。

## 9. 聚宝盆重翻

当某个位置抽到 `pot`：

- 当前聚宝盆位置保留。
- 其余非聚宝盆位置重新执行“先抽类型，再抽具体档位”。
- 新一轮仍可产生金币、四叶草、聚宝盆或 JP。
- 持续重翻，直到没有产生新的聚宝盆。

## 10. 外部结果与调试参数

`ng_spin()`、`fg_spin()` 支持通过 `feature_outcome` 提供指定结果：

- 使用 `initial_board` 指定初始盘面。
- 使用 `scatter_count`、`super_scatter_count`、`bonus_count` 指定功能图标数量。
- 使用 `golden_rounds` 指定各轮金色位置结果。
- 使用 `feature_win` 或 `feature_win_multiple` 指定额外 Bonus 奖励。

传入完整 Bonus 结果时使用外部结果；没有传入结果且满足 Bonus 触发条件时，使用 `yngg_bonus.conf` 的权重生成结果。

## 11. 配置生成

运行以下命令可依据参考轴重新生成 yngg 配置：

```powershell
python -B ThemeMath\yngg\build_from_demo.py --demo-dir <参考数据目录>
```

生成内容包括游戏配置、Bonus 配置、普通轴、免费轴以及 FIX/ZERO 固定结果。
