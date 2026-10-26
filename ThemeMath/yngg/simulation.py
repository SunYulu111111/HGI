"""Simulation entry for the yngg cluster game.

Edit the constants below, then run this file directly:

    python simulation.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import random
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


# --- run parameters: edit these, then execute this file ---
SPIN_TIMES = 10000000
INDEX = [0]
GENERAL_INDEX = [1]
REPORT_INTERVAL = 5000
PRINT_UPDATES = True
SEED = None
BASE_BET = 100000
THRESHOLDS = (5, 10, 20, 50, 100, 1000)
RESULT_CSV = Path(__file__).resolve().with_name("simulate_result.csv")
MAIN_CASCADE_BUCKETS = tuple(range(10))
MAIN_CASCADE_OVERFLOW_LABEL = "10+"
MAIN_CASCADE_BUCKET_COUNT = len(MAIN_CASCADE_BUCKETS) + 1
RESULT_CSV_FIELDS = [
    "INDEX",
    "GENERAL",
    "SPIN",
    "总押注",
    "rtp",
    "rtp_check",
    "base_rtp",
    "base_cluster_rtp",
    "base_bonus_rtp",
    "free_rtp",
    "free_cluster_rtp",
    "free_bonus_rtp",
    "NormalFreeRtp",
    "NormalFreeClusterRtp",
    "NormalFreeBonusRtp",
    "NormalFreeFrequency",
    "NormalFreeSessionCount",
    "NormalFreeSpinCount",
    "NormalFreeRetriggerCount",
    "NormalFreeClusterWin",
    "NormalFreeBonusWin",
    "SuperFreeRtp",
    "SuperFreeClusterRtp",
    "SuperFreeBonusRtp",
    "SuperFreeFrequency",
    "SuperFreeSessionCount",
    "SuperFreeSpinCount",
    "SuperFreeRetriggerCount",
    "SuperFreeClusterWin",
    "SuperFreeBonusWin",
    "总赢钱",
    "Cluster赢钱",
    "Bonus赢钱",
    "BaseCluster",
    "FreeCluster",
    "BaseBonus",
    "FreeBonus",
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
    "Free 1/n",
    "Free次数",
    "FreeSpin",
    "Free重触发",
    "Free平均次数",
    "Free平均倍",
    "SuperFree",
    "SuperFree频率",
    "Bonus触发",
    "Bonus频率",
    "Bonus 1/n",
    "main_win_times",
    "main_win_rate",
    "连消0次",
    "连消1次",
    "连消2次",
    "连消3次",
    "连消4次",
    "连消5次",
    "连消6次",
    "连消7次",
    "连消8次",
    "连消9次",
    "连消10+次",
    "free_win_times",
    "free_win_rate",
    "ok",
    "错误",
    "status",
]


m = ThemeMath(base_bet=BASE_BET)


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


def main_cascade_bucket(cascade_count: int) -> int:
    """Return the status bucket index for a main-game cascade count."""

    return cascade_count if cascade_count < len(MAIN_CASCADE_BUCKETS) else len(MAIN_CASCADE_BUCKETS)


def main_cascade_label(bucket_index: int) -> str:
    """Return the report label for a main-game cascade bucket."""

    if bucket_index < len(MAIN_CASCADE_BUCKETS):
        return str(bucket_index)
    return MAIN_CASCADE_OVERFLOW_LABEL


def record_main_cascade_count(status: dict, ng_result: dict) -> None:
    """Record one base spin's cascade-count bucket."""

    cascade_count = int(ng_result.get("cascade_count", 0))
    bucket_index = main_cascade_bucket(cascade_count)
    status["main_cascade_counts"][bucket_index] += 1


def add_main_cascade_report_values(row: dict, status: dict) -> None:
    """Add main-game cascade-count counts to a report row."""

    counts = status.get("main_cascade_counts", [])
    for bucket_index in range(MAIN_CASCADE_BUCKET_COUNT):
        count = counts[bucket_index] if bucket_index < len(counts) else 0
        label = main_cascade_label(bucket_index)
        row[f"连消{label}次"] = count


def record_spin_wins(status: dict, result: dict, mode_key: str) -> int:
    """Record cluster and bonus wins for one ng/fg spin and return total win."""

    total_win = int(result.get("total_win", 0))
    feature_win = int(result.get("feature_win", 0))
    cluster_win = total_win - feature_win
    status_handler.update_feature_win(status, mode_key, "cluster", cluster_win)
    status_handler.update_feature_win(status, mode_key, "bonus", feature_win)
    return total_win


