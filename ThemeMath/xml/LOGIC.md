# XML 水果机数学逻辑

## 1. 玩法概述

XML 是单轮盘水果机玩法。玩家分别对 symbol `2-9` 中的一个或多个 symbol
下注，spin 后按配置抽取一个轮盘 index，并根据该 index 对应的 symbol 和倍数
结算。

核心文件：

- `theme_math.py`：水果机、Bonus、翻倍和配置校验。
- `simulation.py`：固定下注组合的蒙特卡洛模拟。
- `special/xml_game_config.conf`：BaseBet 和通用格式配置。
- `special/xml_game_server.conf`：轮盘、X、开奖权重、Bonus 和翻倍配置。
- `reel_config/xml_rand_ex_0.conf`：使用 `ReelConfig` 的普通轴占位配置。
- `free_reel_config/xml_free_rand_ex_0.conf`：使用同一 `ReelConfig` 的免费轴占位配置。

## 2. Symbol 和下注

- `symbol 0`：Bonus 触发 symbol。
- `symbol 1`：当前玩法未使用。
- `symbol 2-9`：八个可下注水果图标。

玩家至少选择一个 symbol。每个 symbol 的下注金额必须满足：

```text
symbol_bet > 0
symbol_bet % BaseBet == 0
```

当前 `BaseBet=10000`，因此合法下注包括 `10000`、`20000`、`30000` 等。
不同 symbol 可以使用不同下注金额，总下注为所有 symbol 注额之和。

## 3. 普通 Spin

`ReelConfig`、`MultiConfig`、`WinWeightConfig` 和
`BonusWinWeightConfig` 长度必须相同，且相同下标表示同一个轮盘位置。
`SymbolMultiWeight`、`HighSymbolMulti` 和 `LowSymbolMulti` 使用相同下标。

一次普通 spin 的流程：

1. 校验各 symbol 的下注。
2. 按 `WinWeightConfig` 加权抽取一个 `trigger_index`。
3. 读取 `ReelConfig[trigger_index]` 得到中奖 symbol。
4. 读取 `MultiConfig[trigger_index]` 并按 symbol 规则得到本次 X。
5. symbol 非 0 时直接结算该 index。
6. symbol 为 0 时进入 Bonus。

代码和结果中的 `index` 为 0 基；`position` 为方便显示的 1 基位置。

## 4. 普通派彩

获取本次赢钱倍数 X：

```text
1. 读取 MultiConfig[index]
2. 如果该值不为 1，X = MultiConfig[index]
3. 如果该值为 1：
   - symbol 3/4/5：
     按 SymbolMultiWeight 抽取下标，
     X = HighSymbolMulti[下标]
   - symbol 6/7/8：
     按 SymbolMultiWeight 抽取下标，
     X = LowSymbolMulti[下标]
   - symbol 9：X = 5
```

同一次 spin 只按 `SymbolMultiWeight` 抽取一次下标。该 spin 中所有需要动态 X
的 High symbol（3/4/5）和 Low symbol（6/7/8）共用这个下标，再分别从
`HighSymbolMulti`、`LowSymbolMulti` 读取 X。`MultiConfig != 1` 的位置
仍直接使用其固定 X，不受共享下标影响。

symbol 2 的轮盘位置必须直接在 `MultiConfig` 配置非 1 的 X。

单个中奖 index 的派彩公式为：

```text
win = symbol_bet / BaseBet * ITEM_PRIZE_symbol_id * X
```

未下注的中奖 symbol 派彩为 0。同一个 symbol 在 Bonus 中通过多个不同 index
中奖时，每个 index 独立计算并累加。

固定 X 示例：

```text
symbol 3下注 = 10000
BaseBet = 10000
ITEM_PRIZE_3 = 10000
index 14的MultiConfig = 3
X = 3

win = 10000 / 10000 * 10000 * 3
    = 30000
```

动态 X 示例：

