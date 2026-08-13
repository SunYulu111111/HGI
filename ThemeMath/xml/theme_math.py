"""水果机主题数学入口。

玩家可分别对 symbol 2-9 下注。每局先按 WinWeightConfig 抽取一个轮盘
index；若该位置是 symbol 0，则按 BonusWinWeightConfig 加权、不放回地
抽取八个不同 index。赢钱后可选择翻倍，成功则赢钱乘 2 并可继续，失败归零。
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from configparser import ConfigParser
from pathlib import Path


class ThemeMath:
    """基于配置的单轮盘水果机数学实现。"""

    BET_SYMBOL_IDS = tuple(range(2, 10))
    BONUS_SYMBOL_ID = 0
    BONUS_PICK_COUNT = 8
    DEFAULT_GAME_CONFIG_FILE = Path("special") / "xml_game_config.conf"
    DEFAULT_GAME_SERVER_CONFIG_FILE = Path("special") / "xml_game_server.conf"

    def __init__(
        self,
        project_dir: str | Path | None = None,
        game_config_file: str | Path = DEFAULT_GAME_CONFIG_FILE,
        game_server_config_file: str | Path = DEFAULT_GAME_SERVER_CONFIG_FILE,
        rng: random.Random | None = None,
    ):
        self.project_dir = Path(project_dir or Path(__file__).resolve().parent)
        self.game_config_file = self._resolve_config_path(game_config_file)
        self.game_server_config_file = self._resolve_config_path(game_server_config_file)
        self.rng = rng or random.Random()

        game_config = self._read_config(self.game_config_file)
        server_config = self._read_config(self.game_server_config_file)
        self.game_server_config = server_config
        if not game_config.has_section("MAIN"):
            raise ValueError(f"{self.game_config_file} 缺少 [MAIN]")
        if not server_config.has_section("Game Info"):
            raise ValueError(f"{self.game_server_config_file} 缺少 [Game Info]")

        main = game_config["MAIN"]
        game_info = server_config["Game Info"]
        self.base_bet = self._parse_positive_int(main.get("BaseBet"), "BaseBet")
        self.item_count = self._parse_positive_int(main.get("ITEM_COUNT"), "ITEM_COUNT")
        self.item_prizes = self._load_item_prizes(main)
        self.reel_config = self._parse_int_list(game_info.get("ReelConfig"), "ReelConfig")
        self.multi_config = self._parse_int_list(game_info.get("MultiConfig"), "MultiConfig")
        self.win_weights = self._parse_int_list(
            game_info.get("WinWeightConfig"),
            "WinWeightConfig",
        )
        self.bonus_win_weights = self._parse_int_list(
            game_info.get("BonusWinWeightConfig"),
            "BonusWinWeightConfig",
        )
        self.double_enabled = self._parse_enabled(
            game_info.get("DoubleEnabled"),
            "DoubleEnabled",
        )
        self.double_max_times = self._parse_nonnegative_int(
            game_info.get("DoubleMaxTimes"),
            "DoubleMaxTimes",
        )
        self.double_multiple = self._parse_positive_int(
            game_info.get("DoubleMultiple"),
            "DoubleMultiple",
        )
        self.double_weights = self._parse_int_list(
            game_info.get("DoubleWeight"),
            "DoubleWeight",
        )
        self.double_weight_tiers = self._load_double_weight_tiers(game_info)
        self._validate_configuration()
        self.last_ng_result: dict = {}

    def spin(
        self,
        symbol_bets: Mapping[int, int],
        return_detail: bool = True,
        double_times: int = 0,
    ) -> dict:
        """执行一次水果机 spin。"""

        return self.ng_spin(
            symbol_bets,
            return_detail=return_detail,
            double_times=double_times,
        )

    def ng_spin(
        self,
        symbol_bets: Mapping[int, int],
        return_detail: bool = False,
        double_times: int = 0,
    ) -> dict:
        """校验各 symbol 注额、抽取轮盘位置并结算。"""

        bets = self.validate_bets(symbol_bets)
        trigger_index = self._weighted_index(self.win_weights)
        trigger_symbol_id = self.reel_config[trigger_index]
        is_bonus = trigger_symbol_id == self.BONUS_SYMBOL_ID

        if is_bonus:
            winning_indexes = self._weighted_sample_without_replacement(
                self.bonus_win_weights,
                self.BONUS_PICK_COUNT,
            )
        else:
            winning_indexes = [trigger_index]

        outcomes = [self._settle_index(index, bets) for index in winning_indexes]
        paid_items = [outcome.copy() for outcome in outcomes if outcome["win"] > 0]
        base_win = sum(outcome["win"] for outcome in outcomes)
        total_bet = sum(bets.values())
        double_result = self.apply_double_up(
            base_win,
            double_times,
            total_bet=total_bet,
        )
        trigger = {
            "index": trigger_index,
            "position": trigger_index + 1,
            "symbol_id": trigger_symbol_id,
            "multiplier": self.multi_config[trigger_index],
        }
        result = {
            "bets": bets,
            "total_bet": total_bet,
            "base_win": base_win,
            "total_win": double_result["total_win"],
            "trigger_index": trigger_index,
            "trigger_symbol_id": trigger_symbol_id,
            "is_bonus": is_bonus,
            "winning_indexes": winning_indexes,
            "winning_symbol_ids": [outcome["symbol_id"] for outcome in outcomes],
            "outcomes": outcomes if return_detail else [],
            "win_items": paid_items if return_detail else [],
            "double_result": double_result,
            "spin_info": {
                "trigger": trigger,
                "bonus_pick_count": len(winning_indexes) if is_bonus else 0,
                "double_attempted_times": double_result["attempted_times"],
            },
        }
        self.last_ng_result = result
        return result

    def validate_bets(self, symbol_bets: Mapping[int, int]) -> dict[int, int]:
        """下注必须覆盖至少一个有效 symbol，且每注为 BaseBet 的正整数倍。"""

        if not isinstance(symbol_bets, Mapping):
            raise TypeError("symbol_bets 必须是 {symbol_id: bet} 映射")
        if not symbol_bets:
            raise ValueError("至少需要选择一个 symbol 下注")

        bets: dict[int, int] = {}
        for symbol_id, bet in symbol_bets.items():
            if isinstance(symbol_id, bool) or not isinstance(symbol_id, int):
                raise TypeError("symbol id 必须是整数")
            if symbol_id not in self.BET_SYMBOL_IDS:
                raise ValueError(f"只能对 symbol {self.BET_SYMBOL_IDS} 下注，收到 {symbol_id}")
            if isinstance(bet, bool) or not isinstance(bet, int):
                raise TypeError(f"symbol {symbol_id} 的下注必须是整数")
            if bet <= 0 or bet % self.base_bet != 0:
                raise ValueError(
                    f"symbol {symbol_id} 的下注必须是 BaseBet({self.base_bet}) 的正整数倍"
                )
            bets[symbol_id] = bet
        return dict(sorted(bets.items()))

    def get_double_weight_config(
        self,
        win_amount: int,
        total_bet: int,
    ) -> tuple[str, list[int]]:
        """按初始赢钱倍数选择最小适用的 DoubleWeight_X。"""

        self._validate_win_amount(win_amount)
        if isinstance(total_bet, bool) or not isinstance(total_bet, int):
            raise TypeError("total_bet 必须是整数")
        if total_bet <= 0:
            raise ValueError("total_bet 必须大于 0")

        for threshold, weights in self.double_weight_tiers.items():
            if win_amount <= total_bet * threshold:
                return f"DoubleWeight_{threshold}", weights
        return "DoubleWeight", self.double_weights

    def select_double_times(self, win_amount: int, total_bet: int) -> int:
        """按赢钱倍数对应的权重一次选出允许成功倍乘的次数。"""

        if not self.double_enabled:
            raise ValueError("翻倍玩法未启用")
        _, weights = self.get_double_weight_config(win_amount, total_bet)
        return self._weighted_index(weights)

    def double_win(
        self,
        win_amount: int,
        completed_times: int = 0,
        selected_times: int | None = None,
        total_bet: int | None = None,
        double_weight_key: str | None = None,
    ) -> dict:
        """按本局预选次数执行一次翻倍，超过预选次数时失败归零。"""

        if not self.double_enabled:
            raise ValueError("翻倍玩法未启用")
        self._validate_win_amount(win_amount)
        if isinstance(completed_times, bool) or not isinstance(completed_times, int):
            raise TypeError("completed_times 必须是整数")
        if completed_times < 0 or completed_times >= self.double_max_times:
            raise ValueError(f"翻倍次数必须小于 {self.double_max_times}")

        if selected_times is None:
            total_bet = self.base_bet if total_bet is None else total_bet
            double_weight_key, weights = self.get_double_weight_config(
                win_amount,
                total_bet,
            )
            selected_times = self._weighted_index(weights)
        if isinstance(selected_times, bool) or not isinstance(selected_times, int):
            raise TypeError("selected_times 必须是整数")
        if selected_times < 0 or selected_times > self.double_max_times:
            raise ValueError(f"selected_times 必须为 0-{self.double_max_times}")

        success = completed_times < selected_times
        total_win = win_amount * self.double_multiple if success else 0
        attempted_times = completed_times + 1
        return {
            "attempt": attempted_times,
            "win_before": win_amount,
            "success": success,
            "selected_times": selected_times,
            "double_weight_key": double_weight_key,
            "total_win": total_win,
            "can_double": success and attempted_times < self.double_max_times,
        }

    def apply_double_up(
        self,
        win_amount: int,
        double_times: int = 0,
        total_bet: int | None = None,
    ) -> dict:
        """按玩家选择的次数连续翻倍，失败或达到次数后立即停止。"""

        self._validate_win_amount(win_amount, allow_zero=True)
        if isinstance(double_times, bool) or not isinstance(double_times, int):
            raise TypeError("double_times 必须是整数")
        if double_times < 0 or double_times > self.double_max_times:
            raise ValueError(f"double_times 必须为 0-{self.double_max_times}")
        if double_times > 0 and not self.double_enabled:
            raise ValueError("翻倍玩法未启用")

        total_bet = self.base_bet if total_bet is None else total_bet
        if isinstance(total_bet, bool) or not isinstance(total_bet, int):
            raise TypeError("total_bet 必须是整数")
        if total_bet <= 0:
            raise ValueError("total_bet 必须大于 0")

        current_win = win_amount
        rounds: list[dict] = []
        selected_times = None
        double_weight_key = None
        if double_times > 0 and current_win > 0:
            double_weight_key, weights = self.get_double_weight_config(
                current_win,
                total_bet,
            )
            selected_times = self._weighted_index(weights)
        for _ in range(double_times):
            if current_win == 0:
                break
            round_result = self.double_win(
                current_win,
                completed_times=len(rounds),
                selected_times=selected_times,
                total_bet=total_bet,
                double_weight_key=double_weight_key,
            )
            rounds.append(round_result)
            current_win = round_result["total_win"]
            if not round_result["success"]:
                break

        success_times = sum(round_result["success"] for round_result in rounds)
        return {
            "base_win": win_amount,
            "requested_times": double_times,
            "selected_times": selected_times,
            "double_weight_key": double_weight_key,
            "win_multiple": win_amount / total_bet,
            "attempted_times": len(rounds),
            "success_times": success_times,
            "failed": bool(rounds and not rounds[-1]["success"]),
            "total_win": current_win,
            "can_double": (
                self.double_enabled
                and current_win > 0
                and len(rounds) < self.double_max_times
            ),
            "rounds": rounds,
        }

    @staticmethod
    def _validate_win_amount(win_amount: int, allow_zero: bool = False) -> None:
        if isinstance(win_amount, bool) or not isinstance(win_amount, int):
            raise TypeError("win_amount 必须是整数")
        minimum = 0 if allow_zero else 1
        if win_amount < minimum:
            raise ValueError(f"win_amount 必须大于等于 {minimum}")

    def _settle_index(self, index: int, bets: Mapping[int, int]) -> dict:
        symbol_id = self.reel_config[index]
        multiplier = self.multi_config[index]
        bet = bets.get(symbol_id, 0)
        item_prize = self.item_prizes.get(symbol_id, 0)
        win = self._calculate_win(bet, item_prize, multiplier)
        return {
            "index": index,
            "position": index + 1,
            "symbol_id": symbol_id,
            "bet": bet,
            "item_prize": item_prize,
            "multiplier": multiplier,
            "win": win,
        }

    def _calculate_win(self, bet: int, item_prize: int, multiplier: int) -> int:
        if bet == 0:
            return 0
        numerator = bet * item_prize * multiplier
        win, remainder = divmod(numerator, self.base_bet)
        if remainder:
            raise ValueError(
                "派彩结果不是整数，请检查 bet、BaseBet、ITEM_PRIZE 和 MultiConfig"
            )
        return win

    def _weighted_index(
        self,
        weights: Sequence[int],
        candidates: Sequence[int] | None = None,
    ) -> int:
        available = list(range(len(weights))) if candidates is None else list(candidates)
        total_weight = sum(weights[index] for index in available)
        if total_weight <= 0:
            raise ValueError("可选 index 的权重总和必须大于 0")

        hit = self.rng.randrange(total_weight)
        current_weight = 0
        for index in available:
            current_weight += weights[index]
            if hit < current_weight:
                return index
        raise RuntimeError("权重抽取未命中任何 index")

    def _weighted_sample_without_replacement(
        self,
        weights: Sequence[int],
        count: int,
    ) -> list[int]:
        candidates = [index for index, weight in enumerate(weights) if weight > 0]
        if len(candidates) < count:
            raise ValueError(f"Bonus 正权重 index 少于 {count} 个")

        selected: list[int] = []
        for _ in range(count):
            index = self._weighted_index(weights, candidates)
            selected.append(index)
            candidates.remove(index)
        return selected

    def _load_item_prizes(self, main) -> dict[int, int]:
        prizes: dict[int, int] = {}
        for symbol_id in self.BET_SYMBOL_IDS:
            key = f"ITEM_PRIZE_{symbol_id}"
            if key not in main:
                raise ValueError(f"缺少 {key}")
            prizes[symbol_id] = int(main[key].strip())
        return prizes

    def _load_double_weight_tiers(self, game_info) -> dict[int, list[int]]:
        tiers: dict[int, list[int]] = {}
        prefix = "DoubleWeight_"
        for key, value in game_info.items():
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix) :]
            try:
                threshold = int(suffix)
            except ValueError as exc:
                raise ValueError(f"{key} 的后缀必须是整数") from exc
            if threshold <= 0 or threshold > 100:
                raise ValueError(f"{key} 的阈值必须为 1-100")
            tiers[threshold] = self._parse_int_list(value, key)
        if 100 not in tiers:
            raise ValueError("必须配置 DoubleWeight_100")
        return dict(sorted(tiers.items()))

    def _validate_configuration(self) -> None:
        lengths = {
            len(self.reel_config),
            len(self.multi_config),
            len(self.win_weights),
            len(self.bonus_win_weights),
        }
        if len(lengths) != 1 or not self.reel_config:
            raise ValueError(
                "ReelConfig、MultiConfig、WinWeightConfig 和 "
                "BonusWinWeightConfig 必须非空且长度一致"
            )
        if self.item_count <= max(self.reel_config):
            raise ValueError("ITEM_COUNT 必须大于 ReelConfig 中最大的 symbol id")

        valid_reel_symbols = {self.BONUS_SYMBOL_ID, *self.BET_SYMBOL_IDS}
        invalid_symbols = set(self.reel_config) - valid_reel_symbols
        if invalid_symbols:
            raise ValueError(f"ReelConfig 包含无效 symbol: {sorted(invalid_symbols)}")
        if any(multiplier <= 0 for multiplier in self.multi_config):
            raise ValueError("MultiConfig 的倍数必须全部大于 0")
        if any(weight < 0 for weight in self.win_weights):
            raise ValueError("WinWeightConfig 不能包含负权重")
        if sum(self.win_weights) <= 0:
            raise ValueError("WinWeightConfig 的权重总和必须大于 0")
        if any(weight < 0 for weight in self.bonus_win_weights):
            raise ValueError("BonusWinWeightConfig 不能包含负权重")
        if sum(weight > 0 for weight in self.bonus_win_weights) < self.BONUS_PICK_COUNT:
            raise ValueError(
                f"BonusWinWeightConfig 至少需要 {self.BONUS_PICK_COUNT} 个正权重"
            )
        bonus_recursion_indexes = [
            index
            for index, symbol_id in enumerate(self.reel_config)
            if symbol_id == self.BONUS_SYMBOL_ID and self.bonus_win_weights[index] > 0
        ]
        if bonus_recursion_indexes:
            raise ValueError(
                "BonusWinWeightConfig 中 symbol 0 位置的权重必须为 0: "
                f"{bonus_recursion_indexes}"
            )
        if any(prize < 0 for prize in self.item_prizes.values()):
            raise ValueError("ITEM_PRIZE 不能包含负数")
        if self.double_enabled and self.double_max_times <= 0:
            raise ValueError("启用翻倍玩法时 DoubleMaxTimes 必须大于 0")
        if self.double_multiple != 2:
            raise ValueError("DoubleMultiple 必须为 2")
        double_weight_configs = {
            "DoubleWeight": self.double_weights,
            **{
                f"DoubleWeight_{threshold}": weights
                for threshold, weights in self.double_weight_tiers.items()
            },
        }
        for key, weights in double_weight_configs.items():
            if len(weights) != self.double_max_times + 1:
                raise ValueError(f"{key} 长度必须为 DoubleMaxTimes + 1")
            if any(weight < 0 for weight in weights):
                raise ValueError(f"{key} 不能包含负权重")
            if sum(weights) <= 0:
                raise ValueError(f"{key} 的权重总和必须大于 0")

    def _resolve_config_path(self, path: str | Path) -> Path:
        path = Path(path)
        return path if path.is_absolute() else self.project_dir / path

    @staticmethod
    def _read_config(path: Path) -> ConfigParser:
        parser = ConfigParser(inline_comment_prefixes=("#", ";"))
        parser.optionxform = str
        if not parser.read(path, encoding="utf-8-sig"):
            raise FileNotFoundError(path)
        return parser

    @staticmethod
    def _parse_positive_int(value: str | None, key: str) -> int:
        if value is None:
            raise ValueError(f"缺少 {key}")
        result = int(value.strip())
        if result <= 0:
            raise ValueError(f"{key} 必须大于 0")
        return result

    @staticmethod
    def _parse_nonnegative_int(value: str | None, key: str) -> int:
        if value is None:
            raise ValueError(f"缺少 {key}")
        result = int(value.strip())
        if result < 0:
            raise ValueError(f"{key} 不能为负数")
        return result

    @staticmethod
    def _parse_enabled(value: str | None, key: str) -> bool:
        if value is None:
            raise ValueError(f"缺少 {key}")
        result = int(value.strip())
        if result not in (0, 1):
            raise ValueError(f"{key} 只能为 0 或 1")
        return bool(result)

    @staticmethod
    def _parse_int_list(value: str | None, key: str) -> list[int]:
        if value is None:
            raise ValueError(f"缺少 {key}")
        try:
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        except ValueError as exc:
            raise ValueError(f"{key} 必须是逗号分隔的整数") from exc
