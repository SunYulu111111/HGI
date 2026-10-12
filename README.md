# HGI Math

HGI Math 是一个 Slots 数学逻辑与仿真项目。仓库核心在 `ThemeMath/`：通用模块负责读取配置、生成牌面、计算 Ways / Lines / Count 玩法收益；各主题目录只保留本主题的配置、特色逻辑和仿真入口。

## 项目结构

```text
.
|-- README.md
|-- test.py
`-- ThemeMath/
    |-- slots_math.py          # 通用基础逻辑：SlotsGame / WaysGame / LinesGame / CountGame
    |-- slots_simulation.py    # 通用仿真状态统计与报表输出
    |-- symbol_count.py        # 统计轴带 symbol 数量并写回配置备注
    |-- theme.json             # 轴带召回数据示例
    |-- model_waysgame/        # Ways 玩法模板
    |-- model_linesgame/       # Lines 玩法模板
    |-- model_countgame/       # Count 玩法模板
    |-- mahj3/                 # Ways：麻将主题（消除补牌 / 金色 symbol）
    |-- mjwl/                  # Ways：有效格裁剪 / 金色变 Wild
    |-- rzcs/                  # Lines：第三列分裂 / Free 与 Super Free
    |-- cjyx/                  # Lines：超级英雄玩法介绍与数值逻辑草稿
    |-- kldg/                  # Ways：恐龙帝国数学入口、仿真与配置
    |-- yngg/                  # Count：Cluster 消除 / 金色玩法
    `-- xml/                   # 独立水果机轮盘玩法（不继承上述三类）
```

常见主题目录约定：

| 文件 / 目录 | 说明 |
| --- | --- |
| `theme_math.py` | 主题数学入口，通常定义 `ThemeMath` |
| `simulation.py` | 主题仿真入口 |
| `game_config.conf` 或 `special/*_game_config.conf` | 基础数学配置 |
| `reel_config/` | 普通盘轴带 |
| `free_reel_config/` | 免费盘轴带 |
| `general_config/`、`special/`、`special_config/` | 主题相关配置 |
| `LOGIC.md` | 主题玩法逻辑说明 |
| `PARAMETERS.md` | 参数与实现对应关系（如 `yngg`） |
| `test_theme_math.py` | 主题单元测试（如 `yngg`、`xml`） |

## 主题一览

| 目录 | 基类 / 类型 | 要点 |
| --- | --- | --- |
| `model_waysgame` | `WaysGame` | Ways 模板，可复制新建主题 |
| `model_linesgame` | `LinesGame` | Lines 模板，可复制新建主题 |
| `model_countgame` | `CountGame` | Count 模板，可复制新建主题 |
| `mahj3` | `WaysGame` | 消除补牌、金色 symbol、级联倍数 |
| `mjwl` | `WaysGame` | 5×6 有效格裁剪、金色 symbol 变 Wild |
| `rzcs` | `LinesGame` | 押注解锁第三列分裂、Free / Super Free |
| `cjyx` | Lines 玩法文档 | 5×5、19 线、Wild 延展与乘倍、超级免费列激活；[项目文档](ThemeMath/cjyx/README.md) |
| `kldg` | `WaysGame` | 六列 Megaways、银框升级、连消倍数与免费游戏；[项目文档](ThemeMath/kldg/README.md) |
| `yngg` | `CountGame` | 6×5 Cluster、Scatter / Super Scatter、金色玩法 |
| `xml` | 独立实现 | 多 symbol 下注的轮盘水果机 + Bonus / 翻倍 |

## 环境要求

项目主要使用 Python 标准库，建议 Python 3.10 或更高版本。

```bash
python --version
```

若后续主题引入第三方依赖，请补充依赖文件并更新本 README 的安装说明。

## 快速开始

在仓库根目录运行主题仿真：

```bash
# Lines 模板
python ThemeMath/model_linesgame/simulation.py --spins 100000 --index 0 --general 1

# yngg（Count / Cluster）
python ThemeMath/yngg/simulation.py --spins 100000 --base-bet 100000 --index 0 --general-index 1

# mjwl（Ways）
python ThemeMath/mjwl/simulation.py --spins 100000

# rzcs（Lines）
python ThemeMath/rzcs/simulation.py --spins 100000

# xml（水果机）
python ThemeMath/xml/simulation.py --spins 100000
```

