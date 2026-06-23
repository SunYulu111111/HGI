"""收集 free 中赢钱的牌面。

给定目标数量 X 后，脚本会不断执行 fg_spin，直到收集到 X 个
total_win > 0 的 free 牌面，或达到最大尝试次数。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from .theme_math import ThemeMath
except ImportError:
    from theme_math import ThemeMath


DEFAULT_INDEX = 0
DEFAULT_CHOOSE_INDEX = 1
DEFAULT_COUNT = 10
DEFAULT_FREE_GENERAL_INDEX = None
DEFAULT_MAX_SPINS = 100000
DEFAULT_SEED = None
DEFAULT_INCLUDE_ROUNDS = False
DEFAULT_EXCLUDE_SCATTER = True
DEFAULT_RESULT_PREFIX = "ZERO_RESULT"
DEFAULT_OUTPUT_FORMAT = "conf"
DEFAULT_OUTPUT = Path(__file__).with_name("free_win_boards.conf")


def board_to_rows(board: list[list[int]]) -> list[list[int | None]]:
    """把内部列格式牌面转成更方便查看的行格式。"""
    max_height = max((len(col_items) for col_items in board), default=0)
    return [
        [
            col_items[row_index] if row_index < len(col_items) else None
            for col_items in board
        ]
        for row_index in range(max_height)
    ]


def clone_board(board: list[list[int]]) -> list[list[int]]:
    """复制牌面，避免后续消除流程修改原始停轴结果。"""
    return [list(col_items) for col_items in board]


def flatten_board_col_major(board: list[list[int]], row: int, col: int) -> list[int]:
    """按配置格式把 [列][行] 牌面压平成 col * row 个数。"""
    if len(board) < col:
        raise ValueError(f"board has {len(board)} columns but {col} are required")
    for col_index in range(col):
        if len(board[col_index]) < row:
            raise ValueError(
                f"board column {col_index + 1} has {len(board[col_index])} rows but {row} are required"
            )
    return [
        board[col_index][row_index]
        for col_index in range(col)
        for row_index in range(row)
    ]


def format_result_line(prefix: str, result_index: int, values: list[int]) -> str:
    """生成类似 ZERO_RESULT_1=1,2,3 的配置行。"""
    return f"{prefix}_{result_index}=" + ",".join(str(value) for value in values)


def has_scatter(values: list[int], scatter_id: int) -> bool:
    """判断结果中是否包含 scatter。"""
    return any(value == scatter_id for value in values)


def install_raw_spin_capture(math: ThemeMath) -> None:
    """捕获 fg_spin 中 spin() 生成的原始 5x6 停轴牌面。"""
    original_spin = math.spin

    def captured_spin(*args, **kwargs):
        board = original_spin(*args, **kwargs)
        math.last_raw_spin_board = clone_board(board)
        return board

    math.last_raw_spin_board = []
    math.spin = captured_spin


def summarize_rounds(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """保留每轮消除的关键信息，避免输出过大的补牌详情。"""
    summary = []
    for round_info in rounds:
        summary.append(
            {
                "cascade_index": round_info["cascade_index"],
                "total_win": round_info["total_win"],
                "raw_total_win": round_info["raw_total_win"],
                "win_multiplier": round_info["win_multiplier"],
                "win_items": round_info["win_items"],
                "win_positions": round_info["win_positions"],
                "item_list": round_info["item_list"],
                "item_rows": board_to_rows(round_info["item_list"]),
            }
        )
    return summary


def build_record(
    result: dict[str, Any],
    raw_item_list: list[list[int]],
    raw_result_values: list[int],
    result_prefix: str,
    found_index: int,
    spin_index: int,
    include_rounds: bool,
) -> dict[str, Any]:
    """把一次赢钱的 free spin 结果整理成稳定的输出结构。"""
    item_list = result["item_list"]
    final_item_list = result["final_item_list"]
    record = {
        "found_index": found_index,
        "spin_index": spin_index,
        "total_win": result["total_win"],
        "cascade_count": result["cascade_count"],
        "scatter_count": result["scatter_count"],
        "free_times": result["free_times"],
        "max_round_num": result["max_round_num"],
        "spin_info": result["spin_info"],
        "raw_item_list_5x6": raw_item_list,
        "raw_item_rows_5x6": board_to_rows(raw_item_list),
        "raw_result_values": raw_result_values,
        "result_line": format_result_line(result_prefix, found_index, raw_result_values),
        "item_list": item_list,
        "item_rows": board_to_rows(item_list),
        "final_item_list": final_item_list,
        "final_item_rows": board_to_rows(final_item_list),
        "final_top_indexes": result["final_top_indexes"],
    }
    if include_rounds:
        record["rounds"] = summarize_rounds(result["rounds"])
    return record


def collect_free_win_boards(
    count: int,
    index: int,
    choose_index: int,
    free_general_index: int | None,
    max_spins: int,
    seed: int | None,
    include_rounds: bool,
    exclude_scatter: bool,
    result_prefix: str,
) -> dict[str, Any]:
    """执行 free spin，收集指定数量的赢钱牌面。"""
    if count <= 0:
        raise ValueError("count 必须大于 0")
    if max_spins <= 0:
        raise ValueError("max_spins 必须大于 0")
    if seed is not None:
        random.seed(seed)

    math = ThemeMath()
    install_raw_spin_capture(math)
    source_row = math.config.row_count
    source_col = math.config.col_count
    scatter_id = math.SCATTER_ID
    records = []
    scatter_skipped = 0
    spin_index = 0
    while len(records) < count and spin_index < max_spins:
        spin_index += 1
        result = math.fg_spin(
            index=index,
            choose_index=choose_index,
            free_general_index=free_general_index,
            return_detail=True,
        )
        if result["total_win"] <= 0:
            continue

        raw_item_list = clone_board(math.last_raw_spin_board)
        raw_result_values = flatten_board_col_major(raw_item_list, row=source_row, col=source_col)
        if exclude_scatter and has_scatter(raw_result_values, scatter_id):
            scatter_skipped += 1
            continue

        records.append(
            build_record(
                result=result,
                raw_item_list=raw_item_list,
                raw_result_values=raw_result_values,
                result_prefix=result_prefix,
                found_index=len(records) + 1,
                spin_index=spin_index,
                include_rounds=include_rounds,
            )
        )

    return {
        "request": {
            "count": count,
            "index": index,
            "choose_index": choose_index,
            "free_general_index": free_general_index,
            "max_spins": max_spins,
            "seed": seed,
            "include_rounds": include_rounds,
            "exclude_scatter": exclude_scatter,
            "scatter_id": scatter_id,
            "result_prefix": result_prefix,
        },
        "spins": spin_index,
        "wins_found": len(records),
        "scatter_skipped": scatter_skipped,
        "result_lines": [record["result_line"] for record in records],
        "boards": records,
    }


def format_conf_result(result: dict[str, Any]) -> str:
    """生成可直接复制到配置中的结果行。"""
    return "\n".join(result["result_lines"])


def write_result(
    result: dict[str, Any],
    output: Path | None,
    count: int,
    output_format: str,
) -> None:
    """输出收集结果；传 output 时写 JSON，否则打印到控制台。"""
    if output_format == "json":
        text = json.dumps(result, ensure_ascii=False, indent=2)
    elif output_format == "conf":
        text = format_conf_result(result)
    else:
        raise ValueError(f"unknown output format: {output_format}")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
        print(
            f"已收集 {result['wins_found']}/{count} 个赢钱牌面，"
            f"尝试 {result['spins']} 次，输出到 {output}"
        )
    else:
        print(text)


def check_free_win_boards() -> int:
    """直接在这里配置参数，然后运行脚本收集 free 赢钱牌面。"""
    count = DEFAULT_COUNT
    index = DEFAULT_INDEX
    choose_index = DEFAULT_CHOOSE_INDEX
    free_general_index = DEFAULT_FREE_GENERAL_INDEX
    max_spins = DEFAULT_MAX_SPINS
    seed = DEFAULT_SEED
    include_rounds = DEFAULT_INCLUDE_ROUNDS
    exclude_scatter = DEFAULT_EXCLUDE_SCATTER
    result_prefix = DEFAULT_RESULT_PREFIX
    output_format = DEFAULT_OUTPUT_FORMAT
    output = DEFAULT_OUTPUT

    result = collect_free_win_boards(
        count=count,
        index=index,
        choose_index=choose_index,
        free_general_index=free_general_index,
        max_spins=max_spins,
        seed=seed,
        include_rounds=include_rounds,
        exclude_scatter=exclude_scatter,
        result_prefix=result_prefix,
    )
    write_result(result, output=output, count=count, output_format=output_format)
    return 0 if result["wins_found"] == count else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="收集 X 个 free 中赢钱的牌面。")
    parser.add_argument(
        "count",
        type=int,
        nargs="?",
        default=DEFAULT_COUNT,
        help=f"需要收集的赢钱牌面数量 X，默认 {DEFAULT_COUNT}。",
    )
    parser.add_argument("--index", type=int, default=DEFAULT_INDEX, help="轴配置 index，默认 0。")
    parser.add_argument(
        "--choose-index",
        type=int,
        default=DEFAULT_CHOOSE_INDEX,
        help="free 选择档位，默认 1。",
    )
    parser.add_argument(
        "--free-general",
        type=int,
        default=DEFAULT_FREE_GENERAL_INDEX,
        help="指定 free_reel_config 中的 GENERAL，下传时覆盖 choose 对应的 GENERAL。",
    )
    parser.add_argument(
        "--max-spins",
        type=int,
        default=DEFAULT_MAX_SPINS,
        help="最多尝试的 free spin 次数，默认 100000。",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子，便于复现。")
    parser.add_argument(
        "--include-rounds",
        action="store_true",
        help="输出每轮消除详情；默认只输出初始和最终牌面。",
    )
    parser.add_argument(
        "--allow-scatter",
        action="store_false",
        dest="exclude_scatter",
        help="允许输出包含 scatter 的初始牌面；默认会过滤掉 scatter。",
    )
    parser.set_defaults(exclude_scatter=DEFAULT_EXCLUDE_SCATTER)
    parser.add_argument(
        "--result-prefix",
        default=DEFAULT_RESULT_PREFIX,
        help=f"生成配置行的前缀，默认 {DEFAULT_RESULT_PREFIX}。",
    )
    parser.add_argument(
        "--format",
        choices=("conf", "json"),
        default=DEFAULT_OUTPUT_FORMAT,
        help="输出格式；conf 只输出 ZERO_RESULT_n 行，json 输出完整详情。",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"输出 JSON 文件路径，默认 {DEFAULT_OUTPUT}；传空字符串则打印到控制台。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output) if args.output.strip() else None
    result = collect_free_win_boards(
        count=args.count,
        index=args.index,
        choose_index=args.choose_index,
        free_general_index=args.free_general,
        max_spins=args.max_spins,
        seed=args.seed,
        include_rounds=args.include_rounds,
        exclude_scatter=args.exclude_scatter,
        result_prefix=args.result_prefix,
    )

    write_result(result, output=output, count=args.count, output_format=args.format)
    return 0 if result["wins_found"] == args.count else 1


if __name__ == "__main__":
    raise SystemExit(check_free_win_boards() if len(sys.argv) == 1 else main())