def new_mode_stats() -> dict:
    """Separate session counts and wins without duplicating legacy RTP entries."""

    return {
        Mode: {
            "SessionCount": 0,
            "SpinCount": 0,
            "ClusterWin": 0,
            "BonusWin": 0,
            "RetriggerCount": 0,
        }
        for Mode in ("Free", "SuperFree")
    }


def run_free_spins(status: dict, index: int, general_index: int, ng_result: dict) -> int:
    """Consume a free/super-free session and return total free win."""

    remaining_free_times = int(ng_result.get("free_times", 0))
    free_mode = ng_result.get("free_mode") or "free"
    golden_squares = set()
    bonus_seen = False
    free_total_win = 0
    ModeName = "SuperFree" if free_mode == "super_free" else "Free"
    ModeStats = status.setdefault("ModeStats", new_mode_stats())[ModeName]
    if remaining_free_times > 0:
        ModeStats["SessionCount"] += 1

    while remaining_free_times > 0:
        remaining_free_times -= 1
        status_handler.add_status_value(status, 1, "free", "spin")
        ModeStats["SpinCount"] += 1
        fg_result = m.fg_spin(
            index=index,
            general_index=general_index,
            free_mode=free_mode,
            golden_squares=golden_squares,
            remaining_spins=remaining_free_times + 1,
            bonus_seen=bonus_seen,
        )
        SpinWin = record_spin_wins(status, fg_result, "free")
        BonusWin = int(fg_result.get("feature_win", 0))
        ModeStats["ClusterWin"] += SpinWin - BonusWin
        ModeStats["BonusWin"] += BonusWin
        free_total_win += SpinWin
        if fg_result.get("is_trigger_feature"):
            status_handler.add_status_value(status, 1, "free_bonus_trigger")
        bonus_seen = bool(fg_result.get("free_bonus_seen"))
        golden_squares = set(map(tuple, fg_result.get("golden_squares") or []))
        retrigger_times = int(fg_result.get("retrigger_spins", 0))
        status_handler.update_free_trigger(status, "free", retrigger_times)
        if retrigger_times > 0:
            ModeStats["RetriggerCount"] += 1
        remaining_free_times += retrigger_times

    return free_total_win


def build_simulation_row(status: dict, index: int, general_index: int) -> dict:
    """Build one yngg report row from current status."""

    # The shared helper derives legacy underscore-named fields recursively.
    # Keep the separate scalar counters out of that compatibility projection.
    ReportStatus = {Key: Value for Key, Value in status.items() if Key != "ModeStats"}
    row = status_handler.build_report_row(ReportStatus)
    row["INDEX"] = index
    row["GENERAL"] = general_index
    row["错误"] = ""

    base_spin = status["base"]["spin"]
    base_bet = status["bet"] / base_spin if base_spin else 0
    free_trigger_count = status["base"]["free"]
    base_bonus_trigger = status["base_bonus_trigger"]
    super_free_count = status["super_free"]
    free_cluster_win = status_handler.get_list_win(status["free"]["cluster"])
    free_bonus_win = status_handler.get_list_win(status["free"]["bonus"])
    base_bonus_win = status_handler.get_list_win(status["base"]["bonus"])
    free_session_win = free_cluster_win + free_bonus_win

    row["总押注"] = status["bet"]
    row["Bonus赢钱"] = base_bonus_win + free_bonus_win
    row["BaseBonus"] = base_bonus_win
    row["FreeBonus"] = free_bonus_win
    row["Free平均次数"] = (
        status["free_times"] / free_trigger_count if free_trigger_count else 0
    )
    row["Free平均倍"] = (
        free_session_win / free_trigger_count / base_bet
        if free_trigger_count and base_bet
        else 0
    )
    row["Free 1/n"] = base_spin / free_trigger_count if free_trigger_count else 0
    row["SuperFree"] = super_free_count
    row["SuperFree频率"] = super_free_count / base_spin if base_spin else 0
    row["Bonus触发"] = base_bonus_trigger
    row["Bonus频率"] = base_bonus_trigger / base_spin if base_spin else 0
    row["Bonus 1/n"] = base_spin / base_bonus_trigger if base_bonus_trigger else 0
    row["main_win_times"] = status["base"]["cluster"][0]
    row["free_win_times"] = status["free"]["cluster"][0]
    row["main_win_rate"] = status["base"]["cluster"][0] / base_spin if base_spin else 0
    row["free_win_rate"] = (
        status["free"]["cluster"][0] / status["free"]["spin"]
        if status["free"]["spin"]
        else 0
    )
    ModeStats = status.get("ModeStats", new_mode_stats())
    for ModeName, Prefix in (("Free", "NormalFree"), ("SuperFree", "SuperFree")):
        Stats = ModeStats[ModeName]
        ClusterWin = Stats["ClusterWin"]
        BonusWin = Stats["BonusWin"]
        TotalBet = status["bet"]
        row[f"{Prefix}ClusterRtp"] = ClusterWin / TotalBet if TotalBet else 0
        row[f"{Prefix}BonusRtp"] = BonusWin / TotalBet if TotalBet else 0
        row[f"{Prefix}Rtp"] = (ClusterWin + BonusWin) / TotalBet if TotalBet else 0
        row[f"{Prefix}Frequency"] = Stats["SessionCount"] / base_spin if base_spin else 0
        for Field in ("SessionCount", "SpinCount", "RetriggerCount", "ClusterWin", "BonusWin"):
            row[f"{Prefix}{Field}"] = Stats[Field]
    add_main_cascade_report_values(row, status)
    return row


