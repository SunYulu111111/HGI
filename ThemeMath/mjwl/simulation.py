"""Simulation entry for the mjwl ways game."""

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


m = ThemeMath()

SPIN_TIMES = 100000
INDEX = [1]
GENERAL_INDEX = [1]
REPORT_INTERVAL = 5000
THRESHOLDS = (5, 10, 20, 50, 100, 1000)
CHOOSE_INDEXES = [1]
GENERAL_SECTION_RE = re.compile(r"^\s*\[GENERAL_(\d+)\]\s*$", re.MULTILINE)
RESULT_CSV = Path(__file__).resolve().with_name("simulate_result.csv")
RESULT_CSV_FIELDS = [
    "INDEX",
    "GENERAL",
    "FREE_GENERAL",
    "CHOOSE",
    "SPIN",
    "总押注",
    "rtp",
    "rtp_check",
    "base_rtp",
    "base_ways_rtp",
    "free_rtp",
    "free_ways_rtp",
    "总赢钱",
    "Ways赢钱",
    "BaseWays",
    "FreeWays",
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


def resolve_free_general_index(
    choose_index: int,
    free_choice: dict | None = None,
    free_general_index: int | None = None,
) -> int:
    """Choose which free GENERAL to use for the current free trigger."""

    if free_general_index is not None:
        return int(free_general_index)
    if choose_index == m.RANDOM_CHOOSE_INDEX and free_choice is not None:
        return int(free_choice.get("free_index", int(free_choice.get("multiplier_index", 0)) + 1))
    return int(choose_index)


def format_free_general_index(
    choose_index: int,
    free_general_index: int | None = None,
    used_free_general_indexes: list[int] | None = None,
):
    """Format the free GENERAL value shown in reports."""

    if free_general_index is not None:
        return free_general_index
    if choose_index == m.RANDOM_CHOOSE_INDEX:
        if used_free_general_indexes:
            used_values = sorted(set(used_free_general_indexes))
            return "|".join(str(value) for value in used_values)
        return "random_multiplier"
    return choose_index


def discover_general_indexes(index: int) -> list[int]:
    """Discover GENERAL_n sections from the normal reel file."""

    path = m._find_reel_config_path(index)
    text = path.read_text(encoding="utf-8-sig")
    return sorted({int(match.group(1)) for match in GENERAL_SECTION_RE.finditer(text)})


def record_win_info(status: dict, win_info: dict, mode_key: str) -> int:
    """Record one ng/fg ways win into status and return total win."""

    total_win = int(win_info.get("total_win", 0))
    status_handler.update_feature_win(status, mode_key, "ways", total_win)
    return total_win


def run_free_spins(
    status: dict,
    index: int,
    free_general_index: int,
    choose_index: int,
    free_choice: dict | None,
    free_times: int,
) -> int:
    """Consume free spins and return total free win."""

    remaining_free_times = free_times
    free_total_win = 0
    while remaining_free_times > 0:
        remaining_free_times -= 1
        status_handler.add_status_value(status, 1, "free", "spin")
        fg_result = m.fg_spin(
            index,
            free_general_index=free_general_index,
            choose_index=choose_index,
            free_choice=free_choice,
        )
        free_total_win += record_win_info(status, fg_result, "free")

        retrigger_times = int(fg_result.get("free_times", 0))
        status_handler.update_free_trigger(status, "free", retrigger_times)
        remaining_free_times += retrigger_times

    return free_total_win


def build_simulation_row(
    status: dict,
    index: int,
    general_index: int,
    choose_index: int,
    free_general_index: int | None = None,
    used_free_general_indexes: list[int] | None = None,
) -> dict:
    """Build one mjwl report row from current status."""

    row = status_handler.build_report_row(status)
    row["INDEX"] = index
    row["GENERAL"] = general_index
    row["FREE_GENERAL"] = format_free_general_index(
        choose_index,
        free_general_index=free_general_index,
        used_free_general_indexes=used_free_general_indexes,
    )
    row["CHOOSE"] = choose_index
    row["错误"] = ""

    base_spin = status["base"]["spin"]
    base_bet = status["bet"] / base_spin if base_spin else 0
    free_trigger_count = status["base"]["free"]
    row["总押注"] = status["bet"]
    row["Free平均次数"] = status["free_times"] / free_trigger_count if free_trigger_count else 0
    row["Free平均倍"] = (
        status["free"]["ways"][1] / free_trigger_count / base_bet
        if free_trigger_count and base_bet
        else 0
    )
    row["main_win_times"] = status["base"]["ways"][0]
    row["free_win_times"] = status["free"]["ways"][0]
    row["main_win_rate"] = status["base"]["ways"][0] / base_spin if base_spin else 0
    row["free_win_rate"] = (
        status["free"]["ways"][0] / status["free"]["spin"]
        if status["free"]["spin"]
        else 0
    )
    return row


def simulation(
    spin_times: int = SPIN_TIMES,
    index: int | None = None,
    general_index: int | None = None,
    choose_index: int = 1,
    free_general_index: int | None = None,
    report_interval: int = REPORT_INTERVAL,
    print_updates: bool = False,
) -> list[dict]:
    """Run N base spins and return cumulative checkpoint rows."""

    index = first_config_value(INDEX) if index is None else index
    general_index = first_config_value(GENERAL_INDEX) if general_index is None else general_index
    configured_free_general_index = free_general_index
    used_free_general_indexes = []
    status = status_handler.new_status()
    rows = []

    for _ in range(spin_times):
        status_handler.update_spin_start(status, m.base_bet)
        spin_total_win = 0

        ng_result = m.ng_spin(index, general_index, choose_index=choose_index)
        spin_total_win += record_win_info(status, ng_result, "base")

        free_times = int(ng_result.get("free_times", 0)) if ng_result.get("is_trigger_free") else 0
        status_handler.update_free_trigger(status, "base", free_times)
        if free_times > 0:
            current_free_general_index = resolve_free_general_index(
                choose_index,
                free_choice=ng_result.get("free_choice"),
                free_general_index=configured_free_general_index,
            )
            used_free_general_indexes.append(current_free_general_index)
            spin_total_win += run_free_spins(
                status=status,
                index=index,
                free_general_index=current_free_general_index,
                choose_index=choose_index,
                free_choice=ng_result.get("free_choice"),
                free_times=free_times,
            )

        status_handler.update_spin_result(status, spin_total_win, m.base_bet)

        base_spin = status["base"]["spin"]
        if report_interval > 0 and base_spin % report_interval == 0:
            row = build_simulation_row(
                status,
                index,
                general_index,
                choose_index,
                configured_free_general_index,
                used_free_general_indexes,
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
                choose_index,
                configured_free_general_index,
                used_free_general_indexes,
            )
        )
    rows[-1]["status"] = status
    return rows


