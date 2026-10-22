# yngg 服务器逻辑修改说明

日期：2026年10月15日  
接收方：服务器程序与工具维护程序  
修改基准：当前 `ThemeMath/yngg/theme_math.py` 及 `special/yngg_bonus.conf`。

本文只保留最初两个 P0 问题的修复与验收基准：Bonus 档位按配置权重抽取，以及金币字段与单位对齐。对最新版 `server_ynggtool-2` 的审核已确认两项主要路径均已修复；下述异常配置与兼容用例仍可用于后续回归验收。

最初反馈场景为 group 0 使用正常轴 `BASE_RATE=100,0,0,0` 模拟100万局，RTP约12，即1200%。旧版工具对金币、四叶草、JP 的具体档位等概率抽取，未使用档位权重，是当时 RTP 异常偏高的重要原因。当前所有 GROUP/TYPE 的 Bonus 奖励统一使用 `special/yngg_bonus.conf` 的 `[GENERAL]` 原有参数，不读取数字节覆盖，不要求服务器按 TYPE 合并 Bonus。普通轴、免费轴和特殊图标生成概率仍按 TYPE 配置。

## P0 Bonus 金币 四叶草 JP 按档位权重抽取

### 问题与修改位置

旧版工具使用 `BONUS_SYMBOL_TYPE_PROBABILITY` 决定出现金币、四叶草、聚宝盆还是 JP，但对类型内部的具体档位使用等概率抽取。修复要求是在保留类型抽取的基础上，为金币、四叶草、JP 分别接入对应档位权重。

| 类型 | 旧版抽法 | 必须使用的档位权重 | 旧版问题位置 |
| --- | --- | --- | --- |
| 金币 | 随机数对金币档位数取模 | `BONUS_COIN_MULTIPLE_PROBABILITY` | `RollGoldCell`，`Yngg_Game.cpp:566`，地址 `0x4061d6` |
| 四叶草 | 随机数对四叶草档位数取模 | `BONUS_CLOVER_MULTIPLE_PROBABILITY` | `RollGoldCell`，`Yngg_Game.cpp:575`，地址 `0x4062c4` |
| JP | 随机数 `& 3`，四档各25% | `BONUS_JP_TYPE_PROBABILITY` | `RollGoldCell`，`Yngg_Game.cpp:585`，地址 `0x406343` |

上述位置来自旧版二进制的符号、调试信息和反汇编。最新版 `RollGoldCell` 已分别在 `Yngg_Game.cpp:554`、`:563`、`:573`（地址 `0x406165`、`0x406256`、`0x4062d0`）调用 `PickWeighted`，并由 `ReadBonusConf` 读取对应权重数组，已修复旧版均匀抽档问题。源码更新后以函数为定位依据。

Python 对应实现为 `_load_bonus_config`、`generate_golden_round`、`weighted_random_index`。

### 当前档位与权重

`special/yngg_bonus.conf` 只读取 `[GENERAL]`，所有 GROUP/TYPE 的 Base、Free 和重翻共用同一套 Bonus 参数。数字节不参与读取；不将旧 TYPE 0 专属低权重移到公共段。

以下均复用现有字段名。类型下标固定为 coin、clover、pot、jackpot，不依赖 `BONUS_SYMBOL_TYPE` 名称列表。

```ini
[GENERAL]
BONUS_SYMBOL_TYPE_PROBABILITY=1000,80,6,2

BONUS_COIN_MULTIPLE=0.2,0.5,1,2,3,4,5,10,15,20,25,50,100,250,500
BONUS_COIN_MULTIPLE_PROBABILITY=1560,1240,1030,860,720,545,415,320,228,165,110,62,31,10,3

BONUS_CLOVER_MULTIPLE=2,3,4,5,10,20
BONUS_CLOVER_MULTIPLE_PROBABILITY=40,28,16,10,5,1

BONUS_JP_MULTIPLE=10,25,100,5000
BONUS_JP_TYPE_PROBABILITY=80,25,8,1
```

档位值与权重按相同下标对应。共用 `[GENERAL]` 的类型、金币、四叶草、JP 权重总和分别为1088、7299、100、114。均为相对权重，不能固定除以10000，也不能要求总和为10000。JP 四档依次为 MINI、MINOR、MAJOR、GRAND，所有现有档位继续保留正权重。

### 对奖励期望的影响

下表为已经抽中该类型后的条件平均值，不是单次 Spin 的整体 RTP。

| 项目 | 当前共用 `[GENERAL]` 加权平均值 | 旧版工具等概率平均值 |
| --- | ---: | ---: |
| 金币倍数 | 4.516646x | 65.713333x |
| 四叶草乘数 | 3.48 | 7.333333 |
| JP 奖励倍数 | 63.377193x | 1283.75x |

计算方法为 `Σ(档位值 × 档位权重) / Σ档位权重`。旧版金币等概率平均值相对共用 `[GENERAL]` 放大约14.55倍；四叶草和 JP 分别约2.11倍、20.26倍。

Grand 在 JP 内的概率应为 `1/114≈0.877193%`，旧工具为25%，提高28.5倍。500倍金币在共用 `[GENERAL]` 金币内的概率为 `3/7299≈0.0411015%`，旧工具却为 `1/15≈6.666667%`。

四叶草和聚宝盆会进一步作用于金币奖励，因此上述条件均值不能直接作为整体 RTP 的换算系数，也不能将三项放大倍数直接相乘。

### 实现要求

先计算 `TotalWeight`，在 `[0, TotalWeight)` 内均匀生成整数 `Hit`，累加权重并返回第一个满足 `Hit < CumulativeWeight` 的下标：

