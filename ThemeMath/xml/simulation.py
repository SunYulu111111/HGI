"""RZCS 风格的 XML 水果机模拟入口。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
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


class XmlSlotsSimulation(SlotsSimulation):
    """使用三位小数格式化 XML 模拟统计。"""

    def format_cell(self, header: str, value):
        if value == "" or value is None:
            return ""
        if header in {"Hit率", "Bonus频率", "倍乘成功率"} or header.endswith("_rate"):
            return f"{value:.3%}"
        if header in {"rtp", "rtp_check", "base_rtp", "double_rtp"} or header.endswith("_rtp"):
            return f"{value:.6f}"
        if isinstance(value, float):
            return f"{value:.3f}"
        return value


SPIN_TIMES = 1_000_000
REPORT_INTERVAL = 5_000
THRESHOLDS = (5, 10, 20, 50, 100, 1000)
Bet_Multi = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1]
Double_Times = 0
BET_MULTIS = [Bet_Multi]
DOUBLE_TIMES = [Double_Times]
SEEDS = [None]
RESULT_CSV = Path(__file__).resolve().with_name("simulate_result.csv")
SYMBOL_IDS = tuple(range(2, 10))
DOUBLE_WEIGHT_KEYS = (
    "DoubleWeight_1",
    "DoubleWeight_5",
    "DoubleWeight_10",
    "DoubleWeight_25",
    "DoubleWeight_50",
    "DoubleWeight_100",
    "DoubleWeight",
)
DOUBLE_SELECTED_REPORT_FIELDS = [
    field
    for double_times in range(11)
    for field in (
        f"double_selected_{double_times}_count",
        f"double_selected_{double_times}_rate",
    )
]
DOUBLE_WEIGHT_REPORT_FIELDS = [
    field
    for key in DOUBLE_WEIGHT_KEYS
    for field in (
        f"{key}_count",
        f"{key}_rate",
    )
]
SYMBOL_REPORT_FIELDS = [
    field
    for symbol_id in SYMBOL_IDS
    for field in (
        f"symbol_{symbol_id}_bet",
        f"symbol_{symbol_id}_hit",
        f"symbol_{symbol_id}_hit_rate",
        f"symbol_{symbol_id}_win",
        f"symbol_{symbol_id}_rtp",
    )
]
RESPIN_COUNT_REPORT_FIELDS = [
    field
    for count in range(1, 9)
    for field in (
        f"respin_count_{count}_count",
        f"respin_count_{count}_rate",
    )
]
RESULT_CSV_FIELDS = [
    "BET_MULTI",
    "DOUBLE_TIMES",
    "SEED",
    "SPIN",
    "总押注",
    "rtp",
    "rtp_check",
    "base_rtp",
    "double_rtp",
    "总赢钱",
    "Base赢钱",
    "倍乘增减",
    "Hit",
    "Hit率",
    ">5x",
    ">10x",
    ">20x",
    ">50x",
    ">100x",
    ">1000x",
    "Bonus次数",
    "Bonus频率",
    "BonusSymbol数",
    "Bonus平均Symbol",
    *RESPIN_COUNT_REPORT_FIELDS,
    "倍乘触发",
    "倍乘尝试",
    "倍乘成功",
    "倍乘失败",
    "倍乘成功率",
    *DOUBLE_SELECTED_REPORT_FIELDS,
    *DOUBLE_WEIGHT_REPORT_FIELDS,
    *SYMBOL_REPORT_FIELDS,
    "ok",
    "错误",
    "status",
]


def list_config_values(value) -> list:
    """把标量或列表统一转换成列表。"""

    return list(value) if isinstance(value, (list, tuple)) else [value]


def normalize_double_times(value: int, max_times: int = 10) -> int:
    """校验玩家计划尝试的倍乘次数。"""

    if isinstance(value, bool):
        raise TypeError("double_times 必须是整数")
    value = int(value)
    if not 0 <= value <= max_times:
        raise ValueError(f"double_times 必须为 0-{max_times}")
    return value


def build_symbol_bets(math: ThemeMath, bet_multi: list[int]) -> dict[int, int]:
    """实际下注为 BaseBet * Bet_Multi[symbol_id]。"""

    if len(bet_multi) != math.item_count:
        raise ValueError(f"Bet_Multi 必须包含 {math.item_count} 项")
    if any(bet_multi[symbol_id] != 0 for symbol_id in (0, 1)):
        raise ValueError("Bet_Multi 的 symbol 0 和 1 必须为 0")

    bets: dict[int, int] = {}
    for symbol_id in math.BET_SYMBOL_IDS:
        multiplier = bet_multi[symbol_id]
        if isinstance(multiplier, bool) or not isinstance(multiplier, int):
            raise TypeError(f"Bet_Multi[{symbol_id}] 必须是整数")
        if multiplier < 0:
            raise ValueError(f"Bet_Multi[{symbol_id}] 不能为负数")
        if multiplier > 0:
            bets[symbol_id] = math.base_bet * multiplier
    return math.validate_bets(bets)


status_model = {
    "base": {
        "spin": 0,
        "fruit": [0, 0],
        "free": 0,
    },
    "free": {
        "spin": 0,
        "fruit": [0, 0],
        "free": 0,
    },
    "bet": 0,
    "wins": 0,
    "hit": 0,
    "base_win": 0,
    "double_delta_win": 0,
    "bonus_count": 0,
    "bonus_symbol_count": 0,
    "respin_count_counts": [0] * 9,
    "double_trigger_count": 0,
    "double_attempt_count": 0,
    "double_success_count": 0,
    "double_fail_count": 0,
    "double_selected_counts": [0] * 11,
    "double_weight_key_counts": {key: 0 for key in DOUBLE_WEIGHT_KEYS},
    "symbol_bets": {symbol_id: 0 for symbol_id in SYMBOL_IDS},
    "symbol_hit_counts": {symbol_id: 0 for symbol_id in SYMBOL_IDS},
    "symbol_wins": {symbol_id: 0 for symbol_id in SYMBOL_IDS},
    **{f"gt_{threshold}x": 0 for threshold in THRESHOLDS},
}

statics_columns = [
    {
        "title": "基础信息",
        "fields": [
            "BET_MULTI",
            "DOUBLE_TIMES",
            "SEED",
            "SPIN",
            "总押注",
            "rtp",
            "rtp_check",
            "总赢钱",
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
            "Base赢钱",
            "base_win_times",
            "base_win_rate",
            "Bonus次数",
            "Bonus频率",
            "BonusSymbol数",
            "Bonus平均Symbol",
        ],
    },
    {
        "title": "倍乘",
        "fields": [
            "double_rtp",
            "倍乘增减",
            "倍乘触发",
            "倍乘尝试",
            "倍乘成功",
            "倍乘失败",
            "倍乘成功率",
        ],
    },
    {
        "title": "Symbol RTP",
        "fields": [
            {"label": f"S{symbol_id} RTP", "key": f"symbol_{symbol_id}_rtp"}
            for symbol_id in SYMBOL_IDS
        ],
    },
]

status_handler = XmlSlotsSimulation(
    status_model=status_model,
    thresholds=THRESHOLDS,
    feature_key="fruit",
    feature_label="Fruit",
    print_mode="statics",
    statics_columns=statics_columns,
)


def record_spin(
    status: dict,
    result: dict,
    bets: dict[int, int],
) -> None:
    """把一次 XML spin 记录到累计状态。"""

    total_bet = result["total_bet"]
    base_win = result["base_win"]
    total_win = result["total_win"]
    status_handler.update_spin_start(status, total_bet)
    status_handler.update_feature_win(status, "base", "fruit", base_win)
    status_handler.update_spin_result(status, total_win, total_bet)
    status["base_win"] += base_win
    status["double_delta_win"] += total_win - base_win
    status["bonus_count"] += int(result["is_bonus"])
    if result["is_bonus"]:
        respin_count = result["respin_count"]
        status["bonus_symbol_count"] += respin_count
        status["respin_count_counts"][respin_count] += 1

    for symbol_id in SYMBOL_IDS:
        status["symbol_bets"][symbol_id] += bets.get(symbol_id, 0)
    hit_symbols = set()
    for outcome in result["outcomes"]:
        symbol_id = outcome["symbol_id"]
        if symbol_id not in status["symbol_wins"] or outcome["win"] <= 0:
            continue
        status["symbol_wins"][symbol_id] += outcome["win"]
        hit_symbols.add(symbol_id)
    for symbol_id in hit_symbols:
        status["symbol_hit_counts"][symbol_id] += 1

    double_result = result["double_result"]
    selected_times = double_result["selected_times"]
    if selected_times is not None:
        status["double_trigger_count"] += 1
        status["double_selected_counts"][selected_times] += 1
    status["double_attempt_count"] += double_result["attempted_times"]
    status["double_success_count"] += double_result["success_times"]
    status["double_fail_count"] += int(double_result["failed"])
    weight_key = double_result["double_weight_key"]
    if weight_key is not None:
        status["double_weight_key_counts"].setdefault(weight_key, 0)
        status["double_weight_key_counts"][weight_key] += 1


def build_simulation_row(
    status: dict,
    bet_multi: list[int],
    double_times: int,
    seed: int | None,
) -> dict:
    """构建一个与 RZCS 报表风格一致的累计结果行。"""

    row = status_handler.build_report_row(status)
    spins = status["base"]["spin"]
    total_bet = status["bet"]
    base_win = status["base_win"]
    total_win = status["wins"]
    double_trigger_count = status["double_trigger_count"]
    double_attempt_count = status["double_attempt_count"]

    row.update(
        {
            "BET_MULTI": list(bet_multi),
            "DOUBLE_TIMES": double_times,
            "SEED": "" if seed is None else seed,
            "总押注": total_bet,
            "rtp": total_win / total_bet if total_bet else 0,
            "rtp_check": total_win / total_bet if total_bet else 0,
            "base_rtp": base_win / total_bet if total_bet else 0,
            "double_rtp": status["double_delta_win"] / total_bet if total_bet else 0,
            "总赢钱": total_win,
            "Base赢钱": base_win,
            "倍乘增减": status["double_delta_win"],
            "Bonus次数": status["bonus_count"],
            "Bonus频率": status["bonus_count"] / spins if spins else 0,
            "BonusSymbol数": status["bonus_symbol_count"],
            "Bonus平均Symbol": (
                status["bonus_symbol_count"] / status["bonus_count"]
                if status["bonus_count"]
                else 0
            ),
            "倍乘触发": double_trigger_count,
            "倍乘尝试": double_attempt_count,
            "倍乘成功": status["double_success_count"],
            "倍乘失败": status["double_fail_count"],
            "倍乘成功率": (
                status["double_success_count"] / double_attempt_count
                if double_attempt_count
                else 0
            ),
            "base_win_times": status["base"]["fruit"][0],
            "base_win_rate": status["base"]["fruit"][0] / spins if spins else 0,
            "错误": "",
            # 兼容旧版 XML simulate() 返回字段。
            "spins": spins,
            "seed": seed,
            "bet_multi": list(bet_multi),
            "double_times": double_times,
            "bets": {
                symbol_id: status["symbol_bets"][symbol_id] // spins
                for symbol_id in SYMBOL_IDS
                if spins and status["symbol_bets"][symbol_id] > 0
            },
            "total_bet": total_bet,
            "base_total_win": base_win,
            "total_win": total_win,
            "hit_rate": status["hit"] / spins if spins else 0,
            "bonus_rate": status["bonus_count"] / spins if spins else 0,
            "respin_count_counts": list(status["respin_count_counts"]),
            "double_attempt_count": double_attempt_count,
            "double_success_count": status["double_success_count"],
            "double_fail_count": status["double_fail_count"],
            "double_selected_counts": list(status["double_selected_counts"]),
            "double_weight_key_counts": dict(status["double_weight_key_counts"]),
        }
    )

    for selected_times, count in enumerate(status["double_selected_counts"]):
        row[f"double_selected_{selected_times}_count"] = count
        row[f"double_selected_{selected_times}_rate"] = (
            count / double_trigger_count if double_trigger_count else 0
        )
    for respin_count in range(1, 9):
        count = status["respin_count_counts"][respin_count]
        row[f"respin_count_{respin_count}_count"] = count
        row[f"respin_count_{respin_count}_rate"] = (
            count / status["bonus_count"] if status["bonus_count"] else 0
        )
    for key in DOUBLE_WEIGHT_KEYS:
        count = status["double_weight_key_counts"].get(key, 0)
        row[f"{key}_count"] = count
        row[f"{key}_rate"] = count / double_trigger_count if double_trigger_count else 0
    for symbol_id in SYMBOL_IDS:
        symbol_bet = status["symbol_bets"][symbol_id]
        symbol_hit = status["symbol_hit_counts"][symbol_id]
        symbol_win = status["symbol_wins"][symbol_id]
        row[f"symbol_{symbol_id}_bet"] = symbol_bet
        row[f"symbol_{symbol_id}_hit"] = symbol_hit
        row[f"symbol_{symbol_id}_hit_rate"] = symbol_hit / spins if spins else 0
        row[f"symbol_{symbol_id}_win"] = symbol_win
        row[f"symbol_{symbol_id}_rtp"] = symbol_win / symbol_bet if symbol_bet else 0
    return row


def simulation(
    spin_times: int = SPIN_TIMES,
    bet_multi: list[int] | None = None,
    double_times: int | None = None,
    seed: int | None = None,
    report_interval: int = REPORT_INTERVAL,
    print_updates: bool = False,
) -> list[dict]:
    """运行一次参数组合，返回累计检查点结果。"""

    if spin_times <= 0:
        raise ValueError("spin_times 必须大于 0")
    bet_multi = list(Bet_Multi if bet_multi is None else bet_multi)
    double_times = normalize_double_times(
        Double_Times if double_times is None else double_times
    )
    import random

    math = ThemeMath(rng=random.Random(seed))
    bets = build_symbol_bets(math, bet_multi)
    status = status_handler.new_status()
    rows: list[dict] = []

    for _ in range(spin_times):
        result = math.spin(
            bets,
            return_detail=True,
            double_times=double_times,
        )
        record_spin(status, result, bets)
        spins = status["base"]["spin"]
        if report_interval > 0 and spins % report_interval == 0:
            row = build_simulation_row(status, bet_multi, double_times, seed)
            rows.append(row)
            if print_updates:
                status_handler.print_table([row])

    if not rows or rows[-1]["SPIN"] != status["base"]["spin"]:
        rows.append(build_simulation_row(status, bet_multi, double_times, seed))
    rows[-1]["status"] = status
    return rows


def simulate(
    spins: int,
    bet_multi: list[int] | None = None,
    double_times: int | None = None,
    seed: int | None = None,
) -> dict:
    """兼容旧调用方式，返回最后一个累计结果行。"""

    return simulation(
        spin_times=spins,
        bet_multi=bet_multi,
        double_times=double_times,
        seed=seed,
        report_interval=0,
    )[-1]


def simulation_all(
    spin_times: int = SPIN_TIMES,
    bet_multis: list[list[int]] | None = None,
    double_times_values: list[int] | None = None,
    seeds: list[int | None] | None = None,
    report_interval: int = REPORT_INTERVAL,
    print_updates: bool = True,
) -> list[dict]:
    """运行全部下注、倍乘和随机种子组合。"""

    bet_multis = BET_MULTIS if bet_multis is None else bet_multis
    double_times_values = DOUBLE_TIMES if double_times_values is None else double_times_values
    seeds = SEEDS if seeds is None else seeds
    results = []
    for bet_multi in bet_multis:
        for double_times in double_times_values:
            for seed in seeds:
                try:
                    rows = simulation(
                        spin_times=spin_times,
                        bet_multi=bet_multi,
                        double_times=double_times,
                        seed=seed,
                        report_interval=report_interval if print_updates else 0,
                        print_updates=print_updates,
                    )
                    final_row = rows[-1]
                    final_row["ok"] = True
                    results.append(final_row)
                except Exception as exc:
                    results.append(
                        {
                            "ok": False,
                            "BET_MULTI": list(bet_multi),
                            "DOUBLE_TIMES": double_times,
                            "SEED": "" if seed is None else seed,
                            "SPIN": spin_times,
                            "错误": str(exc),
                        }
                    )
    return results


def print_summary(result: dict | list[dict]) -> None:
    """打印单次模拟最终摘要。"""

    if isinstance(result, list):
        result = result[-1] if result else {}
    if not result:
        return
    print(f"模拟次数: {result['SPIN']}")
    print(
        f"Bet_Multi: {result['BET_MULTI']}, Double_Times: {result['DOUBLE_TIMES']}, "
        f"Seed: {result['SEED']}"
    )
    print(f"总押注: {result['总押注']}")
    print(f"Base赢钱: {result['Base赢钱']}")
    print(f"倍乘增减: {result['倍乘增减']}")
    print(f"总赢钱: {result['总赢钱']}")
    print(f"Base RTP: {result['base_rtp']:.6f}")
    print(f"倍乘 RTP: {result['double_rtp']:.6f}")
    print(f"总 RTP: {result['rtp']:.6f}")
    print(f"Hit率: {result['Hit率']:.3%}")
    print(f"Bonus频率: {result['Bonus频率']:.3%}")
    print(
        f"倍乘触发: {result['倍乘触发']}, 成功: {result['倍乘成功']}, "
        f"失败: {result['倍乘失败']}"
    )


def print_table(results: list[dict]) -> None:
    """按 RZCS 同类静态分组表格输出。"""

    status_handler.print_table(results)


def format_csv_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def get_result_csv_fields(rows: list[dict], path: Path) -> list[str]:
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
            for header in csv.reader(file_obj):
                if header:
                    return header + [field for field in default_fields if field not in header]
    return default_fields


def update_result_csv_header(path: Path, fieldnames: list[str]) -> None:
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
        writer.writerows({key: row.get(key, "") for key in fieldnames} for row in rows)


def append_simulation_results(
    rows: list[dict],
    path: Path = RESULT_CSV,
) -> None:
    """追加最终结果到 simulate_result.csv。"""

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
            writer.writerow(
                {key: format_csv_value(row.get(key, "")) for key in fieldnames}
            )


def parse_int_list(value: str | None) -> list[int] | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_bet_multis(value: str | None) -> list[list[int]] | None:
    """解析分号分隔的多组 Bet_Multi。"""

    if value is None:
        return None
    return [
        [int(item.strip()) for item in group.split(",") if item.strip()]
        for group in value.split(";")
        if group.strip()
    ]


def parse_seeds(value: str | None) -> list[int | None] | None:
    if value is None:
        return None
    result: list[int | None] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        result.append(None if item.lower() in {"none", "null", "random"} else int(item))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spins", type=int, default=SPIN_TIMES)
    parser.add_argument(
        "--bet-multis",
        default=None,
        help="多组下注用分号分隔；每组为symbol 0-9的逗号整数列表。",
    )
    parser.add_argument(
        "--bet-multi",
        default=None,
        help="单组Bet_Multi，兼容参数。",
    )
    parser.add_argument(
        "--double-times",
        default=None,
        help="逗号分隔的玩家倍乘尝试次数。",
    )
    parser.add_argument("--seeds", default=None, help="逗号分隔的随机种子或none。")
    parser.add_argument("--seed", type=int, default=None, help="单个随机种子，兼容参数。")
    parser.add_argument("--report-interval", type=int, default=REPORT_INTERVAL)
    parser.add_argument(
        "--no-print-updates",
        action="store_false",
        dest="print_updates",
        help="运行时不打印阶段统计表。",
    )
    parser.set_defaults(print_updates=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    bet_multis = parse_bet_multis(args.bet_multis)
    if bet_multis is None and args.bet_multi is not None:
        single_bet_multi = parse_int_list(args.bet_multi)
        bet_multis = [single_bet_multi] if single_bet_multi is not None else None
    seeds = parse_seeds(args.seeds)
    if seeds is None and args.seed is not None:
        seeds = [args.seed]
    results = simulation_all(
        spin_times=args.spins,
        bet_multis=bet_multis,
        double_times_values=parse_int_list(args.double_times),
        seeds=seeds,
        report_interval=args.report_interval,
        print_updates=args.print_updates,
    )
    print_table(results)
    append_simulation_results(results)
