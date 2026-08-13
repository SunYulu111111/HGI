# 1. 基础信息

## 1.1 盘面

- 列数：5
- 行数：6
- 原始牌面：5x6
- 有效结构：
  - Base：45554
  - Free：45554
- 无效格配置：
  - Base：`GRID_DISABLES`
  - Free：`GRID_DISABLES_FREE`

原始 5x6 牌面按列优先排列。计算前会按无效格配置裁剪为有效牌面，当前配置为第 1/5 列保留 4 格，第 2/3/4 列保留 5 格。

## 1.2 符号类型

- 0：Scatter
- 1：Wild
- 2~10：普通符号
- 100+普通符号：金色 symbol

金色 symbol 只是一种临时编码。算奖时会先还原为原始 symbol id；第一次被消除时不会离开牌面，而是变成 Wild。

---

# 2. Reel / General 选择

## 2.1 Base

Base 使用 `reel_config/mjwl_rand_ex_{INDEX}.conf`。

| 输入 | 使用配置 | 说明 |
| --- | --- | --- |
| `index` | `mjwl_rand_ex_{index}.conf` | 找不到精确 index 时由通用 reel 查找逻辑回退 |
| `WinBoxLevelUpRate` 抽中第 1 档 | `GENERAL_1` | 未触发 base 倍乘框升级 |
| `WinBoxLevelUpRate` 抽中第 2 档及以上 | `GENERAL_2` | 触发 base 倍乘框升级 |
| `BASE_RATE` | normal / special / fix / zero | 顺序为 `正常盘,特殊盘,固定盘,0几率盘` |

`BASE_RATE` 只决定本次 spin 使用哪类盘：

- normal：`NORMAL_ROLL_1..5`
- special：`SP_ROLL_1..5`
- fix：`FIX_RESULT_n`
- zero：`ZERO_RESULT_n`

## 2.2 Free

Free 使用 `free_reel_config/mjwl_free_rand_ex_{INDEX}.conf`。

| 条件 | 使用 General | 说明 |
| --- | --- | --- |
| `choose_index=1` | `GENERAL_1` | 24 次 free，倍乘 `[1,2,3,5]` |
| `choose_index=2` | `GENERAL_2` | 12 次 free，倍乘 `[2,4,6,10]` |
| `choose_index=3` | `GENERAL_3` | 8 次 free，倍乘 `[3,6,9,15]` |
| `choose_index=4` | `GENERAL_4` | 6 次 free，倍乘 `[4,8,12,20]` |
| `choose_index=5` | 随机 `GENERAL_n` | 次数和倍乘分别按权重随机 |

也可以通过 `free_general_index` 强制指定 free 使用的 `GENERAL_n`。

## 2.3 game_server section

根据玩家 `INDEX` 读取 `mjwl_game_server.conf`：

1. 优先读取同名 section，例如 `[13]`
2. 如果不存在，回退到 `[0]`
3. 如果仍不存在，回退到 `[Game Info]`

---

# 3. 主游戏 Base

## 3.1 Spin 流程

1. 根据 `INDEX` 读取 game server 配置段
2. 根据 `WinBoxLevelUpRate` 抽取 base 倍乘框档位
3. 未升级使用 base `GENERAL_1`，升级使用 base `GENERAL_2`
4. 根据 `BASE_RATE` 选择 normal / special / fix / zero
5. 生成原始 5x6 牌面
6. 按 `GRID_DISABLES` 裁剪成 45554 有效牌面
7. 根据倍乘框档位选择金色 symbol 权重：
   - 未升级：使用 `GoldSymbolWeight`
   - 升级：使用 `LevelUpGoldWeight`
8. 按第 2/3/4 列权重把普通 symbol 转成金色 symbol
9. 计算 Ways 中奖
10. 消除中奖 symbol 并补牌
11. 按消除轮次应用 base 倍乘
12. 重复消除，直到无中奖或达到消除上限
13. 最终牌面 Scatter 数量 >= 3 时触发 free

## 3.2 Base 倍乘框

Base 每次 spin 会先按以下配置抽取一组消除倍乘：

```text
WinBoxLevelUpRate=2000,40,8,2
WinBoxLevelMultiple_1=1,2,3,5
WinBoxLevelMultiple_2=2,4,6,10
WinBoxLevelMultiple_3=3,6,9,15
WinBoxLevelMultiple_4=4,8,12,20
```

