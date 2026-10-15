# 恐龙世界 klsj

本项目位于 `ThemeMath/klsj` 目录，目录内机台文件和配置前缀统一使用 `klsj`。项目对应游戏 ID 353，展示名称为《恐龙世界》（Jurassic World）。

项目按 `model_waysgame` 的目录组织，包含数学入口、仿真入口、主游戏及免费游戏轴带、游戏配置、服务器配置、控制配置和通用配置。玩法规则依据用户提供的《恐龙世界》策划案 1.03 版整理；当前轴带、可变高度、高图标布局和边框权重仍是流程验证用临时样本。

## 文件入口

- [玩法介绍](klsj_玩法描述.md)：玩家可见的 Megaways、消除、边框、倍数和免费游戏规则。
- [数值逻辑](klsj_数值逻辑.md)：服务端处理顺序、赔付、边框状态、免费次数及配置参数。
- [数学入口](theme_math.py)：六列可变高度 Ways、边框升级、Wild 转换、Scatter 累计与免费次数。
- [仿真入口](simulation.py)：按付费 Spin 运行主游戏和免费游戏，输出结构化统计。
- [关键规则测试](test_theme_math.py)：覆盖赔付、Wild 去重与列限制、边框移动、Scatter 尺寸与累计、物理高度及消除倍数。

## 文档与注释写法