```text
symbol 3下注 = 20000
ITEM_PRIZE_3 = 10000
该位置MultiConfig = 1
SymbolMultiWeight抽中的下标 = 0
HighSymbolMulti[0] = 40
X = 40

win = 20000 / 10000 * 10000 * 40
    = 800000
```

## 5. Bonus

普通 spin 抽到 `symbol 0` 时：

1. 按 `RespinCountWeight` 抽取额外获取的 symbol 数量。
2. 数组下标 `0-7` 分别表示 `1-8` 个；权重可将某些数量关闭。当前前两项为
   0，因此实际可抽取 `3-8` 个。
3. 使用 `BonusWinWeightConfig`，按权重不放回抽取对应数量的不同 index。
4. 依次结算抽中的 index。
5. Bonus 权重中 symbol 0 位置必须为 0，禁止递归触发 Bonus。

Bonus 不包含保底逻辑。额外 index 只由 `BonusWinWeightConfig` 决定，不会根据
玩家下注的 symbol 过滤或补选，因此额外 symbol 可能完全不包含玩家下注的
symbol，此时 Bonus 派彩可以为 0。

当前 `WinWeightConfig` 中 symbol 0 对应的 index `9`、`21` 权重均为 0，
因此基础配置不会通过普通 spin 触发 Bonus。保留 Bonus 逻辑供后续控制配置使用。

## 6. 翻倍玩法

只有基础派彩 `base_win > 0` 时才能选择翻倍。

### 6.1 基础规则

- 翻倍玩法始终开放，不使用启用开关。
- `DoubleMaxTimes=10`：最多尝试 10 次。
- `DoubleMultiple=2`：每次成功后当前赢钱乘 2。
- 玩家可选择不翻倍，也可选择尝试 1-10 次。
- 超过本局允许成功的倍乘次数时，本次赢钱归零。

### 6.2 DoubleWeight 分档

先按初始赢钱计算赢钱倍数：

```text
win_multiple = base_win / total_bet
```

根据赢钱倍数选择大于等于它的最小 `DoubleWeight_X`：

| 初始赢钱倍数 | 使用配置 |
|---|---|
| `<= 1` | `DoubleWeight_1` |
| `> 1` 且 `<= 5` | `DoubleWeight_5` |
| `> 5` 且 `<= 10` | `DoubleWeight_10` |
| `> 10` 且 `<= 25` | `DoubleWeight_25` |
| `> 25` 且 `<= 50` | `DoubleWeight_50` |
| `> 50` 且 `<= 100` | `DoubleWeight_100` |
| `> 100` | `DoubleWeight` |

每个权重数组的下标 `0-10` 表示本局允许成功倍乘的次数。中奖后只抽取一次，
不会在每次翻倍时重新做随机判断。

假设抽中的允许次数为 2：

- 玩家不翻倍：领取原赢钱。
- 玩家尝试 1 次：成功，赢钱变为 2 倍。
- 玩家尝试 2 次：两次都成功，赢钱变为 4 倍。
- 玩家尝试第 3 次：失败，赢钱归零。

### 6.3 控制段

`xml_game_server.conf` 保留 `[0]`、`[4]`、`[8]`、`[12]`、`[17]`
控制段。每个控制段均包含完整的：

- `DoubleMaxTimes`
- `DoubleMultiple`
- `DoubleWeight_1/5/10/25/50/100`
- `DoubleWeight`

当前数学逻辑读取 `[Game Info]`；控制段用于后续接入控制 index 时覆盖基础配置。

### 6.4 Control Group 砍分

基础派彩完成后、倍乘开始前，根据玩家 `group_index` 读取
`special_config/slot_control_group.conf` 中
`control_group_cut_multiple[group_index]`：

- 阈值为 0 时不砍分。
- `base_win / total_bet` 严格大于阈值时触发砍分。
- 砍分会完全替换原基础开奖结果，然后再进入倍乘流程。

如果原始 Spin 触发 Bonus，会先完成以下步骤：

