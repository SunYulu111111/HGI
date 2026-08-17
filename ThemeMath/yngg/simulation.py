"""Small reproducible simulation entry point for yngg's published reel sets."""

from __future__ import annotations

import argparse

from theme_math import ThemeMath


def simulation(
    spin_times: int = 100_000,
    base_bet: int = 100_000,
    index: int = 0,
    general_index: int = 1,
    free_game: bool = False,
) -> dict:
    if spin_times <= 0:
        raise ValueError("spin_times must be positive")
    math = ThemeMath(base_bet=base_bet)
    total_win = 0
    hit_count = 0
    cascade_count = 0
    for _ in range(spin_times):
        if free_game:
            result = math.fg_spin(index=index, general_index=general_index)
        else:
            result = math.ng_spin(index=index, general_index=general_index)
        total_win += result["total_win"]
        hit_count += result["total_win"] > 0
        cascade_count += result["cascade_count"]
    total_bet = spin_times * base_bet
    return {
        "spin_times": spin_times,
        "base_bet": base_bet,
        "total_bet": total_bet,
        "total_win": total_win,
        "rtp": total_win / total_bet,
        "hit_frequency": hit_count / spin_times,
        "average_cascades": cascade_count / spin_times,
        "free_game": free_game,
        "note": (
            "Configured Scatter/Bonus and golden-area RNG are included; "
            "free-session guarantee state is not simulated."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spins", type=int, default=100_000)
    parser.add_argument("--base-bet", type=int, default=100_000)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--general-index", type=int, default=1)
    parser.add_argument("--free-game", action="store_true")
    args = parser.parse_args()
    result = simulation(
        spin_times=args.spins,
        base_bet=args.base_bet,
        index=args.index,
        general_index=args.general_index,
        free_game=args.free_game,
    )
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