`WinBoxLevelUpRate` 是权重，不是直接概率。抽中第 1 档时视为未升级；抽中第 2 档及以上时视为触发倍乘框升级。

每轮消除按轮次取倍乘：

| 消除轮次 | 使用倍乘下标 |
| --- | --- |
| 第 1 次消除 | 第 1 个倍乘 |
| 第 2 次消除 | 第 2 个倍乘 |
| 第 3 次消除 | 第 3 个倍乘 |
| 第 4 次及以后 | 第 4 个倍乘 |

## 3.3 Base 金色 symbol

Base 未触发倍乘框升级时，使用：

```text
GoldSymbolWeight =750,600,730
```

Base 触发倍乘框升级时，使用：

```text
LevelUpGoldWeight = 1000,1000,1000
```

权重顺序对应第 2/3/4 列，概率均为万分比。

金色 symbol 规则：

- 只有普通可赔付 symbol 可以转成金色
- Scatter 和 Wild 不会转成金色
- 金色 symbol 编码为 `100 + symbol_id`
- 算奖时按原 symbol id 参与 Ways 计算
- 第一次被消除时变成 Wild
- 变成 Wild 后再次中奖才会被移除

## 3.4 Free 触发判断

每次 base 消除结束后，使用最终牌面判断 free：

- 只统计有效格上的普通 Scatter（symbol 0）
- Scatter 数量 >= 3 时触发 free
- free 次数不使用 `SCATTER_MULTIPLES`
- free 次数由 `choose_index` 对应的 `FREE_COUNT_LIST` 决定

当前 `SCATTER_MULTIPLES` 和 `SCATTER_PRIZES` 均为 0，Scatter 本身不直接派彩。

## 3.5 选择规则

Base 触发 free 后，按外部传入的 `choose_index` 决定 free 类型：

| choose_index | free 次数 | free 倍乘序列 | free general |
| --- | --- | --- | --- |
| 1 | 24 | `1,2,3,5` | `GENERAL_1` |
| 2 | 12 | `2,4,6,10` | `GENERAL_2` |
| 3 | 8 | `3,6,9,15` | `GENERAL_3` |
| 4 | 6 | `4,8,12,20` | `GENERAL_4` |
| 5 | 随机 | 随机 | 随机 |

`choose_index=5` 时，次数和倍乘档位分别按以下权重随机：

```text
FREE_RANDOM_COUNT_WEIGHTS = 2,3,4,5
FREE_RANDOM_MULTI_WEIGHTS = 11,8,8,6
```

---

# 4. JP 逻辑

当前 `mjwl` math 逻辑中没有 JP 判断。

- Base 未触发 free 时不会进入 JP
- Free 中也不会触发 JP
- `mjwl_game_server.conf` 中未配置 `WIN_JP_*` 相关字段

---

# 5. 免费游戏 Free

## 5.1 进入 Free 时记录

Base 触发 free 后会记录一份 `free_choice`：

- `choose_index`
- `times_index`
- `multiplier_index`
- `free_index`
- `free_times`
- `free_count_max`
- `multipliers`

其中 `free_index = multiplier_index + 1`，默认用于选择 `free_reel_config` 中的 `GENERAL_n`。

## 5.2 Free Spin 流程

每次 free spin：

1. 根据 `free_choice` 或 `choose_index` 确定 free 次数和倍乘序列
2. 根据 `free_general_index` / `free_index` 读取 free reel general
3. 根据 `BASE_RATE` 选择 normal / special / fix / zero
4. 生成原始 5x6 牌面
5. 按 `GRID_DISABLES_FREE` 裁剪成 45554 有效牌面
6. 根据 `FreeGoldSymbolWeight_n` 把第 2/3/4 列普通 symbol 转成金色 symbol
7. 计算 Ways 中奖
8. 消除中奖 symbol 并补牌
9. 按 free 倍乘序列应用消除轮次倍乘
10. 最终牌面 Scatter 数量 >= 3 时重触发 free

## 5.3 Free 倍乘

Free 倍乘由进入 free 时的 `free_choice["multipliers"]` 决定。

| choose_index | 倍乘序列 |
| --- | --- |
| 1 | `1,2,3,5` |
| 2 | `2,4,6,10` |
| 3 | `3,6,9,15` |
| 4 | `4,8,12,20` |

每轮消除按轮次取倍乘：