1. 按 `RespinCountWeight` 获取完整额外 symbol 数量。
2. 生成并结算本次 Bonus 的全部额外 index。
3. 使用完整 Bonus 总赢分计算 `base_win / total_bet`。
4. 未超过 `RespinMaxMulti` 阈值时保留整个 Bonus；超过阈值时丢弃整个 Bonus，并按下述普通砍分
   规则重新生成一个受控 Spin 结果。

砍分结果选择：

1. 如果 symbol 2-9 中存在玩家未下注的 symbol，从所有未下注 symbol 中随机
   选择一个，再随机选择该 symbol 的一个轮盘位置。因为该 symbol 未下注，最终
   基础派彩为 0。
2. 如果玩家已下注全部 symbol，只比较 symbol 3-9 的下注额；从最低下注额的
   symbol 中随机选择一个，并强制使用该 symbol 的 `MultiConfig=3` 位置。
3. 多个未下注 symbol 或多个并列最低下注 symbol 均随机选择，不使用固定优先级。

结果中的 `control_result` 会记录 group、阈值、原始基础赢分、原始赢分倍数、
原始 trigger、完整 `original_bonus_result`、是否重新 Spin、砍分原因及强制后的
symbol/index。

## 7. RTP

当前 `WinWeightConfig` 总权重为 `1500`，symbol 0 的两个位置权重为 0。
在当前等权 `SymbolMultiWeight` 下：

- High symbol 动态 X 的期望值为 30。
- Mid symbol 动态 X 的期望值为 15。
- symbol `2-9` 各自的“位置权重 × 期望 X”总和均为 `1050`。
- `ITEM_PRIZE_2-9` 与 `BaseBet` 均为 `10000`。

因此任意单个 symbol 下注一个 BaseBet、不倍乘时：

```text
RTP = 1050 / 1500 = 0.7
```

全部 symbol 各下注一个 BaseBet 时，总 RTP 同样为 0.7。翻倍后的实际 RTP
还会受到 `DoubleWeight_X` 和玩家尝试次数影响。

## 8. 代码接口

普通 spin：

```python
from theme_math import ThemeMath

math = ThemeMath()
result = math.spin(
    {
        2: 100000,
        5: 300000,
        9: 200000,
    }
)
```

预设玩家最多尝试 2 次翻倍：

```python
result = math.spin(
    {2: 100000, 5: 300000},
    double_times=2,
)
```

关键结果字段：

- `bets`：各 symbol 的下注。
- `total_bet`：总下注。
- `base_win`：翻倍前赢钱。
- `total_win`：翻倍结束后的最终赢钱。
- `trigger_index`、`trigger_symbol_id`：主开奖位置和 symbol。
- `is_bonus`：是否进入 Bonus。
- `winning_indexes`：实际结算的 index。
- `outcomes`：各 index 的派彩明细。
- `outcomes[].multi_config`：该位置原始 `MultiConfig`。
- `outcomes[].item_prize`：中奖 symbol 的 `ITEM_PRIZE`。
- `outcomes[].symbol_multi_index`：动态 X 抽中的下标；固定 X 时为 `None`。
- `outcomes[].x`：本次实际使用的 X。
- `symbol_multi_index`：本次 spin 的 High/Mid 共享动态 X 下标。
- `double_result.selected_times`：权重抽中的允许成功次数。
- `double_result.double_weight_key`：本局使用的权重档位。
- `double_result.attempted_times`：实际尝试次数。
- `double_result.success_times`：成功次数。
- `double_result.failed`：是否因超过允许次数而归零。
- `group_index`：本次使用的玩家控制组下标。
- `control_result`：砍分判断和强制结果明细。

## 9. 模拟

`simulation.py` 已按 RZCS 的入口和报表结构实现，支持单参数组合、批量组合、
阶段检查点、分组控制台表格和 CSV 追加。

默认参数：

```python
SPIN_TIMES = 1_000_000
REPORT_INTERVAL = 5_000
Bet_Multi = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1]
Double_Times = 0
BET_MULTIS = [Bet_Multi]
DOUBLE_TIMES = [Double_Times]
GROUP_INDEXES = [0]
SEEDS = [None]
```