def simulation_all(
    spin_times: int = SPIN_TIMES,
    indexes: list[int] | None = None,
    general_indexes: list[int] | None = None,
    choose_indexes: list[int] | None = None,
    free_general_indexes: list[int] | None = None,
    report_interval: int = REPORT_INTERVAL,
    print_updates: bool = True,
) -> list[dict]:
    """Run all index/general/choose combinations and return each final row."""

    results = []
    target_indexes = list_config_values(INDEX) if indexes is None else indexes
    target_choose_indexes = CHOOSE_INDEXES if choose_indexes is None else choose_indexes
    for index in target_indexes:
        target_general_indexes = list_config_values(GENERAL_INDEX) if general_indexes is None else general_indexes
        for general_index in target_general_indexes:
            for choose_index in target_choose_indexes:
                target_free_general_indexes = (
                    [None] if free_general_indexes is None else free_general_indexes
                )
                for free_general_index in target_free_general_indexes:
                    try:
                        rows = simulation(
                            spin_times=spin_times,
                            index=index,
                            general_index=general_index,
                            choose_index=choose_index,
                            free_general_index=free_general_index,
                            report_interval=report_interval if print_updates else 0,
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
                                "FREE_GENERAL": format_free_general_index(
                                    choose_index,
                                    free_general_index=free_general_index,
                                ),
                                "CHOOSE": choose_index,
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
        f"FREE_GENERAL_{result['FREE_GENERAL']}, choose_index: {result['CHOOSE']}"
    )
    print(f"总押注: {result['总押注']}")
    print(f"普通游戏赢钱: {result['BaseWays']}")
    print(f"免费游戏赢钱: {result['FreeWays']}")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run mjwl ways-game simulation.")
    parser.add_argument("--spins", type=int, default=SPIN_TIMES, help="Base ng_spin count.")
    parser.add_argument("--indexes", default=None, help="Comma-separated reel indexes.")
    parser.add_argument("--generals", default=None, help="Comma-separated GENERAL indexes.")
    parser.add_argument("--free-generals", default=None, help="Comma-separated free GENERAL indexes.")
    parser.add_argument("--choose-indexes", default=None, help="Comma-separated choose indexes.")
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
        "ways": [0, 0],
        "free": 0,
    },
    "free": {
        "spin": 0,
        "ways": [0, 0],
        "free": 0,
    },
    "bet": 0,
    "wins": 0,
    "hit": 0,
    "free_times": 0,
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
            "SPIN",
            "总押注",
            "rtp",
            "rtp_check",
            "总赢钱",
            "Ways赢钱",
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
            "base_ways_rtp",
            "BaseWays",
            "main_win_times",
            "main_win_rate",
        ],
    },
    {
        "title": "Free",
        "fields": [
            "free_rtp",
            "free_ways_rtp",
            "FreeWays",
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
    feature_key="ways",
    feature_label="Ways",
    print_mode="statics",
    statics_columns=statics_columns,
)


if __name__ == "__main__":
    args = parse_args()
    results = simulation_all(
        spin_times=args.spins,
        indexes=parse_int_list(args.indexes),
        general_indexes=parse_int_list(args.generals),
        choose_indexes=parse_int_list(args.choose_indexes),
        free_general_indexes=parse_int_list(args.free_generals),
        report_interval=args.report_interval,
        print_updates=args.print_updates,
    )
    print_table(results)
    append_simulation_results(results)
