"""模拟入口。

直接运行本文件会模拟一万次普通游戏 spin；如果普通游戏触发 free，
就按照返回的 free_times 进入免费游戏，并把普通游戏和免费游戏的赢钱合并统计。
"""

import sys
from configparser import ConfigParser

# Windows 控制台和工具读取 Python 输出时编码可能不一致，这里统一按 UTF-8 输出中文摘要。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    # 支持以 python -m mahj3.simulation 或包 import 的方式使用。
    from .theme_math import ThemeMath
except ImportError:
    # 支持直接运行 python .\mahj3\simulation.py。
    from theme_math import ThemeMath

# ThemeMath 会默认读取当前 mahj3 文件夹下的 game_config.conf、reel_config 和 free_reel_config。
m = ThemeMath()

SPIN_TIMES = 100000
INDEX = 0
GENERAL_INDEX = 1


def discover_indexes() -> list[int]:
    """从 reel_config 文件名中自动发现所有 index。"""

    indexes = []
    for path in m.reel_config_dir.glob("*.conf"):
        suffix = path.stem.rsplit("_", 1)[-1]
        if suffix.isdigit():
            indexes.append(int(suffix))
    return sorted(set(indexes))


def discover_general_indexes(index: int) -> list[int]:
    """读取指定 index 的普通轴文件，自动发现其中所有 GENERAL_n。"""

    path = m._find_reel_config_path(index)
    parser = ConfigParser(inline_comment_prefixes=("#", ";"))
    parser.optionxform = str
    parser.read(path, encoding="utf-8-sig")

    general_indexes = []
    for section_name in parser.sections():
        if not section_name.startswith("GENERAL_"):
            continue
        suffix = section_name[len("GENERAL_") :]
        if suffix.isdigit():
            general_indexes.append(int(suffix))
    return sorted(set(general_indexes))


def simulation(spin_times: int = SPIN_TIMES, index: int = INDEX, general_index: int = GENERAL_INDEX) -> dict:
    """模拟指定次数普通游戏；触发 free 后继续模拟对应次数的免费游戏。"""

    main_win = 0
    free_win = 0
    scatter_win = 0
    total_win_times = 0
    main_win_times = 0
    free_win_times = 0
    trigger_free_times = 0
    free_retrigger_times = 0
    free_spin_times = 0

    for _ in range(spin_times):
        spin_total_win = 0
        ng_result = m.ng_spin(index, general_index)
        ng_win = ng_result["total_win"]
        ng_scatter_win = ng_result.get("scatter_win", 0)
        main_win += ng_win
        scatter_win += ng_scatter_win
        spin_total_win += ng_win + ng_scatter_win
        if ng_win + ng_scatter_win > 0:
            main_win_times += 1

        if not ng_result.get("is_trigger_free"):
            if spin_total_win > 0:
                total_win_times += 1
            continue

        trigger_free_times += 1
        remaining_free_times = ng_result.get("free_times", 0)
        free_spin_times += remaining_free_times
        while remaining_free_times > 0:
            remaining_free_times -= 1
            fg_result = m.fg_spin(index, general_index)
            fg_win = fg_result["total_win"]
            fg_scatter_win = fg_result.get("scatter_win", 0)
            free_win += fg_win
            scatter_win += fg_scatter_win
            spin_total_win += fg_win + fg_scatter_win
            if fg_win + fg_scatter_win > 0:
                free_win_times += 1

            # free 中如果再次出现 3 个及以上 scatter，按 base 一样的规则追加 free 次数。
            retrigger_free_times = fg_result.get("free_times", 0)
            if retrigger_free_times > 0:
                free_retrigger_times += 1
                remaining_free_times += retrigger_free_times
                free_spin_times += retrigger_free_times

        if spin_total_win > 0:
            total_win_times += 1

    total_bet = spin_times * m.base_bet
    total_win = main_win + free_win + scatter_win
    return {
        "spin_times": spin_times,
        "index": index,
        "general_index": general_index,
        "total_bet": total_bet,
        "main_win": main_win,
        "free_win": free_win,
        "scatter_win": scatter_win,
        "total_win": total_win,
        "total_win_times": total_win_times,
        "main_win_times": main_win_times,
        "free_win_times": free_win_times,
        "main_rtp": main_win / total_bet if total_bet else 0,
        "free_rtp": free_win / total_bet if total_bet else 0,
        "scatter_rtp": scatter_win / total_bet if total_bet else 0,
        "total_rtp": total_win / total_bet if total_bet else 0,
        "win_rate": total_win_times / spin_times if spin_times else 0,
        "main_win_rate": main_win_times / spin_times if spin_times else 0,
        "free_win_rate": free_win_times / free_spin_times if free_spin_times else 0,
        "trigger_free_times": trigger_free_times,
        "free_retrigger_times": free_retrigger_times,
        "trigger_free_rate": trigger_free_times / spin_times if spin_times else 0,
        "free_spin_times": free_spin_times,
        "avg_free_spins_per_trigger": free_spin_times / trigger_free_times if trigger_free_times else 0,
    }