运行单元测试：

```bash
python -m unittest ThemeMath.yngg.test_theme_math
python -m unittest ThemeMath.xml.test_theme_math
```

统计并更新某个主题的轴带 symbol 数量：

```bash
python ThemeMath/symbol_count.py --root ThemeMath/rzcs
```

只检查不写回：

```bash
python ThemeMath/symbol_count.py --root ThemeMath/rzcs --dry-run
```

## 新主题 / 新任务目录约定

新主题或新任务建议放在 `ThemeMath/<new_folder>/` 下独立进行，避免直接混入已有主题目录。

推荐流程：

1. 按玩法类型复制模板：`model_waysgame/`、`model_linesgame/` 或 `model_countgame/`。
2. 重命名为新目录，例如 `ThemeMath/new_theme/`。
3. 替换或补齐 `game_config.conf`、`reel_config/`、`free_reel_config/` 等配置。
4. 在新目录内维护 `theme_math.py`、`simulation.py` 和必要的 `LOGIC.md`。
5. 大规模仿真输出（如 `simulate_result.csv`）建议单独保存，提交前确认是否纳入版本库。

非标准玩法（类似 `xml`）可不继承 Ways / Lines / Count，但仍建议沿用同一目录约定与仿真报表字段。

## 核心模块说明

### `ThemeMath/slots_math.py`

提供通用基础类和玩法基类：

- `SlotsGame`：读取主题配置、加载轴带、随机生成牌面，并维护停轴状态（供消除补牌使用）。
- `WaysGame`：基于 ways 规则计算中奖（`LINE_MODE=1` 或 `3`）。
- `LinesGame`：基于固定线规则计算中奖（`LINE_MODE=2` 或 `3`）。
- `CountGame`：基于 symbol 数量 / Cluster 规则计算中奖（`LINE_MODE=4`）。

主题入口通常继承其中一个玩法类，并在本目录实现普通盘、免费盘、特殊 symbol、消除补牌等特色功能。

### `ThemeMath/slots_simulation.py`

提供仿真统计工具，统一维护 RTP、Hit 率、Free 触发、倍数区间等报表字段，供各主题 `simulation.py` 复用。

### `ThemeMath/symbol_count.py`

扫描主题的 `reel_config/`、`free_reel_config/`，统计 `NORMAL_ROLL_*` / `SP_ROLL_*` 中各 symbol 出现次数，并可写回配置备注。

## 配置注意事项

- `GENERAL_n` 表示不同权重或轴带分组；仿真时通过 `--general`、`--general-index` 或 `--generals` 选择。
- `reel_config` 中的 `BASE_RATE` 顺序通常为：普通盘、特殊盘、固定结果、零概率结果。
- 金额或赔率需与 `base_bet`、`BET_UNIT`（默认 `10000`）保持一致。
- 修改轴带后建议先跑 `symbol_count.py --dry-run` 检查，再决定是否写回。
- 各主题详细规则见对应目录下的 `LOGIC.md`；`yngg` 另有 `PARAMETERS.md` 说明参数与代码对应关系。

## 字段命名规则

本规则适用于 HGI 目录及所有子目录中的新增内容，与根目录 `AGENTS.md` 保持一致。

- 新增字段统一使用大驼峰命名法（PascalCase）：每个单词首字母大写，不使用下划线或连字符，例如 `BaseBet`、`FreeSpinCount`、`TotalWin`、`BonusJpMultiple`。
- 适用范围包括配置字段、JSON / 字典键、数据结构属性、接口输入输出字段，以及文档、示例和生成脚本中的对应字段。
- 同一字段的定义、读写引用、测试和文档必须使用一致名称。
- 现有字段不自动批量改名；需要迁移时，再同步修改引用和兼容逻辑。下文的 `ITEM_PRIZES_N`、`LINE_MODE`、`lable_user_*` 等是已有服务器协议字段，保留原名，不作为新增字段的命名示例。

## 服务器配置字段规则（视频整理）

来源：`录屏2026-09-17 17.01.18.mov` 中的《HGI_SLOT_服务器配置说明》，画面所示文档最近修订于 2026-08-19。以下整理录屏中可核对的字段含义、填写规则和约束；视频末尾未展开的平台及活动配置不补写字段细节。