def simulation(
    spin_times: int = SPIN_TIMES,
    index: int | None = None,
    general_index: int | None = None,
    report_interval: int = REPORT_INTERVAL,
    print_updates: bool = False,
    seed: int | None = SEED,
) -> list[dict]:
    """Run N base spins and return cumulative checkpoint rows."""

    index = first_config_value(INDEX) if index is None else index
    general_index = first_config_value(GENERAL_INDEX) if general_index is None else general_index
    if seed is not None:
        random.seed(seed)

    status = status_handler.new_status()
    rows = []

    for _ in range(spin_times):
        status_handler.update_spin_start(status, m.base_bet)
        spin_total_win = 0

        ng_result = m.ng_spin(index=index, general_index=general_index)
        record_main_cascade_count(status, ng_result)
        spin_total_win += record_spin_wins(status, ng_result, "base")
        if ng_result.get("is_trigger_feature"):
            status_handler.add_status_value(status, 1, "base_bonus_trigger")

        free_times = (
            int(ng_result.get("free_times", 0)) if ng_result.get("is_trigger_free") else 0
        )
        status_handler.update_free_trigger(status, "base", free_times)
        if free_times > 0:
            if (ng_result.get("free_mode") or "") == "super_free":
                status_handler.add_status_value(status, 1, "super_free")
            spin_total_win += run_free_spins(
                status=status,
                index=index,
                general_index=general_index,
                ng_result=ng_result,
            )

        status_handler.update_spin_result(status, spin_total_win, m.base_bet)

        base_spin = status["base"]["spin"]
        if report_interval > 0 and base_spin % report_interval == 0:
            row = build_simulation_row(status, index, general_index)
            rows.append(row)
            if print_updates:
                status_handler.print_table([row])

    if not rows or rows[-1]["SPIN"] != status["base"]["spin"]:
        rows.append(build_simulation_row(status, index, general_index))
    rows[-1]["status"] = status
    return rows


