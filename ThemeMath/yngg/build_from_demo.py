"""Build Si Botak Desa (yngg) configuration from reference reel data.

The Le King extract supplies reference reel strips. Game rules, IDs, payouts,
free modes and jackpots follow the HGI Si Botak Desa design specification.
Golden-area generation uses the explicit weights in yngg_bonus.conf.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


THEME_DIR = Path(__file__).resolve().parent
MODEL_DIR = THEME_DIR.parent / "model_countgame"
DEFAULT_DEMO_DIR = Path(r"C:\Users\sunyulu\le-king-demo-extract")
BET_UNIT = 10_000
ITEM_COUNT = 13
DESIGN_PAYTABLE = {
    3: ("H1", {"5": 1, "6-7": 2.5, "8-11": 5, "12+": 25}),
    4: ("H2", {"5": 1, "6-7": 2.5, "8-11": 5, "12+": 10}),
    5: ("H3", {"5": 0.5, "6-7": 1, "8-11": 3, "12+": 5}),
    6: ("M1", {"5": 0.3, "6-7": 0.5, "8-11": 1, "12+": 3}),
    7: ("M2", {"5": 0.3, "6-7": 0.5, "8-11": 1, "12+": 3}),
    8: ("L1", {"5": 0.1, "6-7": 0.2, "8-11": 0.5, "12+": 1}),
    9: ("L2", {"5": 0.1, "6-7": 0.2, "8-11": 0.5, "12+": 1}),
    10: ("L3", {"5": 0.1, "6-7": 0.2, "8-11": 0.3, "12+": 0.6}),
    11: ("L4", {"5": 0.1, "6-7": 0.2, "8-11": 0.3, "12+": 0.6}),
    12: ("L5", {"5": 0.1, "6-7": 0.2, "8-11": 0.3, "12+": 0.5}),
}


def target_symbol_id(source_symbol_id: int) -> int:
    """Map provider IDs to HGI: FS=0, Wild=1, features=2, pays=3..12."""

    if source_symbol_id == 12:
        return 0
    if source_symbol_id == 0:
        return 1
    if 1 <= source_symbol_id <= 10:
        # Source payouts rise from LOW_1 to HIGH_5. HGI IDs are reversed so
        # payout decreases as the target ID increases from 3 through 12.
        return 13 - source_symbol_id
    return 2


def load_strip(demo_dir: Path, name: str) -> list[list[int]]:
    path = demo_dir / "numeric" / "reels" / "strips" / f"{name}.csv"
    reels = [[] for _ in range(6)]
    with path.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            for reel_index in range(6):
                value = row[f"reel_{reel_index}"].strip()
                if value:
                    reels[reel_index].append(target_symbol_id(int(value)))
    return reels


def copy_model_layout() -> None:
    for directory in ("general_config", "special_config"):
        destination = THEME_DIR / directory
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(MODEL_DIR / directory, destination)
    (THEME_DIR / "special").mkdir(exist_ok=True)
    (THEME_DIR / "special" / "yngg_control.conf").write_text(
        "\n".join(
            [
                "[MAIN]",
                "#控制配置版本",
                "version = 1",
                "#暂未分配内部控制ID，因此不启用控制项",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (THEME_DIR / "special" / "slot_prop_config.conf").write_text(
        "\n".join(
            [
                "[System Base Info]",
                "#配置文件版本",
                "VERSION = 101",
                "#开放该道具功能所需的最低游戏版本，0表示暂不开放",
                "OPEN_GAME_VER = 0",
                "#单日可使用次数，0表示暂不开放",
                "DAY_USE_MAX_NUM = 0",
                "#暂未分配内部GAME_ID和PROP_ID，因此不启用道具",
                "",
            ]
        ),
        encoding="utf-8",
    )


def payout_row(payouts: dict[str, float]) -> list[int]:
    result = [0] * 30
    result[4] = round(payouts["5"] * BET_UNIT)
    for count in (6, 7):
        result[count - 1] = round(payouts["6-7"] * BET_UNIT)
    for count in range(8, 12):
        result[count - 1] = round(payouts["8-11"] * BET_UNIT)
    for count in range(12, 31):
        result[count - 1] = round(payouts["12+"] * BET_UNIT)
    return result


def flatten_board(board: list[list[int]]) -> list[int]:
    """Flatten a column-major 6x5 board for FIX/ZERO_RESULT."""

    return [symbol for column in board for symbol in column]


def build_fixed_results() -> list[list[int]]:
    """Build ten boards with no orthogonally adjacent matching symbols."""

    return [
        flatten_board(
            [
                [3 + ((column * 2 + row + offset) % 10) for row in range(5)]
                for column in range(6)
            ]
        )
        for offset in range(10)
    ]


def build_zero_results() -> list[list[int]]:
    """Build ten boards that create golden squares and retain Bonus ID 2."""

    results = []
    for offset in range(10):
        board = [
            [3 + ((column * 2 + row + offset + 1) % 10) for row in range(5)]
            for column in range(6)
        ]
        cluster_symbol = 3 + offset
        for column in range(5):
            board[column][0] = cluster_symbol
        board[5][4] = 2
        results.append(flatten_board(board))
    return results


def write_game_config(demo_dir: Path) -> None:
    prizes = [[0] * 30 for _ in range(ITEM_COUNT)]
    for symbol_id, (_, payouts) in DESIGN_PAYTABLE.items():
        prizes[symbol_id] = payout_row(payouts)

    lines = [
        "[MAIN]",
        "#配置文件版本",
        "VERSION=101",
        "#盘面为6列5行，牌面按board[col][row]组织",
        "COL_COUNT=6",
        "ROW_COUNT=5",
        "#原始symbol ID范围为0-12；转化后的Super Scatter ID 13不计入原始symbol数量",
        f"ITEM_COUNT={ITEM_COUNT}",
        "#奖值缩放系数；ITEM_PRIZES以万分之一下注为单位",
        "PRIZE_RATE=1",
        "#按symbol ID标记是否可由Wild代替；仅普通赔付图标3-12启用",
        "USE_WILDS=" + ",".join("1" if 3 <= item <= 12 else "0" for item in range(ITEM_COUNT)),
        "#按symbol ID配置起奖数量；普通图标至少5个相连",
        "BASE_NUMS=" + ",".join("5" if 3 <= item <= 12 else "0" for item in range(ITEM_COUNT)),
        "#ITEM_PRIZES_n数组下标为Cluster数量-1；3-12依次为H1/H2/H3/M1/M2/L1-L5",
    ]
    lines.extend(f"ITEM_PRIZES_{item}=" + ",".join(map(str, row)) for item, row in enumerate(prizes))
    lines.extend(
        [
            "#LINE_MODE=4保留CountGame配置格式，实际按横向/纵向相连的Cluster结算",
            "LINE_MODE=4",
            "#Pay Line兼容配置；Cluster玩法不使用固定线",
            "BOTH_SIDES=0",
            "FULL_WILD_LINE=0",
            "RULE_COUNT=0",
            "#RULE_COUNT大于0时按LINE_RULES_N配置固定线",
            "#Scatter不在通用赔付表派彩，免费触发由theme_math.py处理",
            "SCATTER_MODE=0",
            "SCATTER_ID=0",
            "SCATTER_COLS=1,1,1,1,1,1",
            "SCATTER_SERIAL=0",
            "SCATTER_MULTIPLES=" + ",".join(["0"] * 30),
            "SCATTER_PRIZES=" + ",".join(["0"] * 30),
            "#主游戏和免费游戏均启用全部30个格子；0表示格子有效",
            "GRID_DISABLES=" + ",".join(["0"] * 30),
            "GRID_DISABLES_FREE=" + ",".join(["0"] * 30),
            "",
        ]
    )
    (THEME_DIR / "special" / "yngg_game_config.conf").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_bonus_config() -> None:
    """Write JP and golden-area outcome weights."""

    lines = [
        "[GENERAL]",
        "# 通用Bonus配置。每个金色位置先按类型权重抽取类型，再按该类型的档位权重抽取具体结果。",
        "# 档位数组与权重数组按相同下标一一对应；权重为相对权重，不要求总和为10000。",
        "",
        "# JP固定倍数，顺序为MINI、MINOR、MAJOR、GRAND。",
        "BONUS_MINI_MULTI=10",
        "BONUS_MINOR_MULTI=25",
        "BONUS_MAJOR_MULTI=100",
        "BONUS_GRAND_MULTI=5000",
        "BONUS_JP_MULTIPLE=10,25,100,5000",
        "# JP档位权重，与BONUS_JP_MULTIPLE按下标对应；当前均为1，后续可独立调整。",
        "BONUS_JP_TYPE_PROBABILITY=1,1,1,1",
        "",
        "# 金色框位置类型及对应权重；当前金币/四叶草/聚宝盆/JP为1000/100/10/1。",
        "BONUS_SYMBOL_TYPE=coin,clover,pot,jackpot",
        "BONUS_SYMBOL_TYPE_PROBABILITY=1000,100,10,1",
        "",
        "# 金币档位及对应权重，两个数组按下标对应；当前均为1，后续可调整各档位权重。",
        "BONUS_COIN_MULTIPLE=0.2,0.5,1,2,3,4,5,10,15,20,25,50,100,250,500",
        "BONUS_COIN_MULTIPLE_PROBABILITY=1,1,1,1,1,1,1,1,1,1,1,1,1,1,1",
        "",
        "# 四叶草倍数档位及对应权重，两个数组按下标对应；当前均为1，后续可调整各档位权重。",
        "BONUS_CLOVER_MULTIPLE=2,3,4,5,10,20",
        "BONUS_CLOVER_MULTIPLE_PROBABILITY=1,1,1,1,1,1",
        "",
    ]
    (THEME_DIR / "special" / "yngg_bonus.conf").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_reel_config(
    demo_dir: Path,
    directory: str,
    strip_name: str,
    file_prefix: str = "",
) -> None:
    target = THEME_DIR / directory
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    reels = load_strip(demo_dir, strip_name)
    (target / f"yngg_{file_prefix}rand_main.conf").write_text(
        "\n".join(
            [
                "[MAIN]",
                "#配置文件版本，变更后重新读取配置",
                "VERSION=101",
                "#盘面列数",
                "COL_COUNT=6",
                "#盘面行数",
                "ROW_COUNT=5",
                "#原始symbol总数（ID 0-12；转化后的Super Scatter ID 13不计入）",
                f"ITEM_COUNT={ITEM_COUNT}",
                "#使用的symbol组合数量",
                "ITEM_COM_COUNT=1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    lines = [
        "[MAIN]",
        "#配置文件版本",
        "VERSION=101",
        "",
        "[GENERAL_1]",
        f"#参考轴来源：numeric/reels/strips/{strip_name}.csv",
        "#BASE_RATE依次为正常盘、特殊盘、固定盘、零概率盘；当前仅使用正常盘",
        "#NORMAL_ROLL_1-6为各列基础轴，SP_ROLL_1-6暂与基础轴一致",
        "#FIX包含10个完全无奖盘；ZERO包含10个必定生成金色区域并保留Bonus ID 2的盘面",
        "BASE_RATE=1000,0,0,0",
    ]
    lines.extend(f"NORMAL_ROLL_{index}=" + ",".join(map(str, reel)) for index, reel in enumerate(reels, 1))
    lines.extend(f"SP_ROLL_{index}=" + ",".join(map(str, reel)) for index, reel in enumerate(reels, 1))
    fixed_results = build_fixed_results()
    zero_results = build_zero_results()
    lines.extend(["", "#固定盘：10个完全不赢钱的牌面", "FIX_DISORDER=0", f"FIX_NUM={len(fixed_results)}"])
    lines.extend(
        f"FIX_RESULT_{index}=" + ",".join(map(str, result))
        for index, result in enumerate(fixed_results, 1)
    )
    lines.extend(
        [
            "",
            "#零概率盘：10个必定触发Bonus玩法的牌面",
            "#每盘前五列顶部组成5连Cluster以生成金色区域，同时保留一个Bonus ID 2",
            "ZERO_DISORDER=0",
            f"ZERO_NUM={len(zero_results)}",
        ]
    )
    lines.extend(
        f"ZERO_RESULT_{index}=" + ",".join(map(str, result))
        for index, result in enumerate(zero_results, 1)
    )
    lines.append("")
    (target / f"yngg_{file_prefix}rand_ex_0.conf").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_metadata(demo_dir: Path) -> None:
    paytable = [
        {
            "symbol_id": symbol_id,
            "symbol": name,
            "payout_x_bet": payouts,
        }
        for symbol_id, (name, payouts) in DESIGN_PAYTABLE.items()
    ]
    metadata = {
        "identity": {
            "provider": "HGI",
            "game": "Si Botak Desa",
            "game_id": 362,
            "program_name": "yngg",
        },
        "layout": {
            "reels": 6,
            "rows": 5,
            "win_type": "cluster",
            "minimum_connected_symbols": 5,
            "connection": ["horizontal", "vertical"],
            "original_symbol_count": 13,
        },
        "paytable": paytable,
        "symbol_id_mapping": {
            "scatter": 0,
            "wild": 1,
            "golden_feature_symbols": 2,
            "paying_symbols": "3-12 (payout descending)",
            "super_scatter_source": 0,
            "super_scatter_result": 13,
        },
        "super_scatter_conversion": {
            "probability": "1/50",
            "probability_per_10000": 200,
        },
        "special_symbol_generation": {
            "scatter_count_weights": [1000, 100, 50, 5],
            "base_no_win_bonus_count_weights": [80, 20],
            "base_win_bonus_count_weights": [90, 10],
            "free_golden_bonus_count_weights": [60, 40],
            "free_no_golden_bonus_count_weights": [30, 70],
            "drop_special_symbol_weights": [998, 1, 1],
            "free_bonus_guaranteed": True,
        },
        "coin_values_x_bet": [0.2, 0.5, 1, 2, 3, 4, 5, 10, 15, 20, 25, 50, 100, 250, 500],
        "clover_multipliers": [2, 3, 4, 5, 10, 20],
        "fixed_jackpots_x_bet": {
            "mini": 10,
            "minor": 25,
            "major": 100,
            "grand": 5000,
        },
        "bonus_generation": {
            "symbol_types": ["coin", "clover", "pot", "jackpot"],
            "symbol_type_weights": [1000, 100, 10, 1],
            "coin_value_weights": [1] * 15,
            "clover_multiplier_weights": [1] * 6,
            "jackpot_type_weights": [1] * 4,
        },
        "free_games": {
            "free": {"trigger": "3 scatters", "spins": 10},
            "super_free": {"trigger": "2 scatters + 1 super scatter", "spins": 10},
            "retrigger": {"2_scatters": 2, "3_scatters": 4},
        },
        "bet_scopes": [100000, 200000, 500000, 1000000, 2000000, 5000000, 10000000, 20000000],
        "provenance": {
            "rules": r"C:\Users\sunyulu\Downloads\HGI_SLOT_《印尼鬼怪》策划案.md",
            "reference_reels": str(demo_dir / "numeric" / "reels" / "strips"),
        },
        "limitations": [
            "Reference reel strips do not contain HGI scatter or feature symbols.",
            "Configured local bonus weights can be overridden by authoritative server rounds.",
        ],
    }
    (THEME_DIR / "source_math.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (THEME_DIR / "special_config" / "base_game_name.conf").write_text(
        "\n".join(
            [
                "#服务器提示文字,0中文，1英文，2地方语言",
                "[base_game_name]",
                "game_name_0 = 乡村小秃头",
                "game_name_1 = Si Botak Desa",
                "game_name_2 = Si Botak Desa",
                "game_name_3 = Si Botak Desa",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (THEME_DIR / "special" / "yngg_game_server.conf").write_text(
        "\n".join(
            [
                "[System Base Info]",
                "#支持的下注档位",
                "BetScopes = 100000,200000,500000,1000000,2000000,5000000,10000000,20000000",
                "",
                "[Game Info]",
                "#配置文件版本",
                "Version=101",
                "#从game config迁移的特殊symbol ID",
                "WILD_ID=1",
                "FEATURE_ID=2",
                "BONUS_ID=2",
                "COIN_ID=2",
                "CLOVER_ID=2",
                "POT_ID=2",
                "MULTIPLIER_ID=2",
                "COLLECTOR_ID=2",
                "JACKPOT_ID=2",
                "SUPER_SCATTER_ID=13",
                "#Cluster至少5个横向或纵向相连的同类图标起奖",
                "ClusterMinimum=5",
                "#免费游戏触发图标ID",
                "ScatterId=0",
                "#Super Scatter原始图标与Scatter相同，使用ID 0",
                "SuperScatterSourceId=0",
                "#转化成功后使用ID 13区分Super Scatter",
                "#每个Scatter独立转化为Super Scatter的概率，200/10000=1/50",
                "SuperScatterProbability=200",
                "#Scatter出现数量权重，下标0-3分别表示出现0-3个",
                "ScatterCountProbability=1000,100,50,5",
                "#Base无Scatter且无奖时，Bonus数量0/1的权重",
                "BaseNoWinBonusCountProbability=80,20",
                "#Base无Scatter且有奖时，Bonus数量0/1的权重",
                "BaseWinBonusCountProbability=90,10",
                "#Free已有金框时，Bonus数量0/1的权重",
                "FreeGoldenBonusCountProbability=60,40",
                "#Free没有金框时，Bonus数量0/1的权重",
                "FreeNoGoldenBonusCountProbability=30,70",
                "#每个掉落图标替换结果权重：不替换/Scatter/Bonus",
                "DropSpecialSymbolProbability=998,1,1",
                "#普通免费、超级免费初始次数",
                "FreeSpinCounts=10,10",
                "#下标为Scatter数量；2个追加2次，3个追加4次",
                "FreeSpinRetrigger=0,0,2,4",
                "",
                "#彩虹",
                "BONUS_1 = 1",
                "#铜币",
                "BONUS_2 = 2",
                "#银币",
                "BONUS_3 = 3",
                "#金币",
                "BONUS_4 = 4",
                "#四叶草",
                "BONUS_5 = 5",
                "#聚宝盆",
                "BONUS_6 = 6",
                "#Mini",
                "BONUS_7 = 7",
                "#Minor",
                "BONUS_8 = 8",
                "#Major",
                "BONUS_9 = 9",
                "#Grand",
                "BONUS_10 = 10",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, default=DEFAULT_DEMO_DIR)
    args = parser.parse_args(argv)
    demo_dir = args.demo_dir.resolve()
    if not (demo_dir / "numeric" / "game-math.json").exists():
        raise FileNotFoundError(f"Le King demo extraction not found: {demo_dir}")
    copy_model_layout()
    write_game_config(demo_dir)
    write_bonus_config()
    write_reel_config(demo_dir, "reel_config", "default")
    write_reel_config(demo_dir, "free_reel_config", "fs", file_prefix="free_")
    write_metadata(demo_dir)


if __name__ == "__main__":
    main()