本节描述服务器配置协议，不代表当前 Python 仿真已实现全部协议。主题落地时还需核对相应读取、算奖与控制逻辑。表中的 `{name}`、`{type}`、`N` 是原协议文件名或字段名的占位符。

### 配置文件与作用（00:00–00:24）

| 配置文件 | 作用 |
| --- | --- |
| `base_game_name.conf` | 游戏名称 |
| `game_server.conf` | 全局进入限制、公告、回放和任务开关 |
| `{name}_game_server.conf` | 押注、AutoSpin、大奖弹窗、核心玩法参数及按 TYPE 划分的参数 |
| `{name}_game_config.conf` | 盘面规格、图标功能与赔付规则 |
| `{name}_rand_main.conf` / `{name}_free_rand_main.conf` | 主游戏 / 免费游戏转轴规格、物件数、GENERAL 套数及版本 |
| `{name}_rand_ex_{type}.conf` / `{name}_free_rand_ex_{type}.conf` | 指定 TYPE 的主游戏 / 免费游戏转轴和固定结果 |
| `{name}_control.conf` | 根据玩家状态和条件选择 GROUP |
| `slot_control_group.conf` | GROUP 内的 TYPE 构成、权重及砍分阈值 |
| `slot_prop_config.conf` | 免费游戏道具卡、SPIN 卡属性 |
| `{name}_bonus.conf` | 涉及 Jackpot Bonus 时使用的可选配置 |

### 押注、赔率与基础交互字段（00:34–00:52）

后台房间底分统一为 `10000`。`{name}_game_server.conf` 的 `[System Base Info]` 中，押注相关数组按同一押注档位对应。

| 字段 | 填写规则 |
| --- | --- |
| `BetPerReel` | 现行常规机台各档均为 `1`；多福多财等标签升级玩法可另行配置。不能仅因为是 Line Pay 就填写线数 |
| `BetScopes` | 押注档位系数，常规为 `10,20,50,100,200,500,1000,2000,2500`，对应 100K 至 25M |
| `BetUnLockRegTime` | 注册时间门槛，在该时间之后注册的玩家使用这套押注解锁配置 |
| `BetUnLockLevel` | 各押注档位的玩家等级门槛；满足对应 VIP 门槛时不再判断玩家等级 |
| `BetUnLockVip` | 各押注档位的 VIP 等级门槛 |
| `AutoSpinTimes` | 视频示例为 `10,100,500,-1,-2`；录屏未解释两个负值的具体含义 |
| `BigWinGrade` | 大奖分档配置，视频示例为 `10,20,50` |
| `NewBigWinGrade` | 新版大奖分档配置，视频示例为 `5,10,20,50,100,500` |

押注与基础赔付换算如下，其中 `BetPerReel`、`BetScopes` 均取当前档位的值，`ITEM_PRIZES_N` 取图标 N 对应中奖数量的奖值：

```text
押注值 = 房间底分 × BetPerReel × BetScopes
基础中奖分 = 对应 ITEM_PRIZES_N 奖值 × BetScopes
相对总押注的奖励倍数 = 对应 ITEM_PRIZES_N 奖值 ÷ (房间底分 × BetPerReel)
```

常规配置 `BetPerReel=1`、`PRIZE_RATE=1` 时，奖表填写值为“相对总押注的奖励倍数 × 10000”。例如图标 2 的 5 连奖励为总押注的 5 倍，则 `ITEM_PRIZES_2` 第 5 项填写 `50000`；在 `BetScopes=10` 时，押注为 `100000`，该项基础中奖分为 `500000`。

以上是单个奖表结果的基础换算，Ways 数量、多条中奖线、玩法倍数等按主题结算规则继续计算。旧 Line Pay 文档可能以单线押注描述赔率，填写前须换算到上述总押注口径。特殊押注通常通过缩放 `BetScopes` 实现；若各档 `BetPerReel` 不同，同一奖表相对总押注的倍数也会不同。

### 赔付与图标字段（00:52–01:18）

`{name}_game_config.conf` 的必要内容包括版本、机台基本信息及赔付配置；Pay Line、无效格子和特殊机制按玩法补充。Scatter 次数或金额奖励若由玩法逻辑实现，可省略相应奖励字段。