本机台的两份文档及中文注释按仓库[文档与中文注释写法](../../README.md#文档与中文注释写法)维护，后续机台使用同一写法：数值逻辑写处理流程和计算口径，玩法描述写玩家可见规则；文档直接给出最终文案，配置和代码仅保留必要备注，奖表、轴带及同类权重按组说明。

## 配置文件

- `special/klsj_game_config.conf`：六列 Ways 盘面、图标 ID、赔付表和 Scatter/Wild 协议配置。
- `special/klsj_game_server.conf`：物理列高、沿用 yjzr 字段名和逐列数组形式的高图标布局／消除补牌权重、银框出现率、银框转化权重、主游戏倍数上限、免费单手内倍数增量上限、每轮免费次数上限和免费奖励次数等数值参数。
- `reel_config/klsj_rand_main.conf`、`reel_config/klsj_rand_ex_0.conf`：主游戏轴带。
- `free_reel_config/klsj_free_rand_main.conf`、`free_reel_config/klsj_free_rand_ex_0.conf`：免费游戏轴带。
- `special/klsj_control.conf`：玩家控制分组的版本占位，当前没有已定义的玩家控制规则。
- `special/slot_prop_config.conf`：沿用 yjzr 的 `[System Base Info]` 道具元信息，当前没有已定义道具卡。
- `general_config/slot_activity.conf`：沿用 yjzr 的 `[Act_Info]` 活动启停段，掉落参数统一放在 `game_act_coin.conf` 的对应活动 ID 段。

当前临时轴带和权重用于检查流程，不代表正式 RTP 或上线配置。正式接入前需要替换主/免费轴带、物理列高权重、`base_height_weight_1`～`base_height_weight_6` / `free_height_weight_1`～`free_height_weight_6`、消除补牌布局权重、银框出现率及银框转化权重，并重新校验目标 RTP、免费游戏触发率和第 2～5 列 Wild 限制。已确认的倍数规则、免费次数规则和 9 档押注继续按本文执行。

## yjzr 字段对齐

参考：[截图对应的 yjzr 原始配置](/Users/sunyulu/Downloads/20261012-114625_26662/yjzr/a/yjzr_game_server.conf)。此次按用户指定沿用参考字段名，相关旧协议字段保留下划线；klsj 专属新增字段继续使用 PascalCase。

| 参数 | 当前服务器字段 |
|---|---|
| 主游戏初始 6 格布局 | `base_height_weight_1`～`base_height_weight_6` |
| 免费游戏初始 6 格布局 | `free_height_weight_1`～`free_height_weight_6` |
| 主游戏消除补牌 | `base_elim_height_weight_{Col}_{Height}` |
| 免费游戏消除补牌 | `free_elim_height_weight_{Col}_{Height}` |
| 主游戏最大消除次数 | `BaseMaxEliTimes` |
| 免费游戏最大消除次数 | `Free_Max_EliTimes` |
| 每轮免费次数上限 | `Free_Max_Times`（50），内部属性 `FreeMaxTimes` |

`Col` 为 1～6，对应 klsj 实际第 1～6 列；yjzr 的 1～3 对应其第 2～4 列，因为它只有这三列使用高图标。`Height` 为 2～6；1 格空缺固定补一个 1 格图标，不配置权重。各数组按照参考文件的固定模式顺序排列，抽中后随机打乱图标高度顺序。初始物理列高不足 6 格时，沿用现有逻辑读取同高度的补牌权重。

布局字段必须完整提供；缺项、错误索引、数组长度不符、负权重或全零权重均报错。配置不再读取旧的自定义布局字段和 `高度:权重|…` 格式。`ReelHeightWeights1`～`ReelHeightWeights6` 是 klsj 独有的物理列高配置，也改为逐列逗号数组；银框、倍数与免费次数继续使用 klsj 自身规则和参数。

`Free_Max_Times=50` 用于计算新 Scatter 的生成额度，使每轮初始奖励和追加次数合计不超过 50；Scatter 触发的奖励足额发放，已发放次数全部正常玩完。超额度 Scatter 候选从本次实际来源轴带的同列普通图标池按频次抽取，保留原高度并按普通规则抽银框。未启用独立 Wild 生成替换、免费赢额封顶及保底机制。参考原文件的 `free_elim_height_weight_2_2` 写了 9 个权重，与 2 格的两个布局不符；klsj 按两个布局校验。布局随机打乱会改变同一种拆分的图标位置，仿真需使用实际配置重新生成。

## 其他配置审核

已核对 klsj 的全部 26 个 `.conf` 文件，以 yjzr 同名文件为参照，保留字段大小写、旧协议拼写、所在段及数组形式；盘面数组长度按照 klsj 的六列、13 个图标和 36 格容器确定，通用活动数组保留既有定义。此次调整字段结构，原有奖表、轴带和控制权重数值保持不变。

| klsj 文件 | 对照结果与处理 |
|---|---|
| `special/klsj_game_config.conf` | 已有 `VERSION`、`COL_COUNT`、`ROW_COUNT`、`ITEM_COUNT`、`PRIZE_RATE`、`LINE_MODE`、`USE_WILDS`、`BASE_NUMS`、`ITEM_PRIZES_N`、Scatter 识别字段均同名。补齐 `BOTH_SIDES`（13 项）、`FULL_WILD_LINE`（标量）、`GRID_DISABLES`／`GRID_DISABLES_FREE`（各 36 项）；当前均为 0。 |
| `special/klsj_game_server.conf` | 系统段的 `AutoSpinTimes`、`NewBigWinGrade`、`BetPerReel`、`BetScopes`、`BetUnLockRegTime`、`BetUnLockLevel`、`BetUnLockVip` 同名；游戏段的 `version`、布局和消除次数字段已对齐。 |
| `reel_config/klsj_rand_main.conf`、`free_reel_config/klsj_free_rand_main.conf` | `[MAIN]` 和 `VERSION`、`COL_COUNT`、`ROW_COUNT`、`ITEM_COUNT`、`ITEM_COM_COUNT` 与 yjzr 一致。 |
| `reel_config/klsj_rand_ex_0.conf`、`free_reel_config/klsj_free_rand_ex_0.conf` | 删除 yjzr 没有的冗余 `[MAIN]`／`VERSION`，从 `[GENERAL_1]` 读取 `BASE_RATE`、`NORMAL_ROLL_N`、`SP_ROLL_N`、`FIX_NUM`、`FIX_DISORDER`、`FIX_RESULT_N`、`ZERO_NUM`、`ZERO_DISORDER`、`ZERO_RESULT_N`。第 6 列按同一字段格式扩展。 |
| `special/klsj_control.conf` | `[MAIN].version` 同名，当前没有 `[CONTROL_N]` 规则；未复制 yjzr 的玩家标签、控制概率和道具 ID。 |
| `special/slot_prop_config.conf` | 占位段改为 yjzr 的 `[System Base Info]`，明确 `VERSION`、`OPEN_GAME_VER`、`DAY_USE_MAX_NUM`。当前日使用上限为 0，且无 `[SLOT_PROP_INFO_N]` 定义。 |
| `special_config/base_game_name.conf` | `[base_game_name].game_name_0`～`game_name_3` 同名；保留恐龙世界的名称。 |
| `special_config/game_server.conf` | 登录限制、回放、任务等共有字段均同名、同段、同形式；保留 klsj 原值。 |
| `special_config/slot_control_group.conf` | `[MAIN].version`、`control_group_cut_multiple`、`control_group_free_cut_multiple` 与 `[CONTROL_GROUP_N]` 中的 `lable_user_control_group_rate`／`lable_user_control_group_value` 同名。klsj 现有组数和控制值保留。 |
| `general_config/base_bull.conf`、`base_comm.conf`、`base_level.conf` | 现有字段和段均与 yjzr 一致。 |
| `general_config/base_text.conf` | 现有 `[msg_text_type_N].msg_text_N` 与 yjzr 一致；yjzr 新增的 `msg_text_40` 未关联 klsj 已定义功能，未补入。 |
| `general_config/game_achievement.conf`、`game_get_level_exp.conf` | 字段和段均与 yjzr 一致。 |
| `general_config/game_act_coin.conf` | 活动 ID 段及各掉落字段与 yjzr 一致；保留 klsj 的 9 项押注数组。 |
| `general_config/game_activity.conf` | 所有现有段和字段同名；`all_start_act_info` 沿用 `活动ID,显示标记`，多项使用 `|`。yjzr 的空值表示没有条目，klsj 保留原有条目。 |
| `general_config/game_card.conf` | `[DROP_CONF]`、`[DROP_INFO_N]` 及字段同名；保留 klsj 原值。 |
| `general_config/slot_activity.conf` | `[Coin Info]` 改为 `[Act_Info]`，保留原有 `version`、`activity_id`、`if_start`、`start_time`、`end_time`。重复掉落参数统一读取 `game_act_coin.conf` 的 `[10010]`。未添加未定义的比赛活动。 |
| `general_config/slot_game_activity.conf`、`slot_game_activity2.conf` | 已有段和字段同名；后者与参考文件一样没有字段。 |
| `general_config/spe_user_event.conf`、`spreader_task.conf` | 所有现有段和字段同名。 |
| `general_config/yb_double.conf` | yjzr 目录中没有对应文件，保留既有字段和数值。 |

`slot_activity.conf` 的旧掉落字段与已有 `[10010]` 重复，其中旧的 `activity_coin_drop_min_bet=0` 与 `[10010]` 的 `10000000` 不一致；此次采用 yjzr 的单一配置位置，保留 `[10010]` 原有值。两个旧的强发时间字段 `max_limit_time0`、`max_limit_time` 均为 0，且 yjzr 在该活动段没有对应项，已移除停用占位。活动 `if_start=0` 保持关闭。

数学入口会校验新增的基础协议开关及数组长度。当前 klsj 结算器只支持 `LINE_MODE=1`、`BOTH_SIDES=0`、`FULL_WILD_LINE=0` 和全 0 固定屏蔽数组；修改为不支持的模式会报错，避免配置被静默忽略。最大消除次数的内部属性分别为 `BaseMaxEliTimes`、`FreeMaxEliTimes`，服务器读取名分别为 `BaseMaxEliTimes`、`Free_Max_EliTimes`。

## 保留字段与未对应机制

| klsj 字段／配置 | 保留依据 |
|---|---|
| `ReelHeightWeights1`～`ReelHeightWeights6` | 物理列高 2～6 的权重；yjzr 的 `base_height_weight_N`／`free_height_weight_N` 是 6 格内的图标拆分权重，两者同时使用。 |
| `SilverFrameChance`、`SilverUpgradeSymbolWeights` | 银框生成与银框转金框的机制；yjzr 的 `base_wild_transfer`／`base_elim_wild_transfer` 及免费对应项直接替换 1 格图标为 Wild，含义不同。 |
| `MainMultiplierCap` | 主游戏连消倍数上限；yjzr 的 `BaseMaxEliTimes` 是消除轮数上限。 |
| `FreeSpinMultiplierIncrementCap` | 免费单手内相对起始倍数的增量上限，当前为 4；没有 yjzr 同义字段，名称使用 PascalCase。免费手数由 `Free_Max_Times` 限制，倍数不另设独立上限。 |
| `FreeStartMultiplier`、`FreeEndMultiplier` | 免费接口／结果的 PascalCase 字段，分别记录本手起始倍数和最终实际结算倍数；首手起始为 1，下一手为上一手最终倍数加 1。`FreeSpinNumber` 记录本轮手数并参与 Scatter 额度计算，不决定起始倍数。 |
| `FreeSpinsRemaining` | 免费调用时传入扣除本手后的已发放待玩次数，本手新 Scatter 生成额度为 `FreeMaxTimes-FreeSpinNumber-FreeSpinsRemaining`。未传 `FreeSpinNumber` 时自动推进手数；新付费手将手数和免费起始倍数重置为 1。 |
| `FreeTriggerScatterCount`、`BaseFreeSpins`、`MainExtraFreeSpinsPerScatter`、`FreeExtraSpinsPerScatter` | klsj 的跨消除 Scatter 累计和免费奖励规则；yjzr 的 `base_scatter_num`／`free_scatter_num` 是随机生成数量分布，`Free_Max_Times` 是免费次数封顶。 |
| `WILD_ID`、`SCATTER_MULTIPLES`、`SCATTER_PRIZES`、`ITEM_PRIZES_10`～`ITEM_PRIZES_12` | 通用数学入口的既有图标协议扩展；Scatter 奖励数组当前为 0，由 klsj 跨消除逻辑发放次数。 |
| `BigWinGrade`、`BaseScore` | 既有大奖展示分档和底分；yjzr 只有 `NewBigWinGrade` 展示分档，`Bigwin_Pre_Win_Range`／`Bigwin_Pre_Rate` 是大赢预判参数，不能互相替代。 |
| `special_config/game_server.conf` 的 `cut_multiple`、`free_cut_multiple` | 全局标量阈值；`slot_control_group.conf` 中的 `control_group_cut_multiple`／`control_group_free_cut_multiple` 是按 GROUP 索引的数组。 |
| `SpecialBetPercent`、`SpecialBetUnLockVip` | 既有特殊押注字段，yjzr 没有对应定义。 |

`Free_Max_Times=50` 由数学入口读取为 `FreeMaxTimes`。主游戏共享 Scatter 额度当前为 25；免费每个新 Scatter 固定追加 1 次，本手生成额度为 `FreeMaxTimes-FreeSpinNumber-FreeSpinsRemaining`。六列初始盘面、全部补牌及高 Scatter 拆分产生的额外位置共享额度。候选先判断准入，再决定尺寸拆分；额度为 0 时新 Scatter 候选变为普通图标，保留高度并按普通规则抽银框，不额外推进 `top index`。普通盘使用普通轴，特殊盘使用特殊轴，固定盘和零奖盘的普通候选池使用普通补牌轴。`MainExtraFreeSpinsPerScatter` 必须为正数，`FreeExtraSpinsPerScatter` 固定为 1；`BaseFreeSpins` 超过上限，或需要替换时同列普通候选池为空，均报配置错误。详见 [Scatter 生成控制](klsj_数值逻辑.md#scatter-生成控制)。

未启用 `Free_Max_Win`、`Gua_Last_Spins`、大赢预判及独立 Wild 生成替换机制。通用活动、玩家控制、道具卡和登录等文件由平台服务读取，当前 `theme_math.py`／`simulation.py` 仅读取本机台的数学配置及轴带，不把这些平台配置计入仿真结论。

## 策划案复核与实现更新

盘面、图标、银框转换和金色底板的最终规则见 [盘面与图标](klsj_数值逻辑.md#盘面与图标)，完整奖表见 [判奖与赔付](klsj_数值逻辑.md#判奖与赔付)。

首手免费起始倍数 `FreeStartMultiplier=1`，下一手从上一手最终实际结算倍数 `FreeEndMultiplier+1` 开始；无中奖时最终倍数等于起始倍数。`FreeSpinNumber` 记录本轮手数并参与 Scatter 额度计算，不决定起始倍数。手内按 `FreeStartMultiplier + min(CascadeIndex - 1, FreeSpinMultiplierIncrementCap)` 结算，`FreeSpinMultiplierIncrementCap=4`；达到手内增量上限后后续中奖照常结算，累计倍数不另设独立上限。例如本手从 x3 连消至 x7，下一手从 x8 开始。每轮初始奖励及追加次数合计最多 50，由新 Scatter 生成额度保证；免费每个新 Scatter 固定追加 1 次，所有已发放次数正常玩完，第 50 手完整结算。新 Scatter 额度为 0 时，其候选生成普通图标；已有 Scatter 正常保留且不重计，免费次数自然耗尽后结束。押注共 9 档，最高 25,000,000。大奖条件仅作为数值目标，展示使用 `BigWinGrade`／`NewBigWinGrade` 分档，不增加独立触发逻辑。详见 [免费游戏流程](klsj_数值逻辑.md#免费游戏流程)。

2026/10/13 已修复并验证两项生成约束：清理临时轴带第 1／6 列的非法 Wild，并校验所有普通／特殊轴、固定盘、零奖盘及生成结果；3／4 格 Scatter 保留为 2 格，多余高度在其上方按原补牌权重生成新图标，保留其他原配对图标和每列物理总高度。`ReelLayouts`／`ReelCellCounts` 记录实际初盘结果。33 项测试全部通过，覆盖生成约束、手内倍数封顶后继续派奖、上一手最终倍数加 1 的跨手传递，以及新一轮免费游戏从 1 重启。

该局部修复改变了临时分布和随机序列，已用种子 `20261013` 重跑 10,000 次付费 Spin，完成 47 次免费触发和 446 次免费 Spin。结果仅用于流程验证，不作为正式数值结论；详见 [图标生成规则](klsj_数值逻辑.md#盘面与图标)。

2026/10/13 免费次数生成控制验证：49 项测试全部通过，覆盖初盘与多轮补牌共享额度、同列普通图标频次替换、高度与银框、完整奖励次数、第 50 手完整派奖及新一轮重置。此前使用种子 `20261013` 的 1,000 次付费 Spin 仿真完成 5 次免费触发、59 次免费 Spin；该次结果仅用于流程验证。

## 运行

在仓库根目录运行：

```bash
python3 ThemeMath/klsj/simulation.py --spins 10000 --seed 20261013
python3 -m unittest discover -s ThemeMath/klsj -p 'test_*.py'
```

## 资料来源

- [《恐龙世界》策划案](</Users/sunyulu/Downloads/HGI_SLOT_《恐龙世界》策划案.docx>)：游戏规则、图标赔付、免费游戏和押注档位。
- [数值逻辑规范](</Users/sunyulu/.codex/skills/slot-game-server-designer/references/numeric-logic-output.md>)：数值逻辑文档的范围和流程表达要求。
