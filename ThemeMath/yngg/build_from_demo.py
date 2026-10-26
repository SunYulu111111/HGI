"""Build Si Botak Desa (yngg) configuration from reference reel data.

The Le King extract supplies reference reel strips. Game rules, IDs, payouts,
free modes and jackpots follow the HGI Si Botak Desa design specification.
Golden-area generation uses the explicit weights in yngg_bonus.conf.
"""

from __future__ import annotations

import argparse
from collections import Counter
from configparser import ConfigParser
import csv
import json
import re
import shutil
from pathlib import Path


THEME_DIR = Path(__file__).resolve().parent
MODEL_DIR = THEME_DIR.parent / "model_countgame"
DEFAULT_DEMO_DIR = Path(r"C:\Users\sunyulu\le-king-demo-extract")
BET_UNIT = 10_000
ITEM_COUNT = 13
MaxReelBytes = 399
ConfiguredTypes = (0, 4, 8, 12, 17)
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


def fit_server_reel(reel: list[int]) -> list[int]:
    """Keep symbol proportions and cyclic order within both server limits."""

    if not reel or any(not 0 <= symbol < ITEM_COUNT for symbol in reel):
        raise ValueError("reel must contain valid symbol IDs")
    if len(reel) <= 200 and len(",".join(map(str, reel)).encode("utf-8")) <= MaxReelBytes:
        return list(reel)
    counts = Counter(reel)
    for size in range(min(200, len(reel)), len(counts) - 1, -1):
        quotas = {symbol: 1 for symbol in counts}
        for _ in range(size - len(counts)):
            symbol = max(
                counts,
                key=lambda item: (size * counts[item] / len(reel) - quotas[item], -item),
            )
            quotas[symbol] += 1
        seen = Counter()
        result = []
        for symbol in reel:
            before = seen[symbol] * quotas[symbol] // counts[symbol]
            seen[symbol] += 1
            if seen[symbol] * quotas[symbol] // counts[symbol] > before:
                result.append(symbol)
        if len(",".join(map(str, result)).encode("utf-8")) <= MaxReelBytes:
            return result
    raise ValueError("cannot fit reel within server limits")


def fit_existing_reel_file(path: Path) -> None:
    """Shorten overlong roll values without replacing TYPE-specific tuning."""

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    changed = False
    for index, line in enumerate(lines):
        updated = line.replace("字符串不超过500字符", "轴值小于400字节")
        updated = updated.replace("轴值不超过400字节", "轴值小于400字节")
        if updated != line:
            lines[index] = line = updated
            changed = True
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"(?:NORMAL|SP)_ROLL_[1-6]", key.strip()):
            continue
        roll_value = value.rstrip("\r\n")
        if len(roll_value.encode("utf-8")) <= MaxReelBytes:
            continue
        symbols = [int(symbol.strip()) for symbol in roll_value.split(",")]
        newline = value[len(roll_value):]
        lines[index] = f"{key}={','.join(map(str, fit_server_reel(symbols)))}{newline}"
        changed = True
    if changed:
        path.write_text("".join(lines), encoding="utf-8")


