"""Simulation entry for the line-game model."""

from __future__ import annotations

import argparse
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
INDEX = 0
GENERAL_INDEX = 1
REPORT_INTERVAL = 5000
THRESHOLDS = (5, 10, 20, 50, 100, 1000)
GENERAL_SECTION_RE = re.compile(r"^\s*\[GENERAL_(\d+)\]\s*$", re.MULTILINE)

status_model = {
    "base": {
        "spin": 0,
        "lines": [0, 0],
        "free": 0,
    },
    "free": {
        "spin": 0,
        "lines": [0, 0],
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

def discover_general_indexes(index: int = INDEX, free_game: bool = False) -> list[int]:
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


def get_free_times(m: ThemeMath, win_info: dict) -> int:
    """Return awarded free spins for a win_info payload."""

    if not win_info.get("win_free"):
        return 0

    item_list = win_info["item_list"]
    board_cols, col_count, row_count = m._normalize_item_list(item_list)
    grid_disables = m._get_grid_disables(bool(win_info.get("free_game")), col_count, row_count)
    scatter_count = 0
    for col_index in range(col_count):
        if m._get_or_default(m.scatter_cols, col_index, 1) != 1:
            continue
        for row_index in range(min(row_count, len(board_cols[col_index]))):
            if m._is_disabled(grid_disables, col_index, row_index, row_count):
                continue
            if board_cols[col_index][row_index] == m.scatter_id:
                scatter_count += 1
    return m._get_or_default(m.scatter_multiples, scatter_count, 0)


def record_win_info(status: dict, win_info: dict, mode_key: str) -> int:
    """Record one ng/fg win_info into base/free status and return total win."""

    total_win = int(win_info.get("total_win", 0))
    line_win = get_line_win(win_info)
    status_handler.update_feature_win(status, mode_key, "lines", line_win)
    return total_win


def run_free_spins(
    m: ThemeMath,
    status: dict,
    index: int,
    free_general_index: int,
    free_times: int,
) -> int:
    """Consume free spins and return total free win."""

    remaining_free_times = free_times
    free_total_win = 0
    while remaining_free_times > 0:
        remaining_free_times -= 1
        status_handler.add_status_value(status, 1, "free", "spin")
        fg_info = m.fg_spin(index, free_general_index, return_detail=True)
        free_total_win += record_win_info(status, fg_info, "free")

        retrigger_times = get_free_times(m, fg_info)
        status_handler.update_free_trigger(status, "free", retrigger_times)
        remaining_free_times += retrigger_times

    return free_total_win


def simulation(
    spin_times: int = SPIN_TIMES,
    index: int = INDEX,
    general_index: int = GENERAL_INDEX,
    free_general_index: int | None = None,
    report_interval: int = REPORT_INTERVAL,
) -> list[dict]:
    """Run N ng_spin and return cumulative checkpoint rows."""

    m = ThemeMath()
    free_general_index = general_index if free_general_index is None else free_general_index
    status = status_handler.new_status()
    rows = []

    for _ in range(spin_times):
        status_handler.update_spin_start(status, m.base_bet)
        spin_total_win = 0

        win_info = m.ng_spin(index, general_index, return_detail=True)
        spin_total_win += record_win_info(status, win_info, "base")

        free_times = get_free_times(m, win_info)
        status_handler.update_free_trigger(status, "base", free_times)
        if free_times > 0:
            spin_total_win += run_free_spins(m, status, index, free_general_index, free_times)

        status_handler.update_spin_result(status, spin_total_win, m.base_bet)

        base_spin = status["base"]["spin"]
        if report_interval > 0 and base_spin % report_interval == 0:
            rows.append(status_handler.build_report_row(status))

    if not rows or rows[-1]["SPIN"] != status["base"]["spin"]:
        rows.append(status_handler.build_report_row(status))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run line-game simulation.")
    parser.add_argument("--spins", type=int, default=SPIN_TIMES, help="Base ng_spin count.")
    parser.add_argument("--index", type=int, default=INDEX, help="Reel config index.")
    parser.add_argument("--general", type=int, default=GENERAL_INDEX, help="Base GENERAL index.")
    parser.add_argument("--free-general", type=int, default=None, help="Free GENERAL index.")
    parser.add_argument("--report-interval", type=int, default=REPORT_INTERVAL)
    return parser.parse_args()



status_handler = SlotsSimulation(status_model=status_model, thresholds=THRESHOLDS)


if __name__ == "__main__":
    args = parse_args()
    status_handler.print_table(
        simulation(
            spin_times=args.spins,
            index=args.index,
            general_index=args.general,
            free_general_index=args.free_general,
            report_interval=args.report_interval,
        )
    )