| 消除轮次 | 使用倍乘下标 |
| --- | --- |
| 第 1 次消除 | 第 1 个倍乘 |
| 第 2 次消除 | 第 2 个倍乘 |
| 第 3 次消除 | 第 3 个倍乘 |
| 第 4 次及以后 | 第 4 个倍乘 |

## 5.4 Free 金色 symbol

Free 使用 `FreeGoldSymbolWeight_n`，其中 `n` 为 free general index。

```text
FreeGoldSymbolWeight_1 = 450,10000,550
FreeGoldSymbolWeight_2 = 450,10000,550
FreeGoldSymbolWeight_3 = 500,10000,600
FreeGoldSymbolWeight_4 = 500,10000,600
```

在 `[13]` section 中当前配置为：

```text
FreeGoldSymbolWeight_1 = 650,10000,550
FreeGoldSymbolWeight_2 = 650,10000,550
FreeGoldSymbolWeight_3 = 700,10000,600
FreeGoldSymbolWeight_4 = 700,10000,600
```

权重顺序对应第 2/3/4 列，概率均为万分比。

## 5.5 Free 重触发

Free 中同样在消除结束后的最终牌面上统计 Scatter：

- 有效格 Scatter 数量 >= 3 时重触发
- 重触发次数等于当前 `free_choice["free_times"]`
- 不重新进入选择逻辑
- 额外 free 次数累加到当前剩余 free spin 中

---

# 6. Ways 中奖计算

- 使用 Ways 玩法
- 当前 `LINE_MODE=1`
- 从左向右连续计算
- 每个普通 symbol 单独计算 ways
- 最少 3 连才中奖
- Wild 可替代普通 symbol
- Scatter 和 Wild 自身不参与普通派彩

当前 symbol id：

| Symbol | 含义 |
| --- | --- |
| 0 | Scatter |
| 1 | Wild |
| 2~10 | 普通 symbol |
| 100+symbol | 金色 symbol |

Ways 计算规则：

1. 从第 1 列开始向右连续找同一 symbol
2. 某列没有命中时停止
3. 命中列数 >= `BASE_NUMS[symbol]` 才中奖
4. 每列命中数量相乘得到 ways
5. 赢钱公式：

```text
win = base_bet * prize * ways / BET_UNIT / PRIZE_RATE
```

当前配置中 `BET_UNIT=10000`，`PRIZE_RATE=1`。

---

# 7. 关键配置

## 7.1 mjwl_game_config.conf

- `COL_COUNT`
- `ROW_COUNT`
- `ITEM_COUNT`
- `PRIZE_RATE`
- `USE_WILDS`
- `BASE_NUMS`
- `ITEM_PRIZES_0..10`
- `LINE_MODE`
- `SCATTER_MODE`
- `SCATTER_ID`
- `SCATTER_COLS`
- `SCATTER_SERIAL`
- `SCATTER_MULTIPLES`
- `SCATTER_PRIZES`
- `GRID_DISABLES`
- `GRID_DISABLES_FREE`

## 7.2 mjwl_game_server.conf

- `FREE_COUNT_LIST`
- `FREE_MULTI_LIST_1..4`
- `FREE_RANDOM_COUNT_WEIGHTS`
- `FREE_RANDOM_MULTI_WEIGHTS`
- `WinBoxLevelUpRate`
- `WinBoxLevelMultiple_1..4`
- `FreeMaxGameNum`
- `Base_Max_EliTimes`
- `Free_Max_EliTimes`
- `BetGeneralCtrl`
- `Free_Max_TotalBet`
- `GoldSymbolWeight`
- `FreeGoldSymbolWeight_1..4`
- `Gua_Last_Spins_List`
- `LevelUpGoldWeight`

注意：当前 math 代码读取消除上限的 key 为 `MainMaxRoundNum / FreeMaxRoundNum`；如果未配置，则不使用配置上限，只受函数参数 `max_cascades` 限制。

## 7.3 reel_config / free_reel_config

- `BASE_RATE`
- `NORMAL_ROLL_1..5`
- `SP_ROLL_1..5`
- `FIX_RESULT_n`
- `ZERO_RESULT_n`

`BASE_RATE` 顺序固定为：

```text
normal,special,fix,zero
```

---

# 8. 执行顺序

## Base