def simulation_all(
    spin_times: int = SPIN_TIMES,
    indexes: list[int] | None = None,
    general_indexes: list[int] | None = None,
) -> list[dict]:
    """一次运行所有 index 和 general_index 组合的模拟。"""

    results = []
    target_indexes = discover_indexes() if indexes is None else indexes
    # target_indexes = [0, 4]
    for index in target_indexes:
        target_general_indexes = (
            discover_general_indexes(index) if general_indexes is None else general_indexes
        )
        for general_index in target_general_indexes:
            try:
                result = simulation(spin_times=spin_times, index=index, general_index=general_index)
                result["ok"] = True
            except Exception as exc:
                result = {
                    "ok": False,
                    "spin_times": spin_times,
                    "index": index,
                    "general_index": general_index,
                    "error": str(exc),
                }
            results.append(result)
    return results


def print_summary(result: dict) -> None:
    """打印模拟结果摘要。"""

    print(f"模拟次数: {result['spin_times']}")
    print(f"index: {result['index']}, GENERAL_{result['general_index']}")
    print(f"总押注: {result['total_bet']}")
    print(f"普通游戏赢钱: {result['main_win']}")
    print(f"免费游戏赢钱: {result['free_win']}")
    print(f"Scatter 赢钱: {result['scatter_win']}")
    print(f"总赢钱: {result['total_win']}")
    print(f"普通游戏 RTP: {result['main_rtp']:.3%}")
    print(f"免费游戏 RTP: {result['free_rtp']:.3%}")
    print(f"Scatter RTP: {result['scatter_rtp']:.3%}")
    print(f"总 RTP: {result['total_rtp']:.3%}")
    print(f"赢钱次数: {result['total_win_times']}")
    print(f"赢钱率: {result['win_rate']:.3%}")
    print(f"普通游戏赢钱次数: {result['main_win_times']}")
    print(f"普通游戏赢钱率: {result['main_win_rate']:.3%}")
    print(f"免费游戏赢钱次数: {result['free_win_times']}")
    print(f"免费游戏赢钱率: {result['free_win_rate']:.3%}")
    print(f"触发 free 次数: {result['trigger_free_times']}")
    print(f"free 中再次触发 free 次数: {result['free_retrigger_times']}")
    print(f"触发 free 概率: {result['trigger_free_rate']:.3%}")
    print(f"免费游戏总次数: {result['free_spin_times']}")
    print(f"平均每次触发 free 次数: {result['avg_free_spins_per_trigger']:.6f}")


def print_table(results: list[dict]) -> None:
    """打印批量模拟结果表格。"""

    headers = [
        "INDEX",
        "GENERAL",
        "状态",
        "模拟次数",
        "普通RTP",
        "FreeRTP",
        "ScatterRTP",
        "总RTP",
        "赢钱率",
        "主赢率",
        "Free赢率",
        "触发Free",
        "触发率",
        "Free次数",
        "错误",
    ]
    rows = []
    for result in results:
        if not result.get("ok", True):
            rows.append(
                [
                    result["index"],
                    result["general_index"],
                    "失败",
                    result["spin_times"],
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    result["error"],
                ]
            )
            continue

        rows.append(
            [
                result["index"],
                result["general_index"],
                "成功",
                result["spin_times"],
                f"{result['main_rtp']:.3%}",
                f"{result['free_rtp']:.3%}",
                f"{result['scatter_rtp']:.3%}",
                f"{result['total_rtp']:.3%}",
                f"{result['win_rate']:.3%}",
                f"{result['main_win_rate']:.3%}",
                f"{result['free_win_rate']:.3%}",
                result["trigger_free_times"],
                f"{result['trigger_free_rate']:.3%}",
                result["free_spin_times"],
                "",
            ]
        )

    col_widths = [
        max(len(str(row[col_index])) for row in [headers] + rows)
        for col_index in range(len(headers))
    ]
    print(" | ".join(str(value).ljust(col_widths[index]) for index, value in enumerate(headers)))
    print("-+-".join("-" * width for width in col_widths))
    for row in rows:
        print(" | ".join(str(value).ljust(col_widths[index]) for index, value in enumerate(row)))


if __name__ == "__main__":
    # 直接运行时自动跑完所有 index 和 GENERAL_n 组合，避免手动逐个改常量。
    print_table(simulation_all())