```text
PickWeightedIndex(Weights):
    TotalWeight = Sum(Weights)
    Hit = UniformInteger(0, TotalWeight - 1)
    CumulativeWeight = 0
    For Index From 0 To Length(Weights) - 1:
        CumulativeWeight += Weights[Index]
        If Hit < CumulativeWeight:
            Return Index
```

- 档位值与权重数组均从配置读取，数组长度必须一致。当前为金币15档、四叶草6档、JP四档；金币和四叶草的档数按合法配置读取，JP 固定四档。
- 所有 GROUP/TYPE 的 Base、Free 和重翻只使用 `[GENERAL]` 参数，不读取数字节覆盖。切换 TYPE 不改变 Bonus 奖励分布；轴带与特殊图标生成概率仍按 TYPE 使用各自配置。
- 类型下标固定为 coin、clover、pot、jackpot，`BONUS_SYMBOL_TYPE` 名称列表缺失、注释或改写均不改变此映射。
- 允许0权重，0权重档位永不命中；空数组、负权重、总权重为0或数组长度不匹配均明确报错。
- 金币、四叶草、JP 的档位值必须为正。配置缺失或非法时不得静默改成等概率。
- 初次生成和每次重翻都必须使用对应档位权重。
- 权重累计使用足够位宽并检查溢出；不能用随机数对档位数量取模或使用 `& 3` 替代加权抽取。

### 验收条件

| 用例 | 输入或操作 | 期望 |
| --- | --- | --- |
| 累计权重边界 | `Weights=[1,3,6]`，依次固定 `Hit=0,1,3,4,9` | 下标依次为0、1、1、2、2 |
| 零权重 | `Weights=[0,3,0,7]`，遍历 `Hit=0...9` | 下标0、2永不命中；0至2返回1，3至9返回3 |
| 金币单档 | 仅0.2x档权重为正，再改成仅500x档为正 | 分别始终命中0.2x、500x |
| 四叶草单档 | 仅2倍档权重为正 | 始终命中2倍 |
| JP 单档 | 仅 MINI 权重为正，再改成仅 GRAND 为正 | 分别始终命中10x、5000x |
| 重翻抽样 | 对重翻结果重复单档测试 | 重翻也严格遵守档位权重 |
| 配置异常 | 空数组、长度不匹配、负权重、全0权重 | 明确报错，不启动错误的抽样配置 |
| 所有 GROUP/TYPE 共用 | 按 TYPE 0 → 4 → 8 → 12 → 17 → 0 连续执行 | Bonus 始终使用同一套 `[GENERAL]` 参数 |
| 数字节不生效 | `[GENERAL]` 合法，附加与其冲突的数字节参数 | 数字节不参与 Bonus 类型或档位抽样 |
| 固定类型顺序 | 缺失、注释或改写 `BONUS_SYMBOL_TYPE` | 权重下标始终对应 coin、clover、pot、jackpot |
| 独立分布抽样 | 分别统计金币、四叶草、JP 各档命中频率 | 接近各档权重占比；JP 内 Grand 接近0.877193%，不能接近25% |

## P0 金币字段与单位对齐

### 问题与修改目标

当前 Python 读取 `[GENERAL]` 的 `BONUS_COIN_MULTIPLE`，其中0.2表示0.2倍下注。旧版工具只读取旧字段 `BONUS_COIN_MULTIPLE_X1000`，缺失时回退到内置15档，导致当前金币档位配置不生效。

最新版 `ReadBonusConf` 已在 `Yngg_GameConf.cpp:196`（地址 `0x40c948`）读取 `BONUS_COIN_MULTIPLE`，调用 `ParseCsvMulX1000` 转为内部定点值，结算时再除以1000，已修复主字段读取问题。最初问题场景中的内置默认值恰好等于当前15个金币倍数值乘1000，旧版结算也除以1000，没有发现千倍单位错误；当时 RTP 大幅偏高的主要放大点仍是前一项的权重失效。

修改位置为 `Yngg_GameConf::ReadBonusConf` 的金币档位读取，以及 `RollGoldCell` 中对应的取值与金额换算。Python 对应实现为 `_load_bonus_config`、`generate_golden_round`、`resolve_golden_feature`。

### 实现要求

- 从所有 GROUP/TYPE 共用的 `[GENERAL]` 支持并优先读取 `BONUS_COIN_MULTIPLE`，准确保留0.2、0.5等小数倍数。
- 内部可继续用千倍定点数存储：0.2存200、0.5存500、500存500000。按实际倍数结算，不能将小数截断为0，也不能遗漏或重复除以1000。
- 金币档位与 `BONUS_COIN_MULTIPLE_PROBABILITY` 按下标对应；改变存储单位不能改变权重抽样。
- 若保留旧字段兼容，仅在当前字段缺失时才读取 `BONUS_COIN_MULTIPLE_X1000` 并换算。当前字段存在但非法时直接报错，不回退；两者均缺失时也报错。
- 金额使用足够位宽并检查溢出，整轮最终倍数合计乘下注的结算及舍入结果与当前 Python 一致。

### 验收条件

以 `BaseBet=100000` 验收单个金币：

| 档位 | 千倍定点存储值 | 应付金额 |
| --- | ---: | ---: |
| 0.2x | 200 | 20000 |
| 0.5x | 500 | 50000 |
| 500x | 500000 | 50000000 |

同时配置两个字段且设置不同的合法档位值，确认当前 `BONUS_COIN_MULTIPLE` 优先；仅有旧字段时确认正确换算。当前字段非法或两个字段均缺失时，必须明确报错。

重新编译后核对实际加载的金币档位、三个档位权重数组及上述验收结果，确认配置已进入实际抽样和结算路径。
