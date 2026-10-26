# 超级英雄 cjyx

《超级英雄》（Heroes’ Fight），游戏 ID 373，5 列 5 行、19 条固定赔付线。`ThemeMath` 继承公共 `LinesGame`，目录、配置协议、逐手接口及仿真统计沿用 `model_linesgame`。

特殊 Wild 的共同预延展、普通 Wild 融合乘倍、免费升级和超级免费列激活由主题层处理；配置读取、正常／特殊／固定／零奖盘抽取和基础判线复用公共模块。当前轴带及等权重用于流程验证，标记为 `FlowValidation`，正式数值仍需校准。

## 目录与文件

```text
cjyx/
├── general_config/                 # 模板通用平台配置
├── special_config/
│   ├── base_game_name.conf          # 超级英雄名称
│   ├── game_server.conf             # 通用服务器参数
│   └── slot_control_group.conf      # 已确认的 Group 阈值和模板控制组
├── special/
│   ├── cjyx_game_config.conf         # 5×5、19 线、奖表、Scatter、初始盘
│   ├── cjyx_game_server.conf         # 押注档位、特色玩法参数
│   ├── cjyx_control.conf             # 模板玩家控制配置
│   └── slot_prop_config.conf         # 道具配置入口
├── reel_config/
│   ├── cjyx_rand_main.conf
│   └── cjyx_rand_ex_0.conf
├── free_reel_config/
│   ├── cjyx_free_rand_main.conf
│   ├── cjyx_free_rand_ex_0.conf
│   └── cjyx_super_free_rand_ex_0.conf
├── theme_math.py
├── simulation.py
├── build_demo_reels.py
├── test_theme_math.py
├── test_simulation.py
├── test_config_contract.py
├── cjyx_数值逻辑.md
└── cjyx_玩法描述.md
```

[数值逻辑](cjyx_数值逻辑.md) 说明线路、奖表、处理顺序、配置字段和统计口径；[玩法描述](cjyx_玩法描述.md) 提供玩家可见规则。[数学入口](theme_math.py) 与 [仿真入口](simulation.py) 可直接运行。

配置沿用 `[MAIN]`、`[GENERAL_n]`、`BASE_RATE`、`NORMAL_ROLL_n`、`SP_ROLL_n`、`FIX_RESULT_n`、`ZERO_RESULT_n` 等已有协议。`BASE_RATE` 依次选择正常、特殊、固定、零奖盘；特色新增字段集中在 `cjyx_game_server.conf`，使用 PascalCase；固有规则放 `[Game Info]`，TYPE 0 的融合和补入权重放 `[0]`。

`ITEM_PRIZES_n` 保持万分比存储，`PRIZE_RATE=1`，例如 17.5 倍存为 175000。`BetScopes=10,20,50,100,200,500,1000,2000` 为档位系数，`BetPerReel` 均为 1，乘房间底分 10000 后得到 8 档实际总投注 100,000～20,000,000。`USE_WILDS` 中两类 Wild 自身的对应项均为 0。5 组初始盘每组均为 25 格，无中奖和免费触发。