def simulation_all(
    spin_times: int = SPIN_TIMES,
    indexes: list[int] | None = None,
    general_indexes: list[int] | None = None,
    report_interval: int = REPORT_INTERVAL,
    print_updates: bool = PRINT_UPDATES,
    seed: int | None = SEED,
) -> list[dict]:
    """Run all index/general combinations and return each final row."""

    results = []
    target_indexes = list_config_values(INDEX) if indexes is None else indexes
    for index in target_indexes:
        target_general_indexes = (
            list_config_values(GENERAL_INDEX) if general_indexes is None else general_indexes
        )
        for general_index in target_general_indexes:
            try:
                rows = simulation(
                    spin_times=spin_times,
                    index=index,
                    general_index=general_index,
                    report_interval=report_interval if print_updates else 0,
                    print_updates=print_updates,
                    seed=seed,
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
    print(f"index: {result['INDEX']}, GENERAL_{result['GENERAL']}")
    print(f"总押注: {result['总押注']}")
    print(f"普通游戏 Cluster: {result['BaseCluster']}")
    print(f"普通游戏 Bonus: {result['BaseBonus']}")
    print(f"免费游戏合计 Cluster: {result['FreeCluster']}")
    print(f"免费游戏合计 Bonus: {result['FreeBonus']}")
    print(f"总赢钱: {result['总赢钱']}")
    print(f"普通游戏 RTP: {result['base_rtp']:.3f}")
    print(f"免费游戏合计 RTP: {result['free_rtp']:.3f}")
    for Prefix, Label in (("NormalFree", "普通 Free"), ("SuperFree", "Super Free")):
        if f"{Prefix}Rtp" in result:
            print(
                f"{Label} RTP: {result[f'{Prefix}Rtp']:.6f} "
                f"(Cluster {result[f'{Prefix}ClusterRtp']:.6f}, "
                f"Bonus {result[f'{Prefix}BonusRtp']:.6f})"
            )
            print(f"{Label} 触发概率: {result[f'{Prefix}Frequency']:.3%}")
    print(f"总 RTP: {result['rtp']:.3f}")
    print(f"RTP 校验: {result['rtp_check']:.3f}")
    print(f"赢钱次数: {result['Hit']}")
    print(f"赢钱率: {result['Hit率']:.3f}")
    print(f"触发 free 次数: {result['触发Free']}")
    print(f"free 中再次触发 free 次数: {result['Free重触发']}")
    print(f"触发 free 概率: {result['Free频率']:.3%}")
    print(f"free 1/n: {result['Free 1/n']:.1f}")
    print(f"免费游戏总次数: {result['FreeSpin']}")
    print(f"平均每次触发 free 次数: {result['Free平均次数']:.6f}")
    print(f"平均每次 free 赢钱倍数: {result['Free平均倍']:.3f}")
    print(f"Super Free 次数: {result['SuperFree']}")
    print(f"Base Bonus 触发: {result['Bonus触发']}")
    print(f"Base Bonus 概率: {result['Bonus频率']:.3%}")
    print(f"Base Bonus 1/n: {result['Bonus 1/n']:.1f}")


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
        {key for row in rows for key in row if key not in RESULT_CSV_FIELDS}
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


class YnggSlotsSimulation(SlotsSimulation):
    """Format yngg-specific rate and 1-in-N fields."""

    def format_cell(self, header: str, value):
        if value == "" or value is None:
            return ""
        if header in {"Bonus频率", "SuperFree频率"} or header.endswith("Frequency"):
            return f"{value:.3%}"
        if header.endswith("Rtp"):
            return f"{value:.6f}"
        if header in {"Bonus 1/n", "Free 1/n"}:
            return f"{value:.1f}" if value else ""
        return super().format_cell(header, value)


status_model = {
    "base": {
        "spin": 0,
        "cluster": [0, 0],
        "bonus": [0, 0],
        "free": 0,
    },
    "free": {
        "spin": 0,
        "cluster": [0, 0],
        "bonus": [0, 0],
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
    "base_bonus_trigger": 0,
    "free_bonus_trigger": 0,
    "super_free": 0,
    "main_cascade_counts": [0 for _ in range(MAIN_CASCADE_BUCKET_COUNT)],
    "ModeStats": new_mode_stats(),
}

statics_columns = [
    {
        "title": "基础信息",
        "fields": [
            "INDEX",
            "GENERAL",
            "SPIN",
            "总押注",
            "rtp",
            "rtp_check",
            "总赢钱",
            "Cluster赢钱",
            "Bonus赢钱",
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
            "base_cluster_rtp",
            "base_bonus_rtp",
            "BaseCluster",
            "BaseBonus",
            "main_win_times",
            "main_win_rate",
            "Bonus触发",
            "Bonus频率",
            "Bonus 1/n",
            "连消0次",
            "连消1次",
            "连消2次",
            "连消3次",
            "连消4次",
            "连消5次",
            "连消6次",
            "连消7次",
            "连消8次",
            "连消9次",
            "连消10+次",
        ],
    },
    {
        "title": "Free 合计",
        "fields": [
            "free_rtp",
            "free_cluster_rtp",
            "free_bonus_rtp",
            "FreeCluster",
            "FreeBonus",
            "free_win_times",
            "free_win_rate",
            "触发Free",
            "Free频率",
            "Free 1/n",
            "Free次数",
            "FreeSpin",
            "Free重触发",
            "Free平均次数",
            "Free平均倍",
            "SuperFree",
            "SuperFree频率",
        ],
    },
    {
        "title": "普通 Free",
        "fields": [
            "NormalFreeRtp",
            "NormalFreeClusterRtp",
            "NormalFreeBonusRtp",
            "NormalFreeFrequency",
            "NormalFreeSessionCount",
            "NormalFreeSpinCount",
            "NormalFreeRetriggerCount",
        ],
    },
    {
        "title": "Super Free",
        "fields": [
            "SuperFreeRtp",
            "SuperFreeClusterRtp",
            "SuperFreeBonusRtp",
            "SuperFreeFrequency",
            "SuperFreeSessionCount",
            "SuperFreeSpinCount",
            "SuperFreeRetriggerCount",
        ],
    },
]

status_handler = YnggSlotsSimulation(
    status_model=status_model,
    thresholds=THRESHOLDS,
    feature_key="cluster",
    feature_label="Cluster",
    print_mode="statics",
    statics_columns=statics_columns,
)


if __name__ == "__main__":
    results = simulation_all()
    print_table(results)
    append_simulation_results(results)
