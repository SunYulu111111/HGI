"""按等权位置分组，用不放回抽样的状态递推计算理论 RTP（不含砍分和翻倍）。"""
from collections import defaultdict
from theme_math import ThemeMath


def calculate_rtp(math):
    def expected_x(index):
        symbol = math.reel_config[index]
        value = math.multi_config[index]
        if value != 1:
            return value
        if symbol == 9:
            return 5
        values = (math.high_symbol_multipliers if symbol in (3, 4, 5)
                  else math.low_symbol_multipliers)
        return sum(w * x for w, x in zip(math.symbol_multi_weights, values)) / sum(math.symbol_multi_weights)

    groups = defaultdict(list)
    for index, weight in enumerate(math.bonus_win_weights):
        if weight > 0:
            groups[weight].append(index)
    weights = list(groups)
    positions = list(groups.values())
    counts = [len(group) for group in positions]
    expected_counts = [0.0] * len(weights)
    states = {(0,) * len(weights): 1.0}
    count_total = sum(math.respin_count_weights)
    for draw, count_weight in enumerate(math.respin_count_weights, 1):
        next_states = defaultdict(float)
        for state, probability in states.items():
            remaining = [(n - taken) * w for n, taken, w in zip(counts, state, weights)]
            total = sum(remaining)
            if not total:
                continue
            for group, weight in enumerate(remaining):
                if weight:
                    updated = list(state)
                    updated[group] += 1
                    next_states[tuple(updated)] += probability * weight / total
        states = next_states
        for state, probability in states.items():
            for group, taken in enumerate(state):
                expected_counts[group] += probability * taken * count_weight / count_total
    bonus = {symbol: 0.0 for symbol in math.BET_SYMBOL_IDS}
    for group, indexes in enumerate(positions):
        inclusion = expected_counts[group] / len(indexes)
        for index in indexes:
            symbol = math.reel_config[index]
            bonus[symbol] += inclusion * expected_x(index) * math.item_prizes[symbol] / math.base_bet
    total = sum(math.win_weights)
    bonus_weight = sum(w for s, w in zip(math.reel_config, math.win_weights) if s == 0)
    rtp = {}
    for symbol in math.BET_SYMBOL_IDS:
        normal = sum(w * expected_x(i) * math.item_prizes[symbol] / math.base_bet
                     for i, (s, w) in enumerate(zip(math.reel_config, math.win_weights)) if s == symbol)
        rtp[symbol] = (normal + bonus_weight * bonus[symbol]) / total
    return bonus, rtp


if __name__ == '__main__':
    math = ThemeMath()
    bonus, rtp = calculate_rtp(math)
    for symbol in math.BET_SYMBOL_IDS:
        print(f'Symbol {symbol}: Bonus期望倍数={bonus[symbol]:.12f}, RTP={rtp[symbol]:.12f}')
