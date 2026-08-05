# 1. 基础信息

## 1.1 盘面

- 列数：5
- 行数：6
- 原始牌面：5x6
- 未解锁第三列分裂有效结构：33333
- 已解锁第三列分裂有效结构：33633

## 1.2 符号类型

- 0：Scatter
- 1：Wild
- 2~11：普通符号

当前配置中不再区分分裂 symbol 和非分裂 symbol，计算时直接使用配置中的 symbol id。

---

# 2. Reel / General 选择

## 2.1 Base

根据玩家 `base_bet >= SPECIAL_TYPE_NEED_BET` 判断：

| 条件 | 使用 General | 当前有效结构 |
| --- | --- | --- |
| `base_bet >= SPECIAL_TYPE_NEED_BET` | `GENERAL_1` | 33633 |
| `base_bet < SPECIAL_TYPE_NEED_BET` | `GENERAL_2` | 33333 |

牌面结构由第三列分裂是否解锁决定，与 Base/Free 无关：

- 未解锁：使用 `GRID_DISABLES`
- 已解锁：使用 `GRID_DISABLES_FREE`

## 2.2 Free

根据玩家 `base_bet >= SPECIAL_TYPE_NEED_BET` 以及是否为 `super_free` 判断：

| 条件 | 使用 General | 当前有效结构 |
| --- | --- | --- |
| 低 bet，普通 free | `GENERAL_1` | 33333 |
| 高 bet，普通 free | `GENERAL_2` | 33633 |
| 低 bet，super free | `GENERAL_3` | 33333 |
| 高 bet，super free | `GENERAL_4` | 33633 |

Free 中同样按第三列分裂是否解锁选择有效结构，与普通 free / super free 无关。

---

# 3. 主游戏 Base

## 3.1 Spin 流程

1. 判断 `base_bet >= SPECIAL_TYPE_NEED_BET`
2. 根据结果选择 `GENERAL_1 / GENERAL_2`
3. 根据玩家 `INDEX` 加载 `special/rzcs_game_server.conf` 中对应 section；如果不存在则回退到 `[0]`
4. 生成 5x6 牌面
5. 根据第三列分裂是否解锁选择 `GRID_DISABLES / GRID_DISABLES_FREE`
6. 将无效格置空，形成 33333 / 33633
7. 计算 Line 中奖
8. 判断 scatter/wild 连线触发 free
9. 如果未触发 free，再判断 JP

## 3.2 Free 触发判断

遍历所有中奖线，从第一列开始向右连续判断：

- 连续符号只允许是 `Scatter(0)` 或 `Wild(1)`
- 连续长度 >= 3 才触发
- 每条线按长度获得 free 次数：
  - 3连：8次
  - 4连：12次
  - 5连：16次
- 多条线触发时，free 次数累加

## 3.3 选择规则

Base 中触发 free 后：

- 累计 free 次数 `>= 16`：进入选择玩法
- 累计 free 次数 `< 16`：直接进入普通 free
- 是否进入选择玩法不再根据触发线数量或触发线中是否包含 Wild 判断

选择选项：

1. 普通 free：合计 free 次数
2. Super free：合计 free 次数 / 4

---

# 4. JP 逻辑

仅当 Base 没有进入 free 时判断 JP，Free 中不触发 JP。

判断流程：

1. 检查有效牌面上是否存在 Wild
2. 若存在 Wild，根据 `rzcs_bonus.conf` 中当前 index 的 `BONUS_ENTER_RATE` 判断是否进入 JP
3. 若进入 JP，根据 `BONUS_JP_TYPE_PROBABILITY` 随机 JP 类型
4. 根据 `BONUS_JP_MULTIPLE` 获取基础 JP 倍数
5. 根据 JP 类型对应的 `BONUS_JP_DOUBLE_PROBABILITY` 判断是否翻倍
6. 最终 JP 赢分为：

```text
jp_win = base_bet * final_jp_multiple
```

JP 配置位于 `special/rzcs_bonus.conf`。所有 JP 数组统一按以下顺序排列：

| 数组下标 | JP类型 | 基础倍数 |
| --- | --- | --- |
| 0 | MINI | 20 |
| 1 | MINOR | 50 |
| 2 | MAJOR | 100 |
| 3 | GRAND | 5000 |

