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