| 字段 | 类型 / 对应关系 | 填写规则 |
| --- | --- | --- |
| `VERSION` | 整数 | 更新配置时版本号加 1 |
| `COL_COUNT` | 整数 | 盘面列数 |
| `ROW_COUNT` | 整数 | 最长一列的格子数；异形盘取最大值，并包含可见但不参与中奖的格子 |
| `ITEM_COUNT` | 整数 | 物件数量；按 ID 索引的配置须覆盖所使用的物件 ID |
| `PRIZE_RATE` | 整数 | 默认 `1`；视频说明实际奖励需除以此值，常规配置不修改 |
| `LINE_MODE` | 整数 | `1`：左边连列 / Ways；`2`：左边连线 / Lines；`3`：两边连线；`4`：全盘图标个数；`5`：相邻图标个数 / Cluster |
| `USE_WILDS` | 按物件 ID 对应的数组 | `0` 不可被 Wild 替换，`1` 可替换；Wild 自身对应项不可设为可替换 |
| `BASE_NUMS` | 按物件 ID 对应的数组 | 对应图标最低中奖数量 / 连线数量 |
| `ITEM_PRIZES_N` | 图标 N 的奖表数组 | Ways / Lines 依次对应 1 连至列数；按图标数量赔付时依次对应 1 个至盘面格子数。不中奖项填 `0`，不能省去前置项 |
| `BOTH_SIDES` | 按物件 ID 对应的数组 | `0` 左边连线，`1` 双边连线；视频注明仅 `LINE_MODE=2` 时生效 |
| `FULL_WILD_LINE` | 整数 | `0` 无纯 Wild 中奖，`1` 有；第一列允许出现 Wild 时填 `1`，Wild 开头形成多种赔付可能时取较大奖励 |
| `RULE_COUNT` | 整数 | 中奖线数量 |
| `LINE_RULES_N` | 每列一个格子编号的数组 | 第 N 条中奖线的位置；线编号从 `0` 开始，条数与 `RULE_COUNT` 一致 |

**当前仿真实现的差异：** `ThemeMath/slots_math.py` 的通用 `CountGame` 只接受 `LINE_MODE=4`；`yngg` 的 Cluster 由主题自身逻辑计算。因此不能只把配置改为视频中的 `LINE_MODE=5`，就认为通用仿真已支持 Cluster。

### 格子编号、Scatter 与无效格（00:52–01:10）

格子从 `0` 开始编号，按列遍历：先完成最左一列，再向右移动。视频修订记录规定《皮纳塔》之后的机台列内从下到上；之前的机台列内从上到下。`LINE_RULES_N` 与无效格掩码必须采用该机台同一套编号方式。

以新规则的 5 列 × 3 行盘面为例，屏幕上的编号为：

```text
上排： 2   5   8  11  14
中排： 1   4   7  10  13
下排： 0   3   6   9  12
```

因此中排直线为 `1,4,7,10,13`，上排直线为 `2,5,8,11,14`，下排直线为 `0,3,6,9,12`。

| 字段 | 类型 / 对应关系 | 填写规则 |
| --- | --- | --- |
| `SCATTER_MODE` | 整数 | 视频表格默认填 `1`；具体计数方式需结合玩法核对，不能仅凭这个默认值推断 |
| `SCATTER_ID` | 整数或数组 | Scatter 的图标 ID，常见为 `0`；存在多种 Scatter ID 时可使用数组 |
| `SCATTER_COLS` | 每列一项 | 从第一列开始，`0` 不检查该列，`1` 检查该列 |
| `SCATTER_SERIAL` | 整数 | `0` 不要求连续列；`1` 要求从第一列起连续出现 |
| `SCATTER_MULTIPLES` | 长度为盘面格子数的数组 | 依次对应 1、2、3…个 Scatter 的免费次数；视频默认全 `0`，次数由玩法逻辑实现 |
| `SCATTER_PRIZES` | 长度为盘面格子数的数组 | 依次对应各 Scatter 数量的额外奖励；视频口径为相对“房间底分 × BetPerReel”的倍数，不直接套用 `ITEM_PRIZES_N` 的奖值单位 |
| `GRID_DISABLES` | 每格一项 | 主游戏无效格掩码，`0` 有效、`1` 无效 |
| `GRID_DISABLES_FREE` | 每格一项 | 免费游戏无效格掩码，`0` 有效、`1` 无效 |