`[GENERAL]` 中配置四档 JP 倍数：

```text
BONUS_MINI_MULTI=20
BONUS_MINOR_MULTI=50
BONUS_MAJOR_MULTI=100
BONUS_GRAND_MULTI=5000
BONUS_ENTER_RATE=62
```

各控制类型 section 可独立覆盖 `BONUS_ENTER_RATE`、倍数、类型权重和翻倍概率。当前配置为：

```text
BONUS_JP_MULTIPLE=20,50,100,5000
BONUS_JP_TYPE_PROBABILITY=1399,50,5,1
BONUS_JP_DOUBLE_PROBABILITY=79,50,10,1
```

三个数组必须保持 `MINI → MINOR → MAJOR → GRAND` 的相同顺序：

| JP类型 | 基础倍数 | 类型权重 | 翻倍概率(万分比) |
| --- | --- | --- | --- |
| MINI | 20 | 1399 | 79 |
| MINOR | 50 | 50 | 50 |
| MAJOR | 100 | 5 | 10 |
| GRAND | 5000 | 1 | 1 |

`BONUS_JP_TYPE_PROBABILITY` 是相对权重，不要求总和为 10000；`BONUS_ENTER_RATE` 和 `BONUS_JP_DOUBLE_PROBABILITY` 使用万分比。

若命中翻倍：

```text
final_jp_multiple = base_jp_multiple * 2
```

## 4.1 collect_level 收集等级

仿真中维护玩家当前 `collect_level`：

- 最低等级为 1，最高等级为 5
- 初始等级由 `collect_level` 参数指定
- `level_up_rate` 表示当前等级升级到下一等级的概率，概率口径为万分比
- 每次 Base 牌面结算后，检查有效牌面上是否存在 `Wild(1)`
- 若有效牌面存在 Wild 且本次未触发 JP，则按 `level_up_rate` 尝试升一级，最高升到 4
- 若本次触发 JP，则按达到 `collect_level=5` 记录最高等级
- 触发 JP 玩法后，当前 `collect_level` 重置为 1
- Free 中不触发 JP，收集等级逻辑只在 Base 牌面后处理

---

# 5. 免费游戏 Free

## 5.1 进入 Free 时记录

Base 触发 free 后，根据玩家选择记录 free 类型：

- 普通 free：`is_super = 0`
- Super free：`is_super = 1`

## 5.2 Free Spin 流程

每次 free spin：

1. 根据 bet 和 `is_super` 选择 free general
2. 生成 5x6 牌面
3. 根据第三列分裂是否解锁选择 `GRID_DISABLES / GRID_DISABLES_FREE`
4. 修改牌面为 33333 / 33633
5. 计算 Line 中奖
6. 根据 free 类型应用赢钱倍乘
7. 判断是否再次触发 free

## 5.3 Free 倍乘

Free 倍乘根据 `base_bet >= SPECIAL_TYPE_NEED_BET` 的类型 index 和 free 类型共同决定。

### 普通 Free

普通 free 的基础倍乘配置：

```text
FREE_MULTIPLE=2
```

是否应用普通 free 倍乘由以下配置控制，概率为万分比：

```text
FREE_MULTIPLE_TRIGGER_PROBABILITY=10000,10000
```

该配置顺序对应：

| Index | 条件 | 说明 |
| --- | --- | --- |
| 0 | `base_bet < SPECIAL_TYPE_NEED_BET` | 必定触发普通 free 倍乘 |
| 1 | `base_bet >= SPECIAL_TYPE_NEED_BET` | 必定触发普通 free 倍乘 |

因此：

| 条件 | 结果 |
| --- | --- |
| `base_bet < SPECIAL_TYPE_NEED_BET` | 本次 spin 赢钱必定 `*2` |
| `base_bet >= SPECIAL_TYPE_NEED_BET` | 本次 spin 赢钱必定 `*2` |

---

### Super Free

Super free 的倍乘配置：

```text
SUPER_FREE_MULTIPLE=6,8,15
SUPER_FREE_MULTIPLE_PROBABILITY=100,50,10
```

是否应用 super free 倍乘由以下配置控制，概率为万分比：

```text
SUPER_FREE_MULTIPLE_TRIGGER_PROBABILITY=10000,10000
```