def write_control_groups() -> None:
    """Publish every configured TYPE and its GROUP cutoff."""

    path = THEME_DIR / "special_config" / "slot_control_group.conf"
    existing_groups = {}
    if path.exists():
        old_lines = path.read_text(encoding="utf-8-sig").splitlines()
        for position, line in enumerate(old_lines):
            match = re.fullmatch(r"\[CONTROL_GROUP_(\d+)\]", line.strip())
            if match and int(match.group(1)) in ConfiguredTypes:
                end = next((offset for offset in range(position + 1, len(old_lines))
                            if old_lines[offset].strip().startswith("[")), len(old_lines))
                existing_groups[int(match.group(1))] = old_lines[position:end]
    thresholds = [5000, 0, 0, 0, 12000, 0, 0, 0, 1000,
                  0, 0, 0, 20, 0, 0, 0, 0, 1000]
    values = ",".join(map(str, thresholds))
    lines = [
        "[MAIN]", "version = 101",
        "#按GROUP 0-17排列；未启用组保留0",
        f"control_group_cut_multiple = {values}",
        f"control_group_free_cut_multiple = {values}", "",
    ]
    for type_index in ConfiguredTypes:
        lines.extend(existing_groups.get(type_index, [
            f"[CONTROL_GROUP_{type_index}]",
            "lable_user_control_group_rate = 10000",
            f"lable_user_control_group_value = {type_index * 100 + 1}", "",
        ]))
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def fix_replay_threshold() -> None:
    path = THEME_DIR / "special_config" / "game_server.conf"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = ["replay_min_win_money = 3000000000"
             if line.split("=", 1)[0].strip() == "replay_min_win_money" else line
             for line in lines]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_model_layout() -> None:
    for directory in ("general_config", "special_config"):
        destination = THEME_DIR / directory
        if not destination.exists():
            shutil.copytree(MODEL_DIR / directory, destination)
            for path in destination.rglob("*.conf"):
                content = path.read_bytes()
                content = re.sub(
                    rb"(?im)^([ \t]*version[ \t]*=[ \t]*)[0-9]+\b",
                    lambda match: match[1] + b"101",
                    content,
                )
                path.write_bytes(content)
    write_control_groups()
    fix_replay_threshold()
    (THEME_DIR / "special").mkdir(exist_ok=True)
    control_path = THEME_DIR / "special" / "yngg_control.conf"
    if not control_path.exists():
        control_path.write_text(
            "\n".join(
                [
                    "[MAIN]",
                    "#控制配置版本",
                    "version = 101",
                    "#暂未分配内部控制ID，因此不启用控制项",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    else:
        content = control_path.read_text(encoding="utf-8")
        content = re.sub(r"(?m)^(lable_user_bet_money\s*=\s*)80000\s*$",
                         r"\g<1>100000", content)
        if content != control_path.read_text(encoding="utf-8"):
            control_path.write_text(content, encoding="utf-8")
    prop_path = THEME_DIR / "special" / "slot_prop_config.conf"
    if not prop_path.exists():
        prop_path.write_text(
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
        "#symbol ID范围为0-12；Super Scatter沿用Scatter ID 0，通过位置状态区分",
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
            "LINE_MODE=5",
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
    """Preserve GENERAL and named Type0 tuning; remove legacy numeric sections."""

    BonusPath = THEME_DIR / "special" / "yngg_bonus.conf"
    if BonusPath.exists():
        Content = BonusPath.read_bytes().decode("utf-8")
        SharedLines = []
        InTypeSection = False
        for Line in Content.splitlines(keepends=True):
            Match = re.fullmatch(r"\s*\[([^\]]+)\]\s*(?:[#;].*)?", Line.lstrip("\ufeff").strip())
            if Match:
                InTypeSection = Match.group(1).strip().isdecimal()
            if not InTypeSection:
                SharedLines.append(Line)
        SharedContent = "".join(SharedLines)
        if SharedContent != Content:
            BonusPath.write_bytes(SharedContent.encode("utf-8"))
        return

    lines = [
        "[GENERAL]",
        "# 通用Bonus配置。先应用Game Info共享上限与coin保底，非强制coin时先抽类型再抽档位。",
        "# 档位数组与权重数组按相同下标一一对应；权重为相对权重，不要求总和为10000。",
        "",
        "# JP固定倍数，顺序为MINI、MINOR、MAJOR、GRAND。",
        "BONUS_MINI_MULTI=10",
        "BONUS_MINOR_MULTI=25",
        "BONUS_MAJOR_MULTI=100",
        "BONUS_GRAND_MULTI=5000",
        "BONUS_JP_MULTIPLE=10,25,100,5000",
        "# JP档位权重，与BONUS_JP_MULTIPLE按下标对应。",
        "BONUS_JP_TYPE_PROBABILITY=80,25,8,1",
        "",
        "# 金色框位置类型固定按金币/四叶草/聚宝盆/JP排列，权重按该顺序对应。",
        "BONUS_SYMBOL_TYPE_PROBABILITY=1000,80,6,2",
        "",
        "# 金币档位及对应权重，两个数组按下标对应。",
        "BONUS_COIN_MULTIPLE=0.2,0.5,1,2,3,4,5,10,15,20,25,50,100,250,500",
        "BONUS_COIN_MULTIPLE_PROBABILITY=1560,1240,1030,860,720,545,415,320,228,165,110,62,31,10,3",
        "",
        "# 四叶草倍数档位及对应权重，两个数组按下标对应。",
        "BONUS_CLOVER_MULTIPLE=2,3,4,5,10,20",
        "BONUS_CLOVER_MULTIPLE_PROBABILITY=40,28,16,10,5,1",
        "",
    ]
    BonusPath.write_text(
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
    target.mkdir(exist_ok=True)
    reels = [fit_server_reel(reel) for reel in load_strip(demo_dir, strip_name)]
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
                "#symbol总数（ID 0-12；Super Scatter沿用Scatter ID 0）",
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
        "#按图标占比分配保留数量并均匀删减；每轴最多200个物件且轴值小于400字节",
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
            "#每盘前五列底部组成5连Cluster以生成金色区域，同时保留一个Bonus ID 2",
            "ZERO_DISORDER=0",
            f"ZERO_NUM={len(zero_results)}",
        ]
    )
    lines.extend(
        f"ZERO_RESULT_{index}=" + ",".join(map(str, result))
        for index, result in enumerate(zero_results, 1)
    )
    lines.append("")
    type_zero_path = target / f"yngg_{file_prefix}rand_ex_0.conf"
    if type_zero_path.exists():
        fit_existing_reel_file(type_zero_path)
    else:
        type_zero_path.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )
    for type_index in ConfiguredTypes[1:]:
        type_path = target / f"yngg_{file_prefix}rand_ex_{type_index}.conf"
        if not type_path.exists():
            type_path.write_bytes(type_zero_path.read_bytes())
        else:
            fit_existing_reel_file(type_path)


def migrate_type_zero_server_config(Content: str) -> str:
    """Fill missing Game Info fields from legacy TYPE 0 and retain published values."""

    Lines = Content.splitlines(keepends=True)
    Sections = []
    for Position, Line in enumerate(Lines):
        Match = re.fullmatch(r"\s*\[([^\]]+)\]\s*", Line.strip())
        if Match:
            Sections.append((Position, Match.group(1)))
    ZeroStart = next((Position for Position, Name in Sections if Name == "0"), None)
    if ZeroStart is None:
        return Content
    if not any(Name == "Game Info" for _, Name in Sections):
        raise ValueError("cannot migrate TYPE [0] without [Game Info]")
    ZeroEnd = next((Position for Position, _ in Sections if Position > ZeroStart), len(Lines))
    ZeroLines = Lines[ZeroStart + 1:ZeroEnd]

    def AssignmentKey(Line: str) -> str | None:
        Stripped = Line.lstrip()
        if Stripped.startswith(("#", ";")) or "=" not in Stripped:
            return None
        return Stripped.split("=", 1)[0].strip()

    InfoStart = next(Position for Position, Name in Sections if Name == "Game Info")
    InfoEnd = next((Position for Position, _ in Sections if Position > InfoStart), len(Lines))
    InfoKeys = {AssignmentKey(Line) for Line in Lines[InfoStart + 1:InfoEnd]} - {None}
    MigratedLines = [Line for Line in ZeroLines if AssignmentKey(Line) not in InfoKeys]
    Result = Lines[:Sections[0][0]]
    for SectionIndex, (Start, Name) in enumerate(Sections):
        End = Sections[SectionIndex + 1][0] if SectionIndex + 1 < len(Sections) else len(Lines)
        if Name == "0":
            continue
        Block = Lines[Start:End]
        if Name == "Game Info":
            if Block and not Block[-1].endswith(("\r", "\n")):
                Block[-1] += "\n"
            Block.extend(MigratedLines)
            if Block and not Block[-1].endswith(("\r", "\n")):
                Block[-1] += "\n"
        Result.extend(Block)
    return "".join(Result)


def ensure_bonus_rule_fields(Content: str) -> str:
    """Add shared reveal limits without replacing explicit published values."""

    Config = ConfigParser(interpolation=None)
    Config.optionxform = str
    Config.read_string(Content)
    if not Config.has_section("Game Info"):
        raise ValueError("cannot add Bonus reveal limits without [Game Info]")
    General = Config["Game Info"]
    Defaults = {
        "BonusMaxPotCount": General.get("bonus_max_round", "5"),
        "BonusMaxCloverCount": "3",
        "BonusRevealMinCoinCount": "1",
    }
    Missing = [f"{Key}={Value}\n" for Key, Value in Defaults.items() if Key not in General]
    if not Missing:
        return Content
    Lines = Content.splitlines(keepends=True)
    InfoStart = next(Index for Index, Line in enumerate(Lines)
                     if re.fullmatch(r"\s*\[Game Info\]\s*", Line.strip()))
    InfoEnd = next((Index for Index in range(InfoStart + 1, len(Lines))
                    if re.fullmatch(r"\s*\[[^\]]+\]\s*", Lines[Index].strip())), len(Lines))
    if InfoEnd > 0 and not Lines[InfoEnd - 1].endswith(("\r", "\n")):
        Lines[InfoEnd - 1] += "\n"
    Lines[InfoEnd:InfoEnd] = ["#所有TYPE共用：整轮Pot/Clover上限及每批新翻格的最少coin数\n", *Missing]
    return "".join(Lines)


def update_type_zero_metadata(Metadata: dict) -> None:
    """Read the published TYPE 0 parameters after preserving tuned configs."""

    Metadata["math_targets"]["CalibrationStatus"] = "HistoricalFullTargetsNotRetuned"
    Metadata["bonus_generation"]["CurrentCalibrationReport"] = "bonus_type_calibration.json"
    Server = ConfigParser(interpolation=None)
    Bonus = ConfigParser(interpolation=None)
    Server.optionxform = str
    Bonus.optionxform = str
    Server.read(THEME_DIR / "special/yngg_game_server.conf", encoding="utf-8-sig")
    Bonus.read(THEME_DIR / "special/yngg_bonus.conf", encoding="utf-8-sig")
    if Server.has_section("Game Info"):
        TypeZero = Server["Game Info"]
        Fields = (
            ("scatter_count_weights", "ScatterCountProbability"),
            ("free_scatter_count_weights", "FreeScatterCountProbability"),
            ("base_no_win_bonus_count_weights", "BaseNoWinBonusCountProbability"),
            ("base_win_bonus_count_weights", "BaseWinBonusCountProbability"),
            ("free_golden_bonus_count_weights", "FreeGoldenBonusCountProbability"),
            ("free_no_golden_bonus_count_weights", "FreeNoGoldenBonusCountProbability"),
            ("drop_special_symbol_weights", "DropSpecialSymbolProbability"),
            ("free_drop_special_symbol_weights", "FreeDropSpecialSymbolProbability"),
        )
        for Field, Key in Fields:
            Metadata["special_symbol_generation"][Field] = [
                int(Value.strip()) for Value in TypeZero[Key].split(",")
            ]
        Probability = int(TypeZero["SuperScatterProbability"])
        Metadata["super_scatter_conversion"]["probability_per_10000"] = Probability
        Metadata["super_scatter_conversion"]["probability"] = str(Probability / 10000)
        Metadata["special_symbol_generation"]["ConfigSection"] = "Game Info"
        MaxPotCount = int(TypeZero.get("BonusMaxPotCount", TypeZero.get("bonus_max_round", "5")))
        Metadata["bonus_generation"].update({
            "maximum_pot_count": MaxPotCount,
            "BonusMaxPotCount": MaxPotCount,
            "BonusMaxCloverCount": int(TypeZero.get("BonusMaxCloverCount", "3")),
            "BonusRevealMinCoinCount": int(TypeZero.get("BonusRevealMinCoinCount", "1")),
            "RuleConfigSection": "Game Info",
            "RulesSharedAcrossTypes": True,
            "LimitCountScope": "EntireFeature",
            "LimitResetScope": "EachGoldenFeatureTrigger",
            "SuperFreeGoldenPersistenceCarriesCounts": False,
            "RevealMinCoinScope": "EachNewRevealBatch",
            "RetainedPotsCountAsCoin": False,
            "RevealScanOrder": "RowAscendingThenColAscending",
            "TypeLimitEnforcement": "BeforeEachSymbolDraw",
            "CoinGuaranteeMode": "ForceCoinWhenCoinMinimumDueOrAllowedTypeWeightsZero",
            "ForcedCoinTypeDrawSkipped": True,
            "ForcedCoinTierDrawPreserved": True,
        })
    Metadata["super_scatter_conversion"]["free_initial_rolls"] = 0
    Metadata["super_scatter_conversion"]["free_drop_scatter_rolls_when_no_super"] = False
    Metadata["special_symbol_generation"].update({
        "BaseBonusRequiresBaseCascade": True,
        "BaseNoWinBonusIsDisplayOnly": True,
        "BaseBonusTriggerDenominator": "PaidBaseSpins",
        "FreeInitialBonusMaxScatterCount": 2,
        "FreeBonusGuaranteeStage": "FinalBoard",
        "FreeBonusGuaranteeRequiresUnseen": True,
        "FreeBonusGuaranteeRemainingSpins": 1,
    })
    MainReelPath = THEME_DIR / "reel_config/yngg_rand_ex_0.conf"
    if MainReelPath.exists():
        MainReel = ConfigParser(interpolation=None)
        MainReel.optionxform = str
        MainReel.read(MainReelPath, encoding="utf-8-sig")
        BaseSourceWeights = [
            int(Value.strip()) for Value in MainReel["GENERAL_1"]["BASE_RATE"].split(",")
        ]
        Metadata["special_symbol_generation"]["BaseSourceWeights"] = BaseSourceWeights
        Metadata["special_symbol_generation"]["BaseBonusEntrance"] = (
            "ZeroPreset" if BaseSourceWeights[3] > 0 else "SpecialSymbolGeneration"
        )
        FirstPreset = MainReel["GENERAL_1"].get("ZERO_RESULT_1", "")
        PresetCounts = Counter(int(Value.strip()) for Value in FirstPreset.split(",") if Value.strip())
        Metadata["special_symbol_generation"]["BaseBonusPresetGoldenCount"] = max(
            (Count for Symbol, Count in PresetCounts.items() if 3 <= Symbol < ITEM_COUNT),
            default=0,
        )
    Metadata["bonus_generation"]["SymbolTypeOrderFixed"] = True
    if Bonus.has_section("GENERAL"):
        General = Bonus["GENERAL"]
        TypeZero = Bonus["Type0"] if Bonus.has_section("Type0") else {}
        GeneralSharedWeights = {}
        for Field, GeneralKey, TypeKey in (
            ("symbol_type_weights", "BONUS_SYMBOL_TYPE_PROBABILITY", "BonusSymbolTypeProbability"),
            ("coin_value_weights", "BONUS_COIN_MULTIPLE_PROBABILITY", "BonusCoinMultipleProbability"),
            ("clover_multiplier_weights", "BONUS_CLOVER_MULTIPLE_PROBABILITY", "BonusCloverMultipleProbability"),
            ("jackpot_type_weights", "BONUS_JP_TYPE_PROBABILITY", "BonusJpTypeProbability"),
        ):
            GeneralSharedWeights[TypeKey] = [
                int(Value.strip()) for Value in General[GeneralKey].split(",")
            ]
            EffectiveValue = TypeZero.get(TypeKey, General[GeneralKey])
            Metadata["bonus_generation"][Field] = [
                int(Value.strip()) for Value in EffectiveValue.split(",")
            ]
        Metadata["bonus_generation"]["GeneralSharedWeights"] = GeneralSharedWeights
        HasTypeZero = Bonus.has_section("Type0")
        if HasTypeZero:
            Metadata["bonus_generation"]["TypeIndex"] = 0
        else:
            Metadata["bonus_generation"].pop("TypeIndex", None)
        Metadata["bonus_generation"]["ConfigSectionOrder"] = (
            ["GENERAL", "Type0"] if HasTypeZero else ["GENERAL"]
        )
        Metadata["bonus_generation"]["SharedAcrossTypes"] = not HasTypeZero


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
        "math_targets": {
            "total_rtp": 0.95,
            "BaseClusterRtp": 0.45,
            "BaseBonusRtp": 0.20,
            "FreeClusterRtp": 0.073,
            "FreeBonusRtp": 0.18,
            "SuperFreeClusterRtp": 0.007,
            "SuperFreeBonusRtp": 0.04,
            "NormalFreeTriggerRate": 0.005,
            "SuperFreeTriggerRate": 0.0005,
            "BaseBonusTriggerRate": 0.0125,
            "free_trigger_rate": 0.0055,
            "base_bonus_trigger_interval": 80,
            "NormalFreeRtp": 0.253,
            "SuperFreeRtp": 0.047,
            "RtpDenominator": "PaidBaseBet",
            "FreeModesReportedSeparately": True,
            "CalibrationStatus": "HistoricalFullTargetsNotRetuned",
            "HistoricalCalibrationDate": "2026-10-22",
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
            "super_scatter": 0,
            "super_scatter_distinction": "position_state",
        },
        "super_scatter_conversion": {
            "probability": "1/50",
            "probability_per_10000": 200,
            "maximum_conversions_per_spin": 1,
            "base_initial_rolls": 1,
            "base_drop_scatter_rolls_when_no_super": True,
            "free_initial_rolls": 1,
            "free_drop_scatter_rolls_when_no_super": True,
        },
        "special_symbol_generation": {
            "scatter_count_weights": [10000, 1000, 500, 57],
            "free_scatter_count_weights": [10000, 1000, 500, 57],
            "base_no_win_bonus_count_weights": [98, 2],
            "base_win_bonus_count_weights": [92, 8],
            "base_bonus_max_scatter_count": 2,
            "base_bonus_blocks_future_drop_specials": True,
            "base_drop_max_special_symbols_per_cascade": 1,
            "base_drop_requires_scatter_count_below": 3,
            "free_drop_max_special_symbols_per_cascade": 1,
            "free_drop_requires_scatter_count_below": 3,
            "free_golden_bonus_count_weights": [60, 40],
            "free_no_golden_bonus_count_weights": [30, 70],
            "drop_special_symbol_weights": [998, 1, 1],
            "free_drop_special_symbol_weights": [998, 1, 1],
            "free_bonus_guaranteed": True,
            "free_bonus_no_candidate": "skip",
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
            "symbol_type_weights": [1000, 80, 6, 2],
            "coin_value_weights": [1560, 1240, 1030, 860, 720, 545, 415, 320, 228, 165, 110, 62, 31, 10, 3],
            "coin_tier_thresholds": [5, 25],
            "clover_multiplier_weights": [40, 28, 16, 10, 5, 1],
            "jackpot_type_weights": [80, 25, 8, 1],
            "maximum_pot_count": 5,
            "pot_overflow": "exclude_before_type_draw",
        },
        "free_games": {
            "free": {"trigger": "3 scatters", "spins": 10},
            "super_free": {"trigger": "2 scatters + 1 super scatter", "spins": 10},
            "retrigger": {"2_scatters": 2, "3_scatters": 4},
            "initial_golden_squares": [],
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
    server_path = THEME_DIR / "special" / "yngg_game_server.conf"
    server_lines = [
                "[System Base Info]",
                "#相同配置",
                "AutoSpinTimes = 10,100,500,-1,-2",
                "#第四个参数为super洗分匀速到加速的临界值",
                "BigWinGrade = 10,20,50",
                "NewBigWinGrade = 5,10,20,50,100,500",
                "BetPerReel = 1,1,1,1,1,1,1,1,1",
                "#支持的下注档位",
                "BetScopes = 10,20,50,100,200,500,1000,2000,2500",
                "",
                "#底分",
                "BaseScore = 10000",
                "#解锁押注配置(注册时间+玩家等级+玩家VIP等级)",
                "#解锁押注注册时间,在此时间之后注册的才走配置",
                "#解锁押注玩家等级,达到等级解锁(VIP等级满足此项不生效)",
                "#解锁押注玩家VIP等级,达到等级解锁(不需要判断玩家等级)",
                "BetUnLockRegTime = 2000/09/09 08:00:00",
                "BetUnLockLevel = 5,5,5,5,5,5,5,5,0",
                "BetUnLockVip = 0,0,0,0,0,0,0,0,2",
                "",
                "[Game Info]",
                "#配置文件版本",
                "Version=104",
                "#Super Scatter沿用Scatter ID 0，通过位置状态区分，不配置专门ID",
                "#普通免费、超级免费初始次数",
                "FreeSpinCounts=10,10",
                "#下标为Scatter数量；2个追加2次，3个追加4次",
                "FreeSpinRetrigger=0,0,2,4",
                "#金币颜色分档：小于5为铜币，小于25为银币，其余为金币",
                "coin_multi_1=5",
                "coin_multi_2=25",
                "#兼容旧字段；仅BonusMaxPotCount缺失时作为聚宝盆上限fallback",
                "bonus_max_round=5",
                "#所有TYPE共用；整轮金色玩法累计Pot/Clover上限",
                "BonusMaxPotCount=5",
                "BonusMaxCloverCount=3",
                "#每批首次翻牌或重翻的新symbols至少包含的coin数；保留Pot不计入",
                "BonusRevealMinCoinCount=1",
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
                "#TYPE 0的主游戏与免费游戏特殊图标生成参数",
                "#Base初始及掉落Scatter使用；已有Super时不再转化，Free不生成Super，200/10000=1/50",
                "SuperScatterProbability=200",
                "#Scatter出现数量权重，下标0-3分别表示出现0-3个",
                "ScatterCountProbability=10000,1000,500,57",
                "#Free Scatter出现数量权重，下标0-3分别表示出现0-3个",
                "FreeScatterCountProbability=10000,1000,500,57",
                "#Base中Scatter数量小于等于2且无奖时，Bonus数量0/1的权重",
                "BaseNoWinBonusCountProbability=98,2",
                "#Base中Scatter数量小于等于2且有奖时，Bonus数量0/1的权重；配合中奖率使金色玩法约1/75",
                "BaseWinBonusCountProbability=92,8",
                "#Free Scatter数量不超过2且已有金框时，Bonus数量0/1的权重",
                "FreeGoldenBonusCountProbability=60,40",
                "#Free Scatter数量不超过2且没有金框时，Bonus数量0/1的权重",
                "FreeNoGoldenBonusCountProbability=30,70",
                "#掉落图标替换结果权重：不替换/Scatter/Bonus；Base每轮掉落至多放置1个",
                "DropSpecialSymbolProbability=998,1,1",
                "#Free掉落图标替换结果权重：不替换/Scatter/Bonus；每轮掉落至多放置1个",
                "FreeDropSpecialSymbolProbability=998,1,1",
                "",
            ]
    type_start = server_lines.index("#TYPE 0的主游戏与免费游戏特殊图标生成参数")
    type_template = server_lines[type_start:]
    if server_path.exists():
        Original = server_path.read_text(encoding="utf-8-sig")
        Content = migrate_type_zero_server_config(Original)
        Existing = ConfigParser(interpolation=None)
        Existing.read_string(Content)
    else:
        Original = None
        Content = "\n".join(server_lines).rstrip() + "\n"
        Existing = ConfigParser(interpolation=None)
        Existing.read_string(Content)
    Content = ensure_bonus_rule_fields(Content)
    for type_index in ConfiguredTypes:
        if type_index != 0 and not Existing.has_section(str(type_index)):
            Content = Content.rstrip() + "\n\n" + "\n".join(
                [f"[{type_index}]"] + [
                    line.replace("#TYPE 0的", f"#TYPE {type_index}的")
                    for line in type_template
                ]
            ).rstrip() + "\n"
    if Content != Original:
        server_path.write_text(Content, encoding="utf-8")
    update_type_zero_metadata(metadata)
    (THEME_DIR / "source_math.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
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
