# 恐龙帝国 kldg

本项目按 `model_waysgame` 的目录组织，包含数学入口、仿真入口、主游戏及免费游戏轴带、游戏配置、服务器配置、控制配置和通用配置。玩法规则依据《恐龙帝国》草案 1.01 版及策划在本对话中的确认；正式轴带和随机权重尚未提供，当前配置明确用作**临时仿真样本**。

## 文件入口

- [玩法介绍](kldg_玩法描述.md)：玩家可见的中奖、边框、连消和免费游戏规则。
- [数值逻辑](kldg_数值逻辑.md)：服务端处理顺序、已确认奖表及临时配置的对应关系。
- [数学入口](theme_math.py)：继承 `WaysGame`，实现六列变高、同一路径最高奖、银框升金框再变 Wild、Scatter 跨连消累计与免费次数。
- [仿真入口](simulation.py)：按付费 Spin 运行主游戏和完整免费游戏，输出结构化统计。
- [关键规则测试](test_theme_math.py)：覆盖赔付、Wild 去重、边框随图标移动、Scatter 累计及消除倍数。

项目沿用模板的 `general_config/`、`reel_config/`、`free_reel_config/`、`special/` 和 `special_config/` 目录。`special/kldg_game_config.conf` 保存六列 Ways 盘面和已确认奖表，`special/kldg_game_server.conf` 保存临时仿真参数。通用配置从模板复制；玩家控制和道具卡配置是占位文件，`slot_control_group.conf` 的砍分阈值已置零。这些服务端文件尚不能直接用于上线。

## 临时数值

- `ReelHeightWeights`：六列各自对 2～6 行使用等权重。
- `SilverFrameChance`：第二至第五列第 2～4 行新出现的普通图标，以每格 1200/10000 的临时概率附带银框。
- `SilverUpgradeSymbolWeights`：银框中奖后，11 种普通图标暂按等权重生成带金框的新图标。
- 两套 `NORMAL_ROLL_1`～`NORMAL_ROLL_6` 轴带各长 120 格，由固定种子生成；免费轴带的 Scatter 数量比主游戏少，以保证临时仿真中的免费轮次能够结束。这些图标分布不代表最终数值设计。
- 主游戏和免费游戏各新增六条 120 格的 `SP_ROLL`：第 `i` 列普通轴左移 `17 × i` 格，再把新顺序中最先出现的 3 个图标 12 改为 Wild（图标 1）。这是可复现的临时特殊轴，并未按 RTP 调优。
- 两种模式各新增一个 6 列 × 6 行的 `FIX_RESULT_1` 和 `ZERO_RESULT_1`。固定盘让前三列第 1 行各出现一个 A（图标 8），形成一条 3 连初始中奖；零奖盘的前两列使用不同图标且不含 Wild、Scatter，保证初始盘面不中奖。固定盘如继续消除，补牌仍来自普通轴，最终奖励不固定。
- 两套轴配置的 `BASE_RATE=1,0,0,0` 保持不变，因此新增的特殊轴、固定盘和零奖盘目前只供强制分支测试，不参与常规随机仿真；正式启用比例待数值策划确定。
- 草案中所有普通图标赔付倍数已按最新要求统一除以 10；新奖表仍以本手总投注为基数，写入既有 `ITEM_PRIZES_2` 至 `ITEM_PRIZES_12` 时按平台 `BET_UNIT=10000` 存储。Wild 与 Scatter 无独立图标赔付。

当前轴带与权重仅用于检查流程。仿真输出的 `Rtp` 是奖励与付费投注之比；更新奖表后，用固定种子 `20261010` 跑 1,000 手得到 `Rtp=7.7895`，即样本奖励为投注的 7.7895 倍。这一结果仍不适合作为上线参数，也不表示恐龙帝国的目标 RTP。正式轴带、权重和目标 RTP 确定后须重新调参和仿真。

Wild 造成长短中奖路径共享前缀时，按已确认规则只结算赔付最高的一项，见[数值逻辑](kldg_数值逻辑.md)。

## 运行

在仓库根目录运行：

```bash
python3 ThemeMath/kldg/simulation.py --spins 1000 --seed 20261010
python3 -m unittest discover -s ThemeMath/kldg -p 'test_*.py'
```

正式数值设计时，应替换两套轴带、三个临时权重字段，确定目标 RTP 与免费游戏触发率，并与服务端配置对接后重新仿真。

## 资料来源

- [《恐龙帝国》草案](</Users/sunyulu/Downloads/HGI_SLOT_《恐龙帝国》草案.docx>)：文字规则、Megaways 计奖和图标赔付示意。
- [用户提供的 slot-game-server-designer skill](</Users/sunyulu/Downloads/slot-game-server-designer_share_20260814/slot-game-server-designer\SKILL.md>)及同文件夹的数值逻辑输出规范。

项目展示名称采用用户确认的“恐龙帝国”；草案中的“恐龙王国”和“龙蜥丛林”不作为本项目名称。
