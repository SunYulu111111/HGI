# HGI Math

HGI Math 是一个 Slots 数学逻辑与仿真项目。仓库核心放在 `ThemeMath/` 下，通用模块负责读取配置、生成牌面、计算 Ways/Lines/Count 玩法收益，各主题目录只保留本主题的配置、特性逻辑和仿真入口。

## 项目结构

```text
.
|-- README.md
|-- test.py
`-- ThemeMath/
    |-- slots_math.py          # 通用 Slots 基础逻辑、WaysGame、LinesGame、CountGame
    |-- slots_simulation.py    # 通用仿真状态统计与报表输出
    |-- symbol_count.py        # 统计轴带 symbol 数量并写回配置备注
    |-- model_waysgame/        # Ways 玩法模板
    |-- model_linesgame/       # Lines 玩法模板
    |-- model_countgame/       # Count 玩法模板
    |-- mahj3/
    |-- mjwl/
    |-- rzcs/
    `-- yngg/
```

常见主题目录约定：

- `theme_math.py`：主题数学入口，通常定义 `ThemeMath`。
- `simulation.py`：主题仿真入口。
- `game_config.conf` 或 `special/game_config.conf`：基础数学配置。
- `reel_config/`：普通盘轴带配置。
- `free_reel_config/`：免费盘轴带配置。
- `general_config/`、`special/`、`special_config/`：主题相关配置。
- `LOGIC.md`：主题玩法逻辑说明。

## 环境要求

项目主要使用 Python 标准库，建议使用 Python 3.10 或更高版本。

```bash
python --version
```

如果后续主题引入第三方依赖，请优先补充依赖文件和本 README 的安装说明。

## 快速开始

在仓库根目录运行主题仿真：

```bash
python ThemeMath/model_linesgame/simulation.py --spins 100000 --index 0 --general 1
python ThemeMath/yngg/simulation.py --spins 100000 --base-bet 100000 --index 0 --general-index 1
```

运行单元测试：

```bash
python -m unittest ThemeMath.yngg.test_theme_math
```

统计并更新某个主题的轴带 symbol 数量：

```bash
python ThemeMath/symbol_count.py --root ThemeMath/rzcs
```

只检查不写回：

```bash
python ThemeMath/symbol_count.py --root ThemeMath/rzcs --dry-run
```

## 新任务目录约定

接下来的新主题或新任务建议放在 `ThemeMath/<new_folder>/` 下独立进行，避免直接混入已有主题目录。

推荐流程：

1. 根据玩法类型复制一个模板目录：`model_waysgame/`、`model_linesgame/` 或 `model_countgame/`。
2. 重命名为新的主题或任务目录，例如 `ThemeMath/new_theme/`。
3. 替换或补齐 `game_config.conf`、`reel_config/`、`free_reel_config/` 等配置。
4. 在新目录内维护 `theme_math.py`、`simulation.py` 和必要的 `LOGIC.md`。
5. 大规模仿真输出文件建议单独保存，提交前确认是否需要纳入版本库。

## 核心模块说明

`ThemeMath/slots_math.py` 提供通用基础类和玩法基类：

- `SlotsGame`：读取主题配置、加载轴带、随机生成牌面，并维护停轴状态。
- `WaysGame`：基于 ways 规则计算中奖。
- `LinesGame`：基于固定线规则计算中奖。
- `CountGame`：基于 symbol 数量规则计算中奖。

`ThemeMath/slots_simulation.py` 提供仿真统计工具，统一维护 RTP、Hit 率、Free 触发、倍数区间等报表字段。

主题入口通常继承其中一个玩法类，并实现本主题的普通盘、免费盘、特殊 symbol、消除补牌或其它特色功能。

## 配置注意事项

- `GENERAL_n` 表示不同权重或轴带分组，仿真时通过 `--general` 或 `--general-index` 选择。
- `reel_config` 文件中的 `BASE_RATE` 通常对应普通盘、特殊盘、固定结果、零概率结果等来源。
- 配置里涉及金额或赔率时，注意和 `base_bet`、`BET_UNIT` 保持一致。
- 修改轴带后建议运行 `symbol_count.py --dry-run` 检查统计结果，再决定是否写回。