配置字段归属遵循仓库 [model 生成与配置字段归属](../../README.md#model-生成与配置字段归属)：特色参数仅放在 `cjyx_game_server.conf`，其他配置只保留 model 字段。轴带用途和生成种子记录在本 README；当前验证轴带由 `build_demo_reels.py` 使用默认种子 `20261026` 生成。cjyx 没有独立 Bonus 玩法，不生成 `cjyx_bonus.conf`。

主游戏和普通免费各有模板的 main／ex 文件，超级免费轴放在同一 `free_reel_config` 目录。程序按模式显式选择文件模板，避免两个免费轴文件在相同索引下混淆。请求索引或 GENERAL 不存在时，沿用公共模块的 0／1 回退，并在 `spin_info` 和仿真汇总中记录实际配置。

## 运行

在仓库根目录使用 Python 3.10 或以上版本，无第三方依赖：

```bash
python3 ThemeMath/cjyx/simulation.py --spins 100000 --index 0 --general 1 --free-general 1 --seed 20261026 --output /tmp/cjyx_lines_result.csv
python3 -m unittest discover -s ThemeMath/cjyx -p 'test_*.py'
```

| 参数 | 作用 |
| --- | --- |
| `--spins` | 每组付费旋转数，默认 1,000,000；每次触发的免费游戏全部执行后计入结果。 |
| `--index` | 请求的轴带文件索引，默认 0，当前仅提供 TYPE 0。 |
| `--general`、`--general-index` | 主游戏 `[GENERAL_n]`，当前配置为 1。 |
| `--free-general`、`--free-general-index` | 免费 `[GENERAL_n]`；未指定时跟随主游戏。 |
| `--base-bet` | 总投注，默认 100,000，须为合法投注档位。 |
| `--seed` | 整数随机种子；相同配置和种子可复现。 |
| `--report-interval` | 默认每完成 5,000 次付费旋转输出累计表格；0 仅输出最终汇总。 |
| `--no-print-updates` | 关闭中间表格，保留最终表格。 |
| `--output` | 每组完成后立即追加最终汇总到指定 CSV；默认本目录 `simulate_result.csv`。 |
| `--indexes`、`--generals`、`--free-generals` | 逗号分隔的批量配置，例如 `0,1`；分别与对应单值选项互斥。 |

报表通过 `slots_simulation.simulation` 累计并输出，保留模板的 `SPIN`、`rtp`、`rtp_check`、`BaseLine`、`FreeLine`、`Free次数`、`FreeSpin` 等列，并补充普通免费、超级免费和终极大奖统计。`FreeLine` 合计两种免费奖励；普通／超级免费分项以当前手所属模式统计。

命中与高倍按付费及其完整免费游戏的总奖励统计。高倍保持模板的严格大于口径，`>5x` 不包含恰好 5 倍。各模式 RTP 均除以实际付费总投注；CSV 内 RTP 为比例值，例如 0.95 表示 95%。终极大奖平均间隔以全部实际旋转数为分母，零命中时留空。中间检查点只显示，最终结果每组追加一行，最终检查点不重复打印。运行前检查参数和 CSV 表头；后续组合失败时保留已经完成并写入的结果。

检查轴带图标统计时，显式包含本主题的完整 ID 范围：

```bash
python3 ThemeMath/symbol_count.py --root ThemeMath/cjyx --symbol-max 12 --dry-run
```

统计工具默认最大 ID 为 10；本主题的 ID 11、12 也是合法普通图标。

## 数学接口

```python
from ThemeMath.cjyx.theme_math import ThemeMath

Game = ThemeMath(base_bet=100000, Seed=20261026)
Result = Game.ng_spin(index=0, general_index=1, return_detail=True)
TotalWin = Result["total_win"]
while Game.FreeSpinsRemaining > 0:
    Result = Game.fg_spin(index=0, general_index=1, return_detail=True)
    TotalWin += Result["total_win"]
```

模板返回字段为 `item_list`、`total_win`、`line_win`、`win_items`、`win_positions`、`win_free`、`spin_info`、`free_game`，特色状态使用 `Mode`、`NextMode`、`AwardedFreeSpins`、`FreeSpinsRemaining`、`ActivatedColumns` 等 PascalCase 字段。

基础判奖将 ID 2 临时视为 Wild ID 1，实际调用公共 `LinesGame.cal_item_list`，保留原图标用于展示和融合。共同预延展及最终判线均走公共判奖，最终再按实际中奖组合叠加倍数。

本地判线使用 model 的首个非 Wild 图标作为目标，例如 Wild、Wild、Wild、J、K 按 J 四连结算；整线均为 Wild 时结算 Wild 五连。根 README 的 `FULL_WILD_LINE` 属于平台协议说明，model 未提供该字段，公共加载器也未读取。服务器对接时需核对该协议中“取较大奖励”的候选范围。

`evaluate(item_list=..., return_detail=True)` 用于固定盘验收，不提交免费次数及列激活状态，但会消耗实例随机序列。`ng_spin`、`fg_spin` 也支持 `Board` 固定盘。免费次数达到 99 的组合会在授予前被控制，正常累计发放最多 98 次；此前授予次数全部执行，升级不重置累计。

## 验证轴带与平台配置

三模式每列均有 200 个轴带图标，逗号分隔的值字符串不超过 500 字符；正常盘与特殊盘使用相同样本，`BASE_RATE=10000,0,0,0`。每份 ex 只有 `[GENERAL_1]`，主／免费 main 的 `ITEM_COM_COUNT=1`。固定盘与零奖盘均使用合法 25 格普通图标零奖盘，关闭列内乱序。主游戏每列自然可见特殊 Wild、普通 Wild 的概率均为 5%；两种免费中分别为 12.5%、25%。每列自然可见 Scatter 的概率均为 5%，后续继续执行全盘上限和激活列保证补入。

三套融合权重均为 15 项等权重，每个倍数概率为 1/15；25 项补入权重均为 1，只在本列合法候选内抽取。当前样本奖励明显偏高，不能作为正式 RTP 或终极大奖目标达标依据。

重复生成五份模板轴带文件：

```bash
python3 ThemeMath/cjyx/build_demo_reels.py
```

该命令生成主／免费 main 文件及三模式 ex 文件。相同种子和数据重复生成保持版本不变；ex 内容实际变化时，递增该 ex 及关联 main 的版本。正式数值设计后应同步更新生成方案。

`general_config` 沿用模板通用配置。主题控制配置仅保留实际投注档位及参数完整的控制段；Group 0～17 当前均引用唯一存在的 TYPE 0，属于同一套流程验证样本，尚未分别校准各 Group 的数值目标。TYPE 0 的主／普通免费／超级免费轴和 `[0]` 权重必须齐全；付费手选择的实际 TYPE 贯穿整轮免费。缺少对应 TYPE 参数时报配置错误，不通过切换到其他 TYPE 掩盖缺项。

`slot_control_group.conf` 保留已确认的两组 18 项阈值：主游戏按单手、免费按整轮累计逐手检查，升级继续累计。平台负责玩家控制和实际砍分，本地仿真只读取数学配置、特色参数和轴带，以 `Uncontrolled` 标记自然奖励。

`slot_prop_config.conf` 仅保留模板基础信息，没有道具条目，也没有引用空 ID 的道具控制段。`OPEN_GAME_VER=6` 表示最低功能版本，不作为道具开关。全局配置未添加特殊押注参数，回放金额单位按金币填写，`3000000000` 表示 3B。

## 资料依据

最新附件为 [HGI_SLOT_《超级英雄》策划案-3.docx](</Users/sunyulu/Downloads/HGI_SLOT_《超级英雄》策划案-3.docx>)，修订记录为 1.05，日期为 2026 年 9 月 28 日。2026 年 10 月 26 日核对的正文和全部内嵌规则图片与此前版本相同。

赔付继续采用此前已确认的“图标需求”正文，以总投注计奖；规则页旧 paytable 图片不覆盖已确认奖表。Scatter 替换、次数控制、共同预延展、补入、Group 阈值和终极大奖精确口径沿用目录已记录的确认规则。

## 验证记录

配置与机制检查覆盖 model 字段归属、GENERAL 套数、轴带长度、main/ex 版本联动、完整 TYPE 参数、固定及零奖盘、押注数组、Group 引用、道具配置和基础协议读取。机制测试继续覆盖 19 条线路、双 Wild、融合、免费升级、次数边界和列激活；仿真测试覆盖共享统计、单值／批量命令行、检查点和 CSV。

2026 年 10 月 26 日：78 项测试全部通过，27 份 `.conf` 均可解析；除允许扩展的主题 game_server 外，其余配置只含 model 已有字段和配置段。轴带每列 200 个图标，最长 466 字符；默认种子重复生成的文件及版本一致。图标统计以 ID 0～12 检查，无越界图标。

种子 `20261026`、总投注 `100000` 的 100,000 次付费仿真共执行 101,310 手：普通免费 1,220 手、超级免费 90 手，122 次普通免费触发和 9 次超级免费直接触发；本次未发生再触发或升级，这两类分支由固定盘测试覆盖。授予的 1,310 次免费全部执行，实际 TYPE 均为 0，通用报表与分模式金额、免费计数及最终 CSV 复算一致。

该次流程验证样本 RTP 为 1314.8399%，命中终极大奖 1 手。正式轴带、融合权重和各 Group 目标仍需独立校准，本记录不作为正式返奖率或稀有事件目标达标结论。
