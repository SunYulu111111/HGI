"""运行水果机固定下注组合的蒙特卡洛模拟。"""

from __future__ import annotations

import argparse
import json
import random

from theme_math import ThemeMath


Bet_Multi = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1]
#每次赢钱后最多主动尝试的翻倍次数，0表示不翻倍
Double_Times = 0


def build_symbol_bets(math: ThemeMath, bet_multi: list[int]) -> dict[int, int]:
    """按 symbol id 读取倍数，实际下注为 BaseBet * Bet_Multi[symbol_id]。"""

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


def simulate(
    spins: int,
    bet_multi: list[int] | None = None,
    double_times: int | None = None,
    seed: int | None = None,
) -> dict:
    if spins <= 0:
        raise ValueError("spins 必须大于 0")

    math = ThemeMath(rng=random.Random(seed))
    bet_multi = Bet_Multi if bet_multi is None else bet_multi
    double_times = Double_Times if double_times is None else double_times
    bets = build_symbol_bets(math, bet_multi)
    total_bet = 0
    base_total_win = 0
    total_win = 0
    bonus_count = 0
    hit_count = 0
    double_attempt_count = 0
    double_success_count = 0
    double_fail_count = 0
    double_selected_counts = [0] * (math.double_max_times + 1)
    double_weight_key_counts: dict[str, int] = {}
    for _ in range(spins):
        result = math.spin(
            bets,
            return_detail=False,
            double_times=double_times,
        )
        total_bet += result["total_bet"]
        base_total_win += result["base_win"]
        total_win += result["total_win"]
        bonus_count += int(result["is_bonus"])
        hit_count += int(result["total_win"] > 0)
        double_attempt_count += result["double_result"]["attempted_times"]
        double_success_count += result["double_result"]["success_times"]
        double_fail_count += int(result["double_result"]["failed"])
        selected_times = result["double_result"]["selected_times"]
        if selected_times is not None:
            double_selected_counts[selected_times] += 1
        double_weight_key = result["double_result"]["double_weight_key"]
        if double_weight_key is not None:
            double_weight_key_counts[double_weight_key] = (
                double_weight_key_counts.get(double_weight_key, 0) + 1
            )

    return {
        "spins": spins,
        "seed": seed,
        "bet_multi": list(bet_multi),
        "double_times": double_times,
        "bets": bets,
        "total_bet": total_bet,
        "base_total_win": base_total_win,
        "total_win": total_win,
        "rtp": total_win / total_bet,
        "hit_rate": hit_count / spins,
        "bonus_rate": bonus_count / spins,
        "double_attempt_count": double_attempt_count,
        "double_success_count": double_success_count,
        "double_fail_count": double_fail_count,
        "double_selected_counts": double_selected_counts,
        "double_weight_key_counts": double_weight_key_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spins", type=int, default=100_000)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    print(
        json.dumps(
            simulate(args.spins, seed=args.seed),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