`Bet_Multi[symbol_id]` 表示该 symbol 的 BaseBet 倍数：

```text
实际下注 = BaseBet * Bet_Multi[symbol_id]
```

倍数为 0 表示不下注。`Bet_Multi[0]` 和 `Bet_Multi[1]` 必须为 0。
`Double_Times` 表示玩家赢钱后最多主动尝试的翻倍次数，0 表示不翻倍。

### 9.1 Python 接口

- `simulation(...)`：运行一个参数组合，返回阶段检查点行。
- `simulate(...)`：兼容旧接口，返回最终结果行。
- `simulation_all(...)`：运行全部下注、倍乘次数和 seed 组合。
- `print_table(...)`：输出与 RZCS 类似的分组统计表。
- `append_simulation_results(...)`：追加最终行到 `simulate_result.csv`。

### 9.2 命令行

单组参数：

```bash
python simulation.py \
  --spins 100000 \
  --bet-multi "0,0,1,1,1,1,1,1,1,1" \
  --double-times "0" \
  --group-indexes "0" \
  --seed 7
```

多组下注使用分号分隔，多组倍乘次数和 seed 使用逗号分隔：

```bash
python simulation.py \
  --spins 100000 \
  --bet-multis "0,0,1,1,1,1,1,1,1,1;0,0,2,0,0,0,0,0,0,0" \
  --double-times "0,1,2" \
  --group-indexes "0,12" \
  --seeds "7,8"
```

其他参数：

- `--report-interval`：阶段统计间隔。
- `--no-print-updates`：运行时不打印阶段表格。

### 9.3 输出

每个最终结果会打印并追加到 `simulate_result.csv`，主要包括：

- 基础和最终 RTP。
- 倍乘带来的 RTP 增减。
- Hit 率、Bonus 率。
- Bonus 额外 symbol 总数、平均数量及 1-8 个的分布。
- `>5x` 至 `>1000x` 分布。
- 翻倍尝试、成功和失败次数。
- Control group 砍分次数、频率及砍分前原始赢分。
- 抽中的倍乘次数分布。
- 各 `DoubleWeight_X` 档位使用次数。
- symbol `2-9` 各自的累计下注、命中次数、赢钱和 RTP。
- `ok`、错误信息和完整累计 `status`。

## 10. 配置校验

初始化 `ThemeMath` 时会检查：

- 四组轮盘配置长度一致。
- symbol id、倍数和权重合法。
- `SymbolMultiWeight`、`HighSymbolMulti`、`LowSymbolMulti` 非空且长度一致。
- 动态 X 权重非负，X 全部大于 0。
- `ITEM_PRIZE_2-9` 全部大于 0。
- `MultiConfig=1` 的 symbol 必须存在动态 X 或固定 X=5 的规则。
- `RespinCountWeight` 必须包含 8 项，且权重非负、总和大于 0。
- Bonus 的正权重 index 数量必须覆盖 Respin 可选的最大数量。
- Bonus 中 symbol 0 位置权重为 0。
- `ITEM_COUNT` 能覆盖 ReelConfig 中的最大 symbol id。
- 每个 `DoubleWeight_X` 长度为 `DoubleMaxTimes + 1`。
- `DoubleWeight_100` 必须存在。
- 所有 DoubleWeight 非负且权重总和大于 0。

## 11. MJWL 格式兼容文件

目录和文件名已按 MJWL 格式整理，并将 `mjwl_` 前缀替换为 `xml_`。缺失的通用
配置文件直接复制自 MJWL，用于保持部署目录结构兼容。

当前水果机数学流程不读取复制来的 Ways、活动和通用控制配置；
`xml_rand_ex_0.conf` 与 `xml_free_rand_ex_0.conf` 已改为当前
`ReelConfig` 的占位轴。后续接入其他模块前，需要将其中的 MJWL 内容替换为 XML
的正式配置。