### 转轴规格、GENERAL 与固定盘（01:18–01:26）

`{name}_rand_main.conf` 和 `{name}_free_rand_main.conf` 描述转轴规格，其行列数须与对应 `rand_ex` 文件一致。异形屏按最大规格填写，例如每列高度为 `1-3-5-3-1` 时使用 5 行 × 5 列。

包含水平转轴的玩法需要区分“转轴规格”和“中奖盘面规格”：视频中的 Aztec 例子在转轴配置中为 7 列 × 5 行，在 `game_config` 中为 6 列 × 6 行，水平转轴作为独立 ROLL 配置。

| 字段 / 配置段 | 填写规则 |
| --- | --- |
| `VERSION` | 规格配置版本；修改关联 `rand_ex` 内容后，也必须增加对应主游戏 / 免费游戏 `rand_main` 的版本号，否则服务器无法重新加载 |
| `COL_COUNT` / `ROW_COUNT` | 转轴列数 / 行数，按该文件职责填写，不强制等于中奖盘面规格 |
| `ITEM_COUNT` | 转轴使用的最大物件 ID 加 1 |
| `ITEM_COM_COUNT` | 对应游戏状态下 `[GENERAL_N]` 的套数 |
| `[GENERAL_N]` | 每套物件组合包含正常轴、特殊轴、固定盘和零盘；通过增加 `[GENERAL_2]` 等扩展 |
| `BASE_RATE` | 四项权重依次为正常轴、特殊轴、固定盘、零盘 |
| `NORMAL_ROLL_N` / `SP_ROLL_N` | 第 N 列正常 / 特殊循环轴带，通过随机截取连续图标产生结果；列编号从 `1` 开始 |
| `FIX_RESULT_N` | 固定结果，通常配置为不中奖盘面，用于底层砍分 |
| `ZERO_RESULT_N` | 另一类固定结果，可用于触发免费或低倍中奖等；“零盘”不表示必须零奖励 |
| `FIX_NUM` / `ZERO_NUM` | 启用的固定结果数量；选中该类结果后，从对应前 n 条中等概率抽取 |
| `FIX_DISORDER` / `ZERO_DISORDER` | `1` 开启每列内部图标顺序随机打乱；不是交换整列的位置 |

固定结果是逐格指定的完整盘面，不经过滚轮截取。视频中的结果数组从最左列开始，列内从下到上，再向右排列。例如 `1,2,3,4,5,6,7,8,9` 在 3×3 盘面上显示为上排 `3,6,9`、中排 `2,5,8`、下排 `1,4,7`。固定结果发生消除后，服务器默认使用当前 GENERAL 的 `NORMAL_ROLL` 随机位置补牌。

视频给出的服务器配置上限：固定盘和零盘各最多 200 条；正常轴及特殊轴的单条滚轮字符串最长 500，且每条滚轮最多 200 个物件。两项滚轮长度限制需同时满足。

本仓库的 yngg 轴带采用更严格的发布要求：`NORMAL_ROLL_N` 和 `SP_ROLL_N` 的每条轴值按 UTF-8 编码后必须**小于 400 字节**（不含字段名和 `=`），同时仍须满足每条最多 200 个物件。普通游戏和免费游戏的所有 TYPE 均适用。

### TYPE、GROUP 与控制字段（00:06–00:12、01:26–01:38）

TYPE 是一套完整数值的最小单位，关联同 TYPE 的主游戏轴带、免费游戏轴带，以及 `{name}_game_server.conf` 中相应数字配置段。例如 TYPE 4 对应 `rand_ex_4`、`free_rand_ex_4` 和 `[4]`。

一次付费 SPIN 的选择顺序为：玩家状态 → `{name}_control.conf` 选择 GROUP → `slot_control_group.conf` 按权重抽取 TYPE。选中的 TYPE 贯穿该次 SPIN 的全部结算，包括由其触发的免费游戏、Respin 和其他 Feature，中途不切换。GROUP 编号与使用场景固定对应，组内 TYPE 构成可按数值设计调整；GENERAL 则是 TYPE 对应转轴文件内部的物件组合，不与前两者混用。

`{name}_control.conf` 的 `[CONTROL_N]` 主要字段如下；旧协议中的 `lable` 拼写保留：