1. 根据 `INDEX` 读取 game server 配置段
2. 按 `WinBoxLevelUpRate` 抽取 base 倍乘框档位
3. 未升级读取 base `GENERAL_1`，升级读取 base `GENERAL_2`
4. 根据 `BASE_RATE` 选择 normal / special / fix / zero
5. Spin 生成 5x6 牌面
6. 按 `GRID_DISABLES` 裁剪为 45554
7. 未升级使用 `GoldSymbolWeight`，升级使用 `LevelUpGoldWeight`
8. 第 2/3/4 列按权重生成金色 symbol
9. 计算 Ways 中奖
10. 按当前消除轮次应用 base 倍乘
11. 金色 symbol 第一次消除变 Wild；普通 symbol 直接消除
12. 上方 symbol 下落，并从当前停轴上方继续补牌
13. 重复计算，直到无中奖
14. 根据最终牌面 Scatter 数量判断是否触发 free

## Free

1. 根据 `free_choice/free_general_index` 读取 free reel
2. 根据 `BASE_RATE` 选择 normal / special / fix / zero
3. Spin 生成 5x6 牌面
4. 按 `GRID_DISABLES_FREE` 裁剪为 45554
5. 根据 free general 使用 `FreeGoldSymbolWeight_n`
6. 第 2/3/4 列按权重生成金色 symbol
7. 计算 Ways 中奖
8. 按当前消除轮次应用 free 倍乘
9. 金色 symbol 第一次消除变 Wild；普通 symbol 直接消除
10. 上方 symbol 下落，并从当前停轴上方继续补牌
11. 重复计算，直到无中奖
12. 根据最终牌面 Scatter 数量判断是否重触发 free

---

# 9. Simulation 参数

`simulation.py` 中主要参数：

| 参数 | 说明 |
| --- | --- |
| `SPIN_TIMES` | 仿真次数，默认 `1000000` |
| `INDEX` | reel index 列表，默认 `[0]` |
| `GENERAL_INDEX` | base general 列表，默认 `[1]` |
| `CHOOSE_INDEXES` | free 选择列表，默认 `[1]` |
| `REPORT_INTERVAL` | 进度刷新间隔，默认 `5000` |

命令行参数：

| 参数 | 说明 |
| --- | --- |
| `--spins` | 覆盖仿真次数 |
| `--indexes` | 指定 index 列表 |
| `--generals` | 指定 base GENERAL 列表 |
| `--free-generals` | 指定 free GENERAL 列表 |
| `--choose-indexes` | 指定 choose index 列表 |
| `--report-interval` | 覆盖报告间隔 |
| `--no-print-updates` | 不打印中途进度 |

`FREE_GENERAL` 展示规则：

- 如果显式传入 `free_general_index`，展示该值
- 如果 `choose_index=5`，展示实际随机使用过的 free general 集合
- 否则展示 `choose_index`

---

# 10. 关键注意事项

1. 当前玩法是 Ways 消除玩法，不是固定线玩法。
2. 原始牌面是 5x6，实际计算牌面为 45554。
3. Base 和 Free 使用相同有效结构，但分别读取 `GRID_DISABLES / GRID_DISABLES_FREE`。
4. Scatter 只用于最终牌面触发 free，不直接派彩。
5. Scatter 触发条件是最终有效牌面 Scatter 数量 >= 3。
6. free 次数由 `FREE_COUNT_LIST` 和 `choose_index` 决定，不由 `SCATTER_MULTIPLES` 决定。
7. `choose_index=5` 时，free 次数和倍乘档位分别独立随机。
8. base 倍乘框档位由 `WinBoxLevelUpRate` 权重抽取。
9. base 未升级时使用 `GoldSymbolWeight`。
10. base 升级时使用 `LevelUpGoldWeight`。
11. Free 使用 `FreeGoldSymbolWeight_n`，其中 `n` 对应 free general。
12. 金色 symbol 算奖时按原 symbol 参与，第一次消除后变 Wild。
13. Wild 可以替代普通 symbol，但 Scatter 和 Wild 自身不派普通奖。
14. 消除补牌从本次停轴上方继续取 symbol。
15. 当前 math 逻辑中没有 JP。
16. 所有直接概率配置均使用万分比。
17. `WinBoxLevelUpRate`、`FREE_RANDOM_COUNT_WEIGHTS`、`FREE_RANDOM_MULTI_WEIGHTS` 是权重，不是万分比概率。
