"""恐龙世界仿真：统计付费游戏、免费次数和总奖励。"""

from __future__ import annotations

import argparse
import json
import random

from theme_math import ThemeMath


def simulate(
    spins: int,
    base_bet: int = 10000,
    index: int = 0,
    general_index: int = 1,
    seed: int | None = None,
) -> dict:
    if spins <= 0:
        raise ValueError("spins must be positive")
    if seed is not None:
        random.seed(seed)
    game = ThemeMath(base_bet=base_bet)
    main_win = 0
    free_win = 0
    main_hits = 0
    triggers = 0
    free_spins = 0

    for _ in range(spins):
        main = game.ng_spin(index=index, general_index=general_index)
        main_win += main["TotalWin"]
        main_hits += main["TotalWin"] > 0
        remaining = main["FreeSpinsAwarded"]
        if not 0 <= remaining <= game.FreeMaxTimes:
            raise RuntimeError("initial free award exceeds the generated Scatter budget")
        if remaining:
            triggers += 1
        free_spin_number = 0
        # 首手免费从 1 开始，后续继承终倍加 1；追加次数不重置倍数。
        FreeStartMultiplier = 1
        while remaining:
            remaining -= 1
            free_spin_number += 1
            free_spins += 1
            free = game.fg_spin(
                index=index,
                general_index=general_index,
                FreeSpinNumber=free_spin_number,
                FreeStartMultiplier=FreeStartMultiplier,
                FreeSpinsRemaining=remaining,
            )
            free_win += free["TotalWin"]
            if not 0 <= free["ExtraFreeSpins"] <= game.FreeMaxTimes - free_spin_number - remaining:
                raise RuntimeError("extra free award exceeds the generated Scatter budget")
            remaining += free["ExtraFreeSpins"]
            FreeStartMultiplier = free["FreeEndMultiplier"] + 1

    total_bet = spins * base_bet
    return {
        "ProvisionalConfig": True,
        "PaidSpins": spins,
        "FreeSpins": free_spins,
        "MainHits": main_hits,
        "FreeTriggers": triggers,
        "TotalBet": total_bet,
        "MainWin": main_win,
        "FreeWin": free_win,
        "TotalWin": main_win + free_win,
        "Rtp": (main_win + free_win) / total_bet,
        "MainHitRate": main_hits / spins,
        "FreeTriggerRate": triggers / spins,
        "AverageFreeSpinsPerTrigger": free_spins / triggers if triggers else 0,
        "Seed": seed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="恐龙世界临时配置仿真")
    parser.add_argument("--spins", type=int, default=1000)
    parser.add_argument("--base-bet", type=int, default=10000)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--general-index", type=int, default=1)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    print(
        json.dumps(
            simulate(args.spins, args.base_bet, args.index, args.general_index, args.seed),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