| 字段 | 填写规则 |
| --- | --- |
| `version` | 控制配置版本号 |
| `lable_user_percent` | 进入该控制判断的概率，万分比 |
| `lable_user_value` | 玩家标签值，最多 20 个 |
| `lable_user_bet_money` | 押注金币档位，是其他按档位配置项的对应基准 |
| `lable_user_day_balance` | 各押注档位的日净分区间 |
| `lable_user_user_control_buff` | 各押注档位的充值贡献度区间 |
| `lable_user_user_control_buff_deduct` | 控制触发后整局扣除的贡献度；视频示例使用负数，不能直接改成正数 |
| `lable_user_day_avg_bet_coefficient` | 当前押注 / 日平均押注，万分比区间；`0,0` 表示不启用 |
| `lable_user_day_rtp` | 日总赢分 / 日总玩分，万分比区间；`0,0` 表示不启用 |
| `lable_user_day_control_count` | 各档位的日控制次数，视频注明 `1–99` 有效 |
| `lable_user_day_control_index` | 各档位的日控制索引，视频注明 `1–5` 有效 |
| `lable_user_control_rate` | 各档位的控制概率，万分比，`10000` 为 100% |
| `lable_user_control_group` | 各档位选择的 GROUP；视频示例中贡献度放分对应 `8` |

按押注档位配置的数组长度和顺序必须对应 `lable_user_bet_money`；区间以逗号分隔上下界、以竖线分隔档位。视频没有统一定义所有区间的 `0,0` 含义，不能把上述两个字段的停用规则推广到所有区间字段。

`slot_control_group.conf` 的字段规则：

| 字段 / 配置段 | 填写规则 |
| --- | --- |
| `[CONTROL_GROUP_N]` | GROUP N 的数值组合 |
| `lable_user_control_group_rate` | 组内各控制值的相对权重，最多 20 项 |
| `lable_user_control_group_value` | 与权重一一对应的控制值，最多 20 项；按旧协议 `control_type * 100 + control_num` 编码，不能直接当作 GROUP 编号 |
| `control_group_cut_multiple` | 按 GROUP 编号从 `0` 起排列的单次 Spin 砍分倍数，`0` 不砍分 |
| `control_group_free_cut_multiple` | 按 GROUP 编号从 `0` 起排列的免费游戏单次 Spin 砍分倍数，`0` 不砍分 |

例如视频 GROUP 8 的权重为 `6000,4000`，控制值为 `401,501`，表示按 60% / 40% 抽取两个编码后的控制值。不能把 `401`、`501` 原样填成转轴文件的 TYPE 后缀。

视频所列 GROUP 场景及数值要求如下，作为该版服务器规范记录；不是当前仓库仿真结果：

| GROUP | 场景 | 返奖率 | 游戏范围 | 砍分倍数 | 新机台制作要求 |
| --- | --- | --- | --- | --- | --- |
| 0 | 正常 | 98.3%–98.7% | Base、Feature | 5000 | 是 |
| 1 | 机刷 | <98.5%，低于正常值 | Base，不触发免费 | 100 | 否 |
| 4 | VIP2+ | 98.3%–98.8% | Base、Feature | 12000 | 是 |
| 7 | 小押注放分 | 2000% | Base | 50 | 否 |
| 8 | 贡献度放分 | 5000% | Feature | 1000 | 是 |
| 9 | 贡献度高倍放分 | 50000% | Feature | 1000 | 否 |
| 12 | 强控机刷 | 40% | Base | 20 | 是；单次 SPIN 中奖上限不超过 20 倍 |
| 13 / 15 | Special Bet 1 / 3 | 98.3%–98.7% | Base、Feature | 12000 | 否 |
| 14 / 16 | Special Bet 2 / 4 | 98.3%–98.8% | Base、Feature | 12000 | 否 |
| 17 | 免费道具卡 | 5000% | Feature | 1000 | 是 |
| 18 | Plus 免费道具卡 | 9850% | Feature | 1000 | 视情况，视频绿色标注为 SLOT MASTER 相关 |

免费道具卡用于特殊押注机台时，需要按道具卡价值换算倍数。视频中的 VVIP 额外贡献度放分也使用 GROUP 8。

### 全局开关与道具卡字段（00:28–00:34、01:38–01:44）

全局 `game_server.conf` 使用 `[Game_Info]`，与主题文件中的 `[Game Info]` 不是同一配置段。

