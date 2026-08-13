"""Build Si Botak Desa (yngg) configuration from reference reel data.

The Le King extract supplies reference reel strips. Game rules, IDs, payouts,
free modes and jackpots follow the HGI Si Botak Desa design specification.
Unknown reel-selection and feature-generation probabilities are not invented.
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
ITEM_COUNT = 14
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
    (THEME_DIR / "special" / "control.conf").write_text(
        "\n".join(
            [
                "[MAIN]",
                "version = 1",
                "# Deployment controls are disabled until yngg receives internal control IDs.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (THEME_DIR / "special" / "slot_prop_config.conf").write_text(
        "\n".join(
            [
                "[System Base Info]",
                "VERSION = 101",
                "OPEN_GAME_VER = 0",
                "DAY_USE_MAX_NUM = 0",
                "# Props are disabled until internal GAME_ID and PROP_ID values are assigned.",
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


def write_game_config(demo_dir: Path) -> None:
    prizes = [[0] * 30 for _ in range(ITEM_COUNT)]
    for symbol_id, (_, payouts) in DESIGN_PAYTABLE.items():
        prizes[symbol_id] = payout_row(payouts)

    lines = [
        "[MAIN]",
        "VERSION=101",
        "COL_COUNT=6",
        "ROW_COUNT=5",
        f"ITEM_COUNT={ITEM_COUNT}",
        "PRIZE_RATE=1",
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
        "USE_WILDS=" + ",".join("1" if 3 <= item <= 12 else "0" for item in range(ITEM_COUNT)),
        "BASE_NUMS=" + ",".join("5" if 3 <= item <= 12 else "0" for item in range(ITEM_COUNT)),
    ]
    lines.extend(f"ITEM_PRIZES_{item}=" + ",".join(map(str, row)) for item, row in enumerate(prizes))
    lines.extend(
        [
            "LINE_MODE=4",
            "SCATTER_MODE=0",
            "SCATTER_ID=0",
            "SCATTER_COLS=1,1,1,1,1,1",
            "SCATTER_SERIAL=0",
            "SCATTER_MULTIPLES=" + ",".join(["0"] * 30),
            "SCATTER_PRIZES=" + ",".join(["0"] * 30),
            "GRID_DISABLES=" + ",".join(["0"] * 30),
            "GRID_DISABLES_FREE=" + ",".join(["0"] * 30),
            "",
        ]
    )
    (THEME_DIR / "special" / "game_config.conf").write_text("\n".join(lines), encoding="utf-8")


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
    (target / f"{file_prefix}rand_main.conf").write_text(
        "\n".join(
            [
                "[MAIN]",
                "VERSION=101",
                "COL_COUNT=6",
                "ROW_COUNT=5",
                f"ITEM_COUNT={ITEM_COUNT}",
                "ITEM_COM_COUNT=1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    lines = [
        "[MAIN]",
        "VERSION=101",
        "",
        "[GENERAL_1]",
        "BASE_RATE=1000,0,0,0",
    ]
    lines.extend(f"NORMAL_ROLL_{index}=" + ",".join(map(str, reel)) for index, reel in enumerate(reels, 1))
    lines.extend(f"SP_ROLL_{index}=" + ",".join(map(str, reel)) for index, reel in enumerate(reels, 1))
    lines.extend(["FIX_DISORDER=0", "FIX_NUM=0", "ZERO_DISORDER=0", "ZERO_NUM=0", ""])
    (target / f"{file_prefix}rand_ex_0.conf").write_text("\n".join(lines), encoding="utf-8")


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
        },
        "paytable": paytable,
        "symbol_id_mapping": {
            "scatter": 0,
            "wild": 1,
            "golden_feature_symbols": 2,
            "paying_symbols": "3-12 (payout descending)",
            "super_scatter": 13,
        },
        "coin_values_x_bet": [0.2, 0.5, 1, 2, 3, 4, 5, 10, 15, 20, 25, 50, 100, 250, 500],
        "clover_multipliers": [2, 3, 4, 5, 10, 20],
        "fixed_jackpots_x_bet": {
            "mini": 10,
            "minor": 25,
            "major": 100,
            "grand": 5000,
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
            "Reference reel strips do not contain HGI feature-generation probabilities.",
            "Golden feature outcomes must be supplied by authoritative server data.",
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
    (THEME_DIR / "special" / "game_server.conf").write_text(
        "\n".join(
            [
                "[System Base Info]",
                "BetScopes = 100000,200000,500000,1000000,2000000,5000000,10000000,20000000",
                "",
                "[Game Info]",
                "Version=101",
                "GameId=362",
                "GameName=Si Botak Desa",
                "ClusterMinimum=5",
                "ScatterId=0",
                "SuperScatterId=13",
                "FeatureSymbolId=2",
                "FreeSpinCounts=10,10",
                "FreeSpinRetrigger=0,0,2,4",
                "JackpotMultiple=10,25,100,5000",
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
    write_reel_config(demo_dir, "reel_config", "default")
    write_reel_config(demo_dir, "free_reel_config", "fs", file_prefix="free_")
    write_metadata(demo_dir)


if __name__ == "__main__":
    main()
