# yngg / Si Botak Desa 数学说明

## 数据来源

玩法以 `HGI_SLOT_《印尼鬼怪》策划案.md` 为准，Le King demo 只提供参考滚轮：

- `numeric/reels/strips/default.csv`：基础数学滚轮。
- `numeric/reels/strips/fs.csv`：免费游戏数学滚轮。

运行 `python -B ThemeMath\yngg\build_from_demo.py --demo-dir <目录>` 可重新生成配置。

## 基础玩法

- 6 列 × 5 行。
- 图标 0 为 Free Spin，1 为 Wild，2 为所有翻金币相关功能图标。
- 普通图标使用 3–12，ID 越大赔付越低。
- Super Scatter 为 13。
- 相同图标横向或纵向相邻形成 Cluster，至少 5 个起奖。
- Wild 可以加入 Cluster，但不能单独中奖。
- 每轮只消除实际中奖 Cluster 的位置，然后按原停轴上方顺序补牌，直到无奖。
- 押注档位：100,000 / 200,000 / 500,000 / 1,000,000 / 2,000,000 / 5,000,000 / 10,000,000 / 20,000,000。

## 免费游戏

- 3 个 Scatter：普通免费，10 次。
- 2 个 Scatter + 1 个 Super Scatter：超级免费，10 次。
- 免费游戏中 2/3 个 FS 分别追加 2/4 次。
- 普通免费中的金色区域在金币玩法触发后清除。
- 超级免费中的金色区域持续到玩法结束。
- 触发 Scatter/Super Scatter 的位置进入免费时直接成为金色区域。

## 金色玩法

- 消除位置生成金色区域；全部消除后仍有 Bonus（ID 2）时触发。
- 金币倍数：0.2/0.5/1/2/3/4/5/10/15/20/25/50/100/250/500。
- 四叶草：按 2/3/4/5/10/20 倍放大中心九宫格内的金币和聚宝盆，不影响 JP。
- 聚宝盆：按从上到下、从左到右顺序收集当前金币及已结算聚宝盆，不收集 JP。
- JP：MINI 10x、MINOR 25x、MAJOR 100x、GRAND 5000x。

功能图标生成概率不在策划案中，需通过 `golden_rounds` 注入服务器结果，数学层负责确定性结算：

```python
{
    "initial_board": [[...], [...], [...], [...], [...], [...]],
    "scatter_count": 3,
    "super_scatter_count": 0,
    "bonus_count": 1,
    "golden_rounds": [
        [
            {"position": [0, 0], "type": "coin", "value": 5},
            {"position": [1, 0], "type": "clover", "multiplier": 2},
            {"position": [2, 0], "type": "jackpot", "tier": "mini"},
        ]
    ],
}
```

聚宝盆导致重翻后，下一项 `golden_rounds` 必须给出所有被重新生成格子的结果。

## 验证

```powershell
python -B ThemeMath\yngg\test_theme_math.py
python -B ThemeMath\symbol_count.py --root ThemeMath\yngg --symbol-max 13 --dry-run
python -B ThemeMath\yngg\simulation.py --spins 10000
```

模拟结果只覆盖参考滚轮及 Cluster Cascade，不包含未知的服务器功能概率。