| 字段 | 含义与视频规则 |
| --- | --- |
| `limit_lv` | 游戏进入等级；开放首周 VIP BETA 为 `5,5`，之后填写常态等级，如 `7,7` |
| `limit_reg_time` | 注册时间门槛，晚于配置时间使用新限制等级 |
| `limit_vip` | VIP 进入限制 |
| `limit_login_type` | `-1` 全部，`0` PC，`1` Android，`2` iOS |
| `limit_send_bull_user_type` | 大奖公告用户限制；`-1` 不限，`0` 限制游客。视频要求测试服及正式开放为 `-1`，定向服测试为 `0` |
| `replay_open` | 回放开关：`0` 关闭、`1` 开启；关闭后中奖信息不上报、不上榜 |
| `replay_min_win_money` | 回放排行最低金币数，视频示例 `3000000000` |
| `replay_min_win_mul` | 回放排行最低倍数，视频示例 `999999` |
| `replay_min_version` | 回放最低功能版本，视频示例 `65` |
| `task_open` | 服务器任务开关，`0` 关、`1` 开，默认关 |
| `task_skip_label_value` | 不累计任务的标签值，默认 `0`，大于 `0` 时生效，对应 `account_shua_02` |
| `kick_time` | 长时间未操作的踢出时间，秒；示例 `180` |
| `game_gap_time` | 游戏间隔，毫秒；示例 `300` |
| `radius_num` | 多少局计费一次；示例 `1500` |
| `merge_log_num` | 类型相同时每多少局合并记录一次日志；示例 `1` |
| `day_play_game_num` | 日游戏局数的三段限制，前两段提示、最后一段禁止；示例 `18000,36000,72000` |
| `limit_login_lable_user_value` | 限制登录的数据库标签值，最多 20 个 |
| `limit_login_lable_user_percent` | 上述标签用户进入时提示维护的概率，万分比 |
| `daily_act_game_ver` | 最低活动版本号；视频示例 `8` 对应 2.29 |
| `enter_limit_prop_ids` | SLOT MASTER 机台的解锁道具 ID |
| `enter_limit_prop_time` | 解锁道具生效起止时间，两个时间用竖线分隔 |

`slot_prop_config.conf` 的 `[System Base Info]` 及 `[SLOT_PROP_INFO_N]` 规则：

| 字段 | 填写规则 |
| --- | --- |
| `VERSION` | 配置版本，变化后重新读取 |
| `OPEN_GAME_VER` | 开启该游戏功能的版本号，视频示例 `6` |
| `DAY_USE_MAX_NUM` | 日使用数量上限，不超过 `100000000`；视频示例 `99999` |
| `PROP_ID` / `GAME_ID` | 道具 ID / 所属游戏 ID，按实际机台和道具填写 |
| `PROP_TYPE` | `-2` 表示免费游戏卡 |
| `PROP_BUFF_1` | `PROP_TYPE=-2` 时表示押注值索引，不是押注金币金额 |
| `PROP_BUFF_2` | 道具卡品质 |
| `PROP_BUFF_3` / `PROP_BUFF_4` / `PROP_BUFF_5` | 预留数字，可不配置 |
| `PROP_BUFF_6` | 预留字符串，可不配置 |

免费道具卡及 SPIN 卡还涉及 `{name}_control.conf` 的 `[FREE_PROP_CONTROL]`、`[SPIN_PROP_CONTROL]`。录屏未完整展开这两段的具体字段，不据此推断 SPIN 卡类型编码或押注索引起点。

### 视频中需要辨别的说明

- 00:08 附近正文将砍分数组写成按 TYPE 排列，但 01:36 的字段注释明确写“每个 Group”。本节按后者记录为 GROUP 下标；与实际服务器对接时需核对读取实现。
- 00:30 的定向服回放一项写“开启”，示例却是 `replay_open=0`；同一视频代码注释明确 `0` 关闭、`1` 开启。本节保留开关含义，不把该处矛盾转成开启规则。
- `SCATTER_MODE=1` 在不同示例中分别出现“按列查找”和“全盘计数”注释，不能据此统一认定 Scatter 计数方式；按具体主题实现核对。
- 部分示例把相邻图标赔付编号误写为 `3`，字段说明表列为 `5`；本节采用字段说明表，并单独注明当前仿真的支持范围。