该配置顺序对应：

| Index | 条件 | 说明 |
| --- | --- | --- |
| 0 | `base_bet < SPECIAL_TYPE_NEED_BET` | 必定触发 super free 倍乘 |
| 1 | `base_bet >= SPECIAL_TYPE_NEED_BET` | 必定触发 super free 倍乘 |

因此：

| 条件 | 结果 |
| --- | --- |
| `base_bet < SPECIAL_TYPE_NEED_BET` | 本次 spin 必定从 `6/8/15` 中按权重抽取倍乘 |
| `base_bet >= SPECIAL_TYPE_NEED_BET` | 本次 spin 必定从 `6/8/15` 中按权重抽取倍乘 |

---

### 执行顺序

每次 free spin：

1. 根据 `base_bet >= SPECIAL_TYPE_NEED_BET` 判断当前类型 index：
   - 低 bet：index 0
   - 高 bet：index 1
2. 根据是否为 super free 选择对应倍乘配置
3. 先判断本次 spin 是否触发倍乘
4. 若未触发，倍乘为 `1`
5. 若触发：
   - 普通 free：使用 `FREE_MULTIPLE`
   - super free：按 `SUPER_FREE_MULTIPLE_PROBABILITY` 抽取 index，再从 `SUPER_FREE_MULTIPLE` 获取倍乘
6. 本次 free spin 总赢钱乘以最终倍乘

## 5.4 Free 重触发

Free 中同样遍历所有中奖线：

- 连续 scatter/wild 长度 >= 3 才触发
- 每条线按 8/12/16 次计算
- 多条线累加额外 free 次数
- Free 中不进入选择玩法，只增加额外 free 次数
- `Free重触发`、`普通Free重触发`、`SuperFree重触发` 统计额外获得的 free 次数总和，不统计重触发事件数
- 每局 free 的初始次数与重触发额外次数之和不能超过当前 index 的 `Free_Max_Spins`
- 当前 index `0/4/8/12/17` 均配置为 `Free_Max_Spins=960`
- Base 触发的初始 free 次数若超过 `Free_Max_Spins`，实际进入次数截断为 `Free_Max_Spins`
- 若接受当前牌面会使 free 总次数超过 `Free_Max_Spins`，则丢弃该牌面并重新 roll，直到结果不超过上限
- 被丢弃的牌面不计入 FreeSpin、赢钱或重触发统计

### Free 次数分组统计

仿真按 Base 触发时的原始 free 次数拆分为两组：

- `Free>=16`：原始 free 次数大于等于 16
- `Free<16`：原始 free 次数小于 16
- 分组判断发生在选择普通 Free / Super Free 之前；例如原始16次选择 Super Free 后变为4次，仍归入 `Free>=16`
- 触发后的整局 FreeSpin、赢钱、重触发额外次数和总次数始终记录在该组

---

# 6. Line 中奖计算

- 使用固定线玩法
- 当前配置为 60 条线
- 从左向右计算
- Wild 可替代普通符号
- Scatter/Wild 的中奖与替代能力由配置控制

当前 symbol id：

| Symbol | 含义 |
| --- | --- |
| 0 | Scatter |
| 1 | Wild |
| 2~11 | 普通 symbol |

---

# 7. 关键配置

## 7.1 special/rzcs_game_config.conf

- `GRID_DISABLES`
- `GRID_DISABLES_FREE`
- `SCATTER_ID`
- `WILD_ID`
- `SCATTER_MULTIPLES`

## 7.2 special/rzcs_game_server.conf

- `[Game Info]`
  - `SPECIAL_TYPE_NEED_BET`
- `[index]`
  - `Free_Max_Spins`（当前为 960）
  - `FREE_MULTIPLE`
  - `FREE_MULTIPLE_PROBABILITY`
  - `FREE_MULTIPLE_TRIGGER_PROBABILITY`
  - `SUPER_FREE_MULTIPLE`
  - `SUPER_FREE_MULTIPLE_PROBABILITY`
  - `SUPER_FREE_MULTIPLE_TRIGGER_PROBABILITY`

旧版本若仍在 `special/rzcs_game_config.conf` 中配置 `SPECIAL_TYPE_NEED_BET`，代码会作为回退读取。

