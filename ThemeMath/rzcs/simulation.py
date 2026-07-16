"""Simulation entry for the rzcs line-game model."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from slots_simulation import simulation as SlotsSimulation

try:
    from .theme_math import ThemeMath
except ImportError:
    from theme_math import ThemeMath


SPIN_TIMES = 1000000
INDEX = [0]
GENERAL_INDEX = [1]
BASE_BETS = [10000]
REPORT_INTERVAL = 5000
THRESHOLDS = (5, 10, 20, 50, 100, 1000)
FREE_CHOOSE_INDEX = [1]
FREE_CHOOSE_TYPE_BY_INDEX = {
    1: "free",
    2: "super_free",
}
FREE_CHOOSE_INDEX_BY_TYPE = {value: key for key, value in FREE_CHOOSE_TYPE_BY_INDEX.items()}
FREE_TRIGGER_CHOICES = ("free", "super_free", "super_wild")
JP_TYPE_COUNT = 4
JP_TYPE_REPORT_FIELDS = tuple(
    field
    for index in range(JP_TYPE_COUNT)
    for field in (f"jp_type_{index}_count", f"jp_type_{index}_rate")
)
JP_TYPE_STATICS_FIELDS = [
    {"label": f"JP{index}次数", "key": f"jp_type_{index}_count"}
    if field_type == "count"
    else {"label": f"JP{index}频率", "key": f"jp_type_{index}_rate"}
    for index in range(JP_TYPE_COUNT)
    for field_type in ("count", "rate")
]
GENERAL_SECTION_RE = re.compile(r"^\s*\[GENERAL_(\d+)\]\s*$", re.MULTILINE)
RESULT_CSV = Path(__file__).resolve().with_name("simulate_result.csv")
RESULT_CSV_FIELDS = [
    "INDEX",
    "GENERAL",
    "FREE_GENERAL",
    "CHOOSE",
    "FREE_CHOOSE_INDEX",
    "CHOOSE_TYPE",
    "BASE_BET",
    "SPIN",
    "总押注",
    "rtp",
    "rtp_check",
    "base_rtp",
    "base_lines_rtp",
    "base_jp_rtp",
    "free_rtp",
    "free_lines_rtp",
    "free_jp_rtp",
    "总赢钱",
    "Line赢钱",
    "BaseLine",
    "FreeLine",
    "BaseJP",
    "FreeJP",
    *JP_TYPE_REPORT_FIELDS,
    "Hit",
    "Hit率",
    ">5x",
    ">10x",
    ">20x",
    ">50x",
    ">100x",
    ">1000x",
    "触发Free",
    "Free频率",
    "Free次数",
    "FreeSpin",
    "Free重触发",
    "Free平均次数",
    "Free平均倍",
    "main_win_times",
    "main_win_rate",
    "free_win_times",
    "free_win_rate",
    "ok",
    "错误",
    "status",
]


def first_config_value(value):
    """Return the first value from a scalar-or-list default config."""

    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError("default config list cannot be empty")
        return value[0]
    return value


def list_config_values(value) -> list:
    """Return a list from a scalar-or-list default config."""

    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def normalize_choice_type(choice_type: str) -> str:
    """Validate and normalize the configured free-trigger choice."""

    if choice_type not in FREE_TRIGGER_CHOICES:
        choices = ", ".join(FREE_TRIGGER_CHOICES)
        raise ValueError(f"choice_type must be one of: {choices}")
    if choice_type == "super_wild":
        return "super_free"
    return choice_type


def normalize_free_choose_index(free_choose_index: int) -> int:
    """Validate FREE_CHOOSE_INDEX where 1=free, 2=super free."""

    if free_choose_index not in FREE_CHOOSE_TYPE_BY_INDEX:
        choices = ", ".join(str(index) for index in FREE_CHOOSE_TYPE_BY_INDEX)
        raise ValueError(f"FREE_CHOOSE_INDEX must be one of: {choices}")
    return free_choose_index


def choice_type_from_free_choose_index(free_choose_index: int) -> str:
    """Resolve FREE_CHOOSE_INDEX into an internal choice type."""

    return FREE_CHOOSE_TYPE_BY_INDEX[normalize_free_choose_index(free_choose_index)]


def free_choose_index_from_choice_type(choice_type: str) -> int:
    """Resolve an internal choice type into FREE_CHOOSE_INDEX."""

    return FREE_CHOOSE_INDEX_BY_TYPE[normalize_choice_type(choice_type)]


def format_choice_type(choice_type: str) -> str:
    """Format choice type shown in reports."""

    return normalize_choice_type(choice_type)


def format_free_general_index(free_general_index: int | None, general_index: int):
    """Format the free GENERAL value shown in reports."""

    return general_index if free_general_index is None else free_general_index


def discover_general_indexes(index: int, free_game: bool = False) -> list[int]:
    """Discover GENERAL_n sections in the configured reel file."""

    m = ThemeMath()
    reel_dir = m.FREE_REEL_CONFIG_DIR if free_game else None
    path = m._find_reel_config_path(index, reel_config_dir=reel_dir)
    text = path.read_text(encoding="utf-8-sig")
    return sorted({int(match.group(1)) for match in GENERAL_SECTION_RE.finditer(text)})


def get_line_win(win_info: dict) -> int:
    """Return line win from a win_info payload."""

    if "line_win" in win_info:
        return int(win_info["line_win"])
    return sum(int(item.get("win", 0)) for item in win_info.get("win_items", []))


def get_free_times(win_info: dict) -> int:
    """Return awarded free spins for a win_info payload."""

    return int(win_info.get("free_times", 0)) if win_info.get("win_free") else 0


def resolve_free_trigger_choice(m: ThemeMath, win_info: dict, choice_type: str) -> dict:
    """Resolve one win_info trigger with the requested choice."""

    win_free_info = win_info.get("win_free_info", {})
    if not win_info.get("win_free"):
        choice_result = {"type": "none", "win_free": False}
    else:
        resolved_choice_type = normalize_choice_type(choice_type) if win_free_info.get("need_choice") else "free"
        choice_result = m.resolve_free_trigger_choice(win_free_info, resolved_choice_type)
    win_info["free_choice_result"] = choice_result
    return choice_result


def record_win_info(status: dict, win_info: dict, mode_key: str) -> int:
    """Record one ng/fg win_info into status and return total win."""

    total_win = int(win_info.get("total_win", 0))
    line_win = get_line_win(win_info)
    jp_win = int(win_info.get("jp_win", 0))
    status_handler.update_feature_win(status, mode_key, "lines", line_win)
    status_handler.update_feature_win(status, mode_key, "jp", jp_win)
    if win_info.get("win_jp"):
        win_jp_info = win_info.get("win_jp_info", {})
        jp_type_index = win_jp_info.get("jp_type_index", win_info.get("jp_type_index"))
        if not isinstance(jp_type_index, int) or not 0 <= jp_type_index < JP_TYPE_COUNT:
            raise ValueError(f"invalid jp_type_index: {jp_type_index}")
        status["jp_type_counts"][jp_type_index] += 1
    return total_win


def run_free_spins(
    m: ThemeMath,
    status: dict,
    index: int,
    free_times: int,
    free_mode: str = "free",
) -> int:
    """Consume free spins and return total free win."""

    remaining_free_times = free_times
    free_total_win = 0
    while remaining_free_times > 0:
        remaining_free_times -= 1
        status_handler.add_status_value(status, 1, "free", "spin")
        fg_info = m.fg_spin(index, return_detail=True, free_mode=free_mode)
        free_total_win += record_win_info(status, fg_info, "free")

        retrigger_times = get_free_times(fg_info)
        status_handler.update_free_trigger(status, "free", retrigger_times)
        remaining_free_times += retrigger_times

    return free_total_win


def apply_base_trigger_choice(
    m: ThemeMath,
    status: dict,
    index: int,
    win_info: dict,
    choice_type: str,
) -> int:
    """Apply the selected trigger option and return extra spin win."""

    choice_result = resolve_free_trigger_choice(m, win_info, choice_type)
    if choice_result["type"] == "free":
        free_times = int(choice_result.get("free_times", 0))
        status_handler.update_free_trigger(status, "base", free_times)
        return run_free_spins(m, status, index, free_times, free_mode="free")
    if choice_result["type"] == "super_free":
        free_times = int(choice_result.get("free_times", 0))
        status_handler.update_free_trigger(status, "base", free_times)
        return run_free_spins(m, status, index, free_times, free_mode="super_free")
    return 0


def build_simulation_row(
    status: dict,
    index: int,
    general_index: int,
    free_choose_index: int,
    choice_type: str,
    base_bet: int,
    free_general_index: int | None = None,
) -> dict:
    """Build one rzcs report row from current status."""

    row = status_handler.build_report_row(status)
    row["INDEX"] = index
    row["GENERAL"] = general_index
    row["FREE_GENERAL"] = format_free_general_index(free_general_index, general_index)
    row["CHOOSE"] = free_choose_index
    row["FREE_CHOOSE_INDEX"] = free_choose_index
    row["CHOOSE_TYPE"] = format_choice_type(choice_type)
    row["BASE_BET"] = base_bet
    row["错误"] = ""

    base_status = status["base"]
    free_status = status["free"]
    base_spin = base_status["spin"]
    free_trigger_count = base_status["free"]
    row["总押注"] = status["bet"]
    row["BaseJP"] = base_status["jp"][1]
    row["FreeJP"] = free_status["jp"][1]
    for jp_type_index, count in enumerate(status["jp_type_counts"]):
        row[f"jp_type_{jp_type_index}_count"] = count
        row[f"jp_type_{jp_type_index}_rate"] = count / base_spin if base_spin else 0
    row["Free平均次数"] = status["free_times"] / free_trigger_count if free_trigger_count else 0
    row["Free平均倍"] = (
        free_status["lines"][1] / free_trigger_count / base_bet
        if free_trigger_count and base_bet
        else 0
    )
    row["main_win_times"] = base_status["lines"][0]
    row["free_win_times"] = free_status["lines"][0]
    row["main_win_rate"] = base_status["lines"][0] / base_spin if base_spin else 0
    row["free_win_rate"] = (
        free_status["lines"][0] / free_status["spin"]
        if free_status["spin"]
        else 0
    )
    return row


def simulation(
    spin_times: int = SPIN_TIMES,
    index: int | None = None,
    general_index: int | None = None,
    free_choose_index: int | None = None,
    choice_type: str = "free",
    free_general_index: int | None = None,
    report_interval: int = REPORT_INTERVAL,
    base_bet: int | None = None,
    print_updates: bool = False,
) -> list[dict]:
    """Run N base spins and return cumulative checkpoint rows."""

    index = first_config_value(INDEX) if index is None else index
    base_bet = first_config_value(BASE_BETS) if base_bet is None else base_bet
    if free_choose_index is None:
        free_choose_index = free_choose_index_from_choice_type(choice_type)
    else:
        free_choose_index = normalize_free_choose_index(free_choose_index)
    choice_type = choice_type_from_free_choose_index(free_choose_index)
    m = ThemeMath(base_bet=base_bet)
    general_index = m.get_base_general_index()
    current_free_general_index = m.get_free_general_index(choice_type)
    status = status_handler.new_status()
    rows = []

    for _ in range(spin_times):
        status_handler.update_spin_start(status, m.base_bet)
        spin_total_win = 0

        win_info = m.ng_spin(index, return_detail=True)
        spin_total_win += record_win_info(status, win_info, "base")
        spin_total_win += apply_base_trigger_choice(
            m,
            status,
            index,
            win_info,
            choice_type,
        )

        status_handler.update_spin_result(status, spin_total_win, m.base_bet)

        base_spin = status["base"]["spin"]
        if report_interval > 0 and base_spin % report_interval == 0:
            row = build_simulation_row(
                status,
                index,
                general_index,
                free_choose_index,
                choice_type,
                base_bet,
                current_free_general_index,
            )
            rows.append(row)
            if print_updates:
                status_handler.print_table([row])

    if not rows or rows[-1]["SPIN"] != status["base"]["spin"]:
        rows.append(
            build_simulation_row(
                status,
                index,
                general_index,
                free_choose_index,
                choice_type,
                base_bet,
                current_free_general_index,
            )
        )
    rows[-1]["status"] = status
    return rows


def simulation_all(
    spin_times: int = SPIN_TIMES,
    indexes: list[int] | None = None,
    general_indexes: list[int] | None = None,
    free_choose_indexes: list[int] | None = None,
    choice_types: list[str] | None = None,
    free_general_indexes: list[int] | None = None,
    base_bets: list[int] | None = None,
    report_interval: int = REPORT_INTERVAL,
    print_updates: bool = True,
) -> list[dict]:
    """Run all index/general/choice combinations and return each final row."""

    results = []
    target_indexes = list_config_values(INDEX) if indexes is None else indexes
    if free_choose_indexes is None:
        target_free_choose_indexes = (
            [free_choose_index_from_choice_type(choice_type) for choice_type in choice_types]
            if choice_types is not None
            else list_config_values(FREE_CHOOSE_INDEX)
        )
    else:
        target_free_choose_indexes = free_choose_indexes
    target_base_bets = list_config_values(BASE_BETS) if base_bets is None else base_bets
    for base_bet in target_base_bets:
        for index in target_indexes:
            target_general_indexes = [None]
            for general_index in target_general_indexes:
                for free_choose_index in target_free_choose_indexes:
                    choice_type = ""
                    target_free_general_indexes = [None]
                    for free_general_index in target_free_general_indexes:
                        try:
                            choice_type = choice_type_from_free_choose_index(free_choose_index)
                            rows = simulation(
                                spin_times=spin_times,
                                index=index,
                                general_index=general_index,
                                free_choose_index=free_choose_index,
                                choice_type=choice_type,
                                free_general_index=free_general_index,
                                report_interval=report_interval if print_updates else 0,
                                base_bet=base_bet,
                                print_updates=print_updates,
                            )
                            if rows:
                                final_row = rows[-1]
                                final_row["ok"] = True
                                results.append(final_row)
                        except Exception as exc:
                            results.append(
                                {
                                    "ok": False,
                                    "INDEX": index,
                                    "GENERAL": general_index,
                                    "FREE_GENERAL": format_free_general_index(free_general_index, general_index),
                                    "CHOOSE": free_choose_index,
                                    "FREE_CHOOSE_INDEX": free_choose_index,
                                    "CHOOSE_TYPE": choice_type,
                                    "BASE_BET": base_bet,
                                    "SPIN": spin_times,
                                    "错误": str(exc),
                                }
                            )
    return results


def print_summary(result: dict | list[dict]) -> None:
    """Print a summary for the final row of one simulation."""

    if isinstance(result, list):
        result = result[-1] if result else {}
    if not result:
        return

    print(f"模拟次数: {result['SPIN']}")
    print(
        f"index: {result['INDEX']}, GENERAL_{result['GENERAL']}, "
        f"FREE_GENERAL_{result['FREE_GENERAL']}, FREE_CHOOSE_INDEX: {result['FREE_CHOOSE_INDEX']}, "
        f"choice_type: {result['CHOOSE_TYPE']}, "
        f"base_bet: {result['BASE_BET']}"
    )
    print(f"总押注: {result['总押注']}")
    print(f"普通游戏赢钱: {result['BaseLine']}")
    print(f"免费游戏赢钱: {result['FreeLine']}")
    print(f"JP赢钱: {result['BaseJP'] + result['FreeJP']}")
    for jp_type_index in range(JP_TYPE_COUNT):
        print(
            f"JP{jp_type_index}次数: {result[f'jp_type_{jp_type_index}_count']}, "
            f"频率: {result[f'jp_type_{jp_type_index}_rate']:.6%}"
        )
    print(f"总赢钱: {result['总赢钱']}")
    print(f"普通游戏 RTP: {result['base_rtp']:.3f}")
    print(f"免费游戏 RTP: {result['free_rtp']:.3f}")
    print(f"总 RTP: {result['rtp']:.3f}")
    print(f"RTP 校验: {result['rtp_check']:.3f}")
    print(f"赢钱次数: {result['Hit']}")
    print(f"赢钱率: {result['Hit率']:.3f}")
    print(f"普通游戏赢钱次数: {result['main_win_times']}")
    print(f"普通游戏赢钱率: {result['main_win_rate']:.3f}")
    print(f"免费游戏赢钱次数: {result['free_win_times']}")
    print(f"免费游戏赢钱率: {result['free_win_rate']:.3f}")
    print(f"触发 free 次数: {result['触发Free']}")
    print(f"free 中再次触发 free 次数: {result['Free重触发']}")
    print(f"触发 free 概率: {result['Free频率']:.3%}")
    print(f"免费游戏总次数: {result['FreeSpin']}")
    print(f"平均每次触发 free 次数: {result['Free平均次数']:.6f}")
    print(f"平均每次 free 赢钱倍数: {result['Free平均倍']:.3f}")


def print_table(results: list[dict]) -> None:
    """Print simulation rows as a table."""

    status_handler.print_table(results)


def format_csv_value(value):
    """Convert nested values into stable CSV cell text."""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def get_result_csv_fields(rows: list[dict], path: Path) -> list[str]:
    """Return the CSV field order, extending an existing file header if needed."""

    extra_fields = sorted(
        {
            key
            for row in rows
            for key in row
            if key not in RESULT_CSV_FIELDS
        }
    )
    default_fields = RESULT_CSV_FIELDS + extra_fields

    if path.exists() and path.stat().st_size > 0:
        with path.open("r", newline="", encoding="utf-8-sig") as file_obj:
            reader = csv.reader(file_obj)
            for header in reader:
                if header:
                    return header + [field for field in default_fields if field not in header]

    return default_fields


def update_result_csv_header(path: Path, fieldnames: list[str]) -> None:
    """Rewrite an existing CSV only when new fields need to be added."""

    if not path.exists() or path.stat().st_size == 0:
        return

    with path.open("r", newline="", encoding="utf-8-sig") as file_obj:
        reader = csv.DictReader(file_obj)
        existing_fieldnames = reader.fieldnames or []
        if existing_fieldnames == fieldnames:
            return
        rows = list(reader)

    with path.open("w", newline="", encoding="utf-8-sig") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def append_simulation_results(rows: list[dict], path: Path = RESULT_CSV) -> None:
    """Append completed simulation final rows to simulate_result.csv."""

    if not rows:
        return

    write_header = not path.exists() or path.stat().st_size == 0
    fieldnames = get_result_csv_fields(rows, path)
    if not write_header:
        update_result_csv_header(path, fieldnames)
    encoding = "utf-8-sig" if write_header else "utf-8"
    with path.open("a", newline="", encoding=encoding) as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: format_csv_value(row.get(key, "")) for key in fieldnames})


def parse_int_list(value: str | None) -> list[int] | None:
    """Parse comma-separated ints from CLI options."""

    if value is None:
        return None
    value = value.strip()
    if not value:
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_str_list(value: str | None) -> list[str] | None:
    """Parse comma-separated strings from CLI options."""

    if value is None:
        return None
    value = value.strip()
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run rzcs line-game simulation.")
    parser.add_argument("--spins", type=int, default=SPIN_TIMES, help="Base ng_spin count.")
    parser.add_argument("--indexes", default=None, help="Comma-separated reel indexes.")
    parser.add_argument("--generals", default=None, help="Comma-separated GENERAL indexes.")
    parser.add_argument("--free-generals", default=None, help="Comma-separated free GENERAL indexes.")
    parser.add_argument(
        "--free-choose-indexes",
        default=None,
        help="Comma-separated free choices: 1=free, 2=super free.",
    )
    parser.add_argument("--choices", default=None, help="Comma-separated choices: free,super_free.")
    parser.add_argument("--base-bets", default=None, help="Comma-separated base bets.")
    parser.add_argument("--base-bet", type=int, default=None, help="Single base bet, kept for compatibility.")
    parser.add_argument("--report-interval", type=int, default=REPORT_INTERVAL)
    parser.add_argument(
        "--no-print-updates",
        action="store_false",
        dest="print_updates",
        help="Skip interval statics tables while running.",
    )
    parser.set_defaults(print_updates=True)
    return parser.parse_args()


status_model = {
    "base": {
        "spin": 0,
        "lines": [0, 0],
        "jp": [0, 0],
        "free": 0,
    },
    "free": {
        "spin": 0,
        "lines": [0, 0],
        "jp": [0, 0],
        "free": 0,
    },
    "bet": 0,
    "wins": 0,
    "hit": 0,
    "free_times": 0,
    "jp_type_counts": [0] * JP_TYPE_COUNT,
    "gt_5x": 0,
    "gt_10x": 0,
    "gt_20x": 0,
    "gt_50x": 0,
    "gt_100x": 0,
    "gt_1000x": 0,
}

statics_columns = [
    {
        "title": "基础信息",
        "fields": [
            "INDEX",
            "GENERAL",
            "FREE_GENERAL",
            "CHOOSE",
            "FREE_CHOOSE_INDEX",
            "CHOOSE_TYPE",
            "BASE_BET",
            "SPIN",
            "总押注",
            "rtp",
            "rtp_check",
            "总赢钱",
            "Line赢钱",
            "Hit",
            "Hit率",
            ">5x",
            ">10x",
            ">20x",
            ">50x",
            ">100x",
            ">1000x",
            "错误",
        ],
    },
    {
        "title": "Base",
        "fields": [
            "base_rtp",
            "base_lines_rtp",
            "base_jp_rtp",
            "BaseLine",
            "BaseJP",
            *JP_TYPE_STATICS_FIELDS,
            "main_win_times",
            "main_win_rate",
        ],
    },
    {
        "title": "Free",
        "fields": [
            "free_rtp",
            "free_lines_rtp",
            "free_jp_rtp",
            "FreeLine",
            "FreeJP",
            "free_win_times",
            "free_win_rate",
            "触发Free",
            "Free频率",
            "Free次数",
            "FreeSpin",
            "Free重触发",
            "Free平均次数",
            "Free平均倍",
        ],
    },
]

status_handler = SlotsSimulation(
    status_model=status_model,
    thresholds=THRESHOLDS,
    feature_key="lines",
    feature_label="Line",
    print_mode="statics",
    statics_columns=statics_columns,
)


if __name__ == "__main__":
    args = parse_args()
    base_bets = parse_int_list(args.base_bets)
    if base_bets is None and args.base_bet is not None:
        base_bets = [args.base_bet]
    results = simulation_all(
        spin_times=args.spins,
        indexes=parse_int_list(args.indexes),
        general_indexes=parse_int_list(args.generals),
        free_choose_indexes=parse_int_list(args.free_choose_indexes),
        choice_types=parse_str_list(args.choices),
        free_general_indexes=parse_int_list(args.free_generals),
        base_bets=base_bets,
        report_interval=args.report_interval,
        print_updates=args.print_updates,
    )
    print_table(results)
    append_simulation_results(results)
