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
2. 若存在 Wild，根据 `WIN_JP_PROBABILITY` 判断是否进入 JP
3. 若进入 JP，根据 `WIN_JP_TYPE_PROBABILITY` 随机 JP 类型
4. 根据 `WIN_JP_MULTIPLE` 获取基础 JP 倍数
5. 根据 JP 类型对应的 `WIN_JP_DOUBLE_PROBABILITY` 判断是否翻倍
6. 最终 JP 赢分为：

```text
jp_win = base_bet * final_jp_multiple
```

JP 概率配置在 `special/rzcs_game_server.conf` 中，概率均为万分比：

```text
WIN_JP_PROBABILITY=10
WIN_JP_MULTIPLE=5000,100,50,20
WIN_JP_TYPE_PROBABILITY=1,5,100,500
WIN_JP_DOUBLE_PROBABILITY=10,100,500,1000
```

`WIN_JP_DOUBLE_PROBABILITY` 顺序对应 `WIN_JP_MULTIPLE=5000,100,50,20`：

| JP基础倍数 | 翻倍概率(万分比) | 说明 |
| --- | --- | --- |
| 5000 | 10 | 10/10000 |
| 100 | 100 | 100/10000 |
| 50 | 500 | 500/10000 |
| 20 | 1000 | 1000/10000 |

若命中翻倍：

```text
final_jp_multiple = base_jp_multiple * 2
```

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
FREE_MULTIPLE_TRIGGER_PROBABILITY=10000,5000
```

该配置顺序对应：

| Index | 条件 | 说明 |
| --- | --- | --- |
| 0 | `base_bet < SPECIAL_TYPE_NEED_BET` | 必定触发普通 free 倍乘 |
| 1 | `base_bet >= SPECIAL_TYPE_NEED_BET` | 50% 概率触发普通 free 倍乘 |

因此：

| 条件 | 结果 |
| --- | --- |
| `base_bet < SPECIAL_TYPE_NEED_BET` | 本次 spin 赢钱必定 `*2` |
| `base_bet >= SPECIAL_TYPE_NEED_BET` | 本次 spin 赢钱 50% 概率 `*2`，50% 概率 `*1` |

---

### Super Free

Super free 的倍乘配置：

```text
SUPER_FREE_MULTIPLE=6,8,15
SUPER_FREE_MULTIPLE_PROBABILITY=100,50,10
```

是否应用 super free 倍乘由以下配置控制，概率为万分比：

```text
SUPER_FREE_MULTIPLE_TRIGGER_PROBABILITY=10000,5000
```

该配置顺序对应：

| Index | 条件 | 说明 |
| --- | --- | --- |
| 0 | `base_bet < SPECIAL_TYPE_NEED_BET` | 必定触发 super free 倍乘 |
| 1 | `base_bet >= SPECIAL_TYPE_NEED_BET` | 50% 概率触发 super free 倍乘 |

因此：

| 条件 | 结果 |
| --- | --- |
| `base_bet < SPECIAL_TYPE_NEED_BET` | 本次 spin 必定从 `6/8/15` 中按权重抽取倍乘 |
| `base_bet >= SPECIAL_TYPE_NEED_BET` | 本次 spin 50% 概率从 `6/8/15` 中按权重抽取倍乘，50% 概率 `*1` |

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

- `SPECIAL_TYPE_NEED_BET`
- `GRID_DISABLES`
- `GRID_DISABLES_FREE`
- `SCATTER_ID`
- `WILD_ID`
- `SCATTER_MULTIPLES`

## 7.2 special/rzcs_game_server.conf

- `WIN_JP_PROBABILITY`
- `WIN_JP_MULTIPLE`
- `WIN_JP_TYPE_PROBABILITY`
- `WIN_JP_DOUBLE_PROBABILITY`
- `FREE_MULTIPLE`
- `FREE_MULTIPLE_PROBABILITY`
- `FREE_MULTIPLE_TRIGGER_PROBABILITY`
- `SUPER_FREE_MULTIPLE`
- `SUPER_FREE_MULTIPLE_PROBABILITY`
- `SUPER_FREE_MULTIPLE_TRIGGER_PROBABILITY`

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

- `SPIN_TIMES=1000000`
- `INDEX=[0]`
- `BASE_BETS=[10000]`
- `FREE_CHOOSE_INDEX=[1]`
- `REPORT_INTERVAL=5000`

---

# 10. 关键注意事项

1. Base 是否使用高 bet 逻辑，以 `base_bet >= SPECIAL_TYPE_NEED_BET` 判断
2. Base 高 bet 使用 `GENERAL_1`，低 bet 使用 `GENERAL_2`
3. `GRID_DISABLES` 表示未解锁第三列分裂，`GRID_DISABLES_FREE` 表示已解锁第三列分裂，与 Base/Free 无关
4. Free general 由 bet 和 `is_super` 共同决定
5. Base 中累计 free 次数 `>= 16` 才进入选择玩法
6. Base 中累计 free 次数 `< 16` 直接进入普通 free
7. Free 中不进入选择玩法，只累加额外 free 次数
8. 普通 free 低 bet 必定 `*2`，高 bet 按 `FREE_MULTIPLE_TRIGGER_PROBABILITY` 判断是否 `*2`
9. Super free 低 bet 必定随机倍乘，高 bet 按 `SUPER_FREE_MULTIPLE_TRIGGER_PROBABILITY` 判断是否随机倍乘
10. JP 只在 Base 未触发 free 时判断
11. JP pick 后会按 JP 类型概率判断是否翻倍
12. 当前 symbol id 已压缩，不再区分分裂和非分裂 symbol
13. 所有直接概率配置均使用万分比
14. `WIN_JP_TYPE_PROBABILITY`、`FREE_MULTIPLE_PROBABILITY`、`SUPER_FREE_MULTIPLE_PROBABILITY` 是权重，不是万分比概率