## 7.3 special/rzcs_bonus.conf

- `[GENERAL]`
  - `BONUS_MINI_MULTI`
  - `BONUS_MINOR_MULTI`
  - `BONUS_MAJOR_MULTI`
  - `BONUS_GRAND_MULTI`
  - `BONUS_ENTER_RATE`
  - `BONUS_JP_MULTIPLE`
  - `BONUS_JP_TYPE_PROBABILITY`
  - `BONUS_JP_DOUBLE_PROBABILITY`
- `[index]`
  - `BONUS_ENTER_RATE`
  - `BONUS_JP_MULTIPLE`
  - `BONUS_JP_TYPE_PROBABILITY`
  - `BONUS_JP_DOUBLE_PROBABILITY`

---

# 8. 执行顺序

## Base

1. 根据 bet 选择 base general
2. Spin 生成 5x6 牌面
3. 根据第三列分裂是否解锁应用 `GRID_DISABLES / GRID_DISABLES_FREE`
4. 计算 Line 中奖
5. 计算 scatter/wild free 触发
6. 若触发 free，判断是否进入选择玩法
7. 若未触发 free，判断 JP
8. 若进入 JP，按类型概率判断是否翻倍

## Free

1. 根据 bet 和是否 super 选择 free general
2. Spin 生成 5x6 牌面
3. 根据第三列分裂是否解锁应用 `GRID_DISABLES / GRID_DISABLES_FREE`
4. 计算 Line 中奖
5. 根据普通 free / super free 应用倍乘
6. 计算 scatter/wild 重触发次数
7. 累加额外 free 次数

---

# 9. Simulation 参数

`simulation.py` 中可通过 `FREE_CHOOSE_INDEX` 控制选择玩法：

| FREE_CHOOSE_INDEX | 选择 |
| --- | --- |
| 1 | 普通 free |
| 2 | super free |

如果当前触发不满足选择条件，则无论传入哪个 `FREE_CHOOSE_INDEX`，都会按普通 free 处理。

默认仿真配置：

- `SPIN_TIMES=10000000`
- `INDEX=[0]`
- `BASE_BETS=[10000]`
- `FREE_CHOOSE_INDEX=[2]`
- `COLLECT_LEVEL=1`
- `LEVEL_UP_RATE=0`
- `REPORT_INTERVAL=5000`

相关命令行参数：

- `--collect-level`：初始收集等级，范围 1~5
- `--level-up-rate`：牌面出现有效 Wild 时从当前等级升到下一等级的概率，范围 0~10000

---

# 10. 关键注意事项

1. Base 是否使用高 bet 逻辑，以 `base_bet >= SPECIAL_TYPE_NEED_BET` 判断
2. Base 高 bet 使用 `GENERAL_1`，低 bet 使用 `GENERAL_2`
3. `GRID_DISABLES` 表示未解锁第三列分裂，`GRID_DISABLES_FREE` 表示已解锁第三列分裂，与 Base/Free 无关
4. Free general 由 bet 和 `is_super` 共同决定
5. Base 中累计 free 次数 `>= 16` 才进入选择玩法
6. Base 中累计 free 次数 `< 16` 直接进入普通 free
7. Free 中不进入选择玩法，只累加额外 free 次数
8. 普通 free 低 bet / 高 bet 都按 `FREE_MULTIPLE_TRIGGER_PROBABILITY=10000,10000` 必定 `*2`
9. Super free 低 bet / 高 bet 都按 `SUPER_FREE_MULTIPLE_TRIGGER_PROBABILITY=10000,10000` 必定随机倍乘
10. JP 只在 Base 未触发 free 时判断
11. JP pick 后会按 JP 类型概率判断是否翻倍
12. 当前 symbol id 已压缩，不再区分分裂和非分裂 symbol
13. 所有直接概率配置均使用万分比
14. `BONUS_JP_TYPE_PROBABILITY`、`FREE_MULTIPLE_PROBABILITY`、`SUPER_FREE_MULTIPLE_PROBABILITY` 是权重，不是万分比概率
15. `collect_level` 只在 Base 牌面后更新；普通 Wild 升级最高到 4
16. 触发 JP 时按达到 `collect_level=5` 记录最高等级，随后当前 `collect_level` 重置为 1
