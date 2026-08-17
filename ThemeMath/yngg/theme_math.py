"""Si Botak Desa (yngg) math using the count-game project format."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import random
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from slots_math import CountGame


class ThemeMath(CountGame):
    """6x5 cluster-pay implementation of the Indonesian design specification."""

    SPECIAL_CONFIG_DIR = "special"
    DEFAULT_GAME_CONFIG_FILE = str(Path(SPECIAL_CONFIG_DIR) / "yngg_game_config.conf")
    DEFAULT_GAME_SERVER_CONFIG_FILE = str(
        Path(SPECIAL_CONFIG_DIR) / "yngg_game_server.conf"
    )
    DEFAULT_BONUS_CONFIG_FILE = str(Path(SPECIAL_CONFIG_DIR) / "yngg_bonus.conf")
    FREE_REEL_CONFIG_DIR = "free_reel_config"
    FREE_SPIN_ID = 0
    WILD_ID = 1
    FEATURE_ID = 2
    BONUS_ID = FEATURE_ID
    COIN_ID = FEATURE_ID
    CLOVER_ID = FEATURE_ID
    POT_ID = FEATURE_ID
    MULTIPLIER_ID = FEATURE_ID
    COLLECTOR_ID = FEATURE_ID
    JACKPOT_ID = FEATURE_ID
    SUPER_SCATTER_ID = 13
    MIN_CLUSTER_SIZE = 5
    PAYING_SYMBOL_IDS = tuple(range(3, 13))

    ALLOWED_BONUS_TYPES = ("coin", "clover", "pot", "jackpot")
    JACKPOT_TIERS = ("mini", "minor", "major", "grand")
    MAX_GOLDEN_ROUNDS = 100
    PROBABILITY_DENOMINATOR = 10_000
    RETRIGGER_SPINS = {2: 2, 3: 4}
    FREE_MODE_NAMES = {"free", "super_free"}

    def __init__(self, base_bet: int = 100_000, **kwargs):
        kwargs.setdefault("project_dir", Path(__file__).resolve().parent)
        kwargs.setdefault("game_config_file", self.DEFAULT_GAME_CONFIG_FILE)
        self.game_server_config_file = kwargs.pop(
            "game_server_config_file",
            self.DEFAULT_GAME_SERVER_CONFIG_FILE,
        )
        self.bonus_config_file = kwargs.pop(
            "bonus_config_file",
            self.DEFAULT_BONUS_CONFIG_FILE,
        )
        super().__init__(base_bet=base_bet, **kwargs)
        game_server_config_path = self.project_dir / self.game_server_config_file
        self.game_server_config = self._read_config_file(game_server_config_path)
        self._load_super_scatter_config()
        bonus_config_path = self.project_dir / self.bonus_config_file
        self.bonus_config = self._read_config_file(bonus_config_path)
        self._load_bonus_config()
        self.last_ng_result: dict = {}
        self.last_fg_result: dict = {}

    def _load_super_scatter_config(self) -> None:
        if not self.game_server_config.has_section("Game Info"):
            raise ValueError(f"{self.game_server_config_file} missing [Game Info]")
        game_info = self.game_server_config["Game Info"]
        self.FREE_SPIN_ID = int(game_info.get("ScatterId", self.FREE_SPIN_ID))
        self.WILD_ID = int(game_info.get("WILD_ID", self.WILD_ID))
        self.FEATURE_ID = int(game_info.get("FEATURE_ID", self.FEATURE_ID))
        self.BONUS_ID = int(game_info.get("BONUS_ID", self.FEATURE_ID))
        self.COIN_ID = int(game_info.get("COIN_ID", self.FEATURE_ID))
        self.CLOVER_ID = int(game_info.get("CLOVER_ID", self.FEATURE_ID))
        self.POT_ID = int(game_info.get("POT_ID", self.FEATURE_ID))
        self.MULTIPLIER_ID = int(
            game_info.get("MULTIPLIER_ID", self.FEATURE_ID)
        )
        self.COLLECTOR_ID = int(
            game_info.get("COLLECTOR_ID", self.FEATURE_ID)
        )
        self.JACKPOT_ID = int(game_info.get("JACKPOT_ID", self.FEATURE_ID))
        self.SUPER_SCATTER_SOURCE_ID = int(
            game_info.get("SuperScatterSourceId", self.FREE_SPIN_ID)
        )
        self.SUPER_SCATTER_ID = int(
            game_info.get(
                "SUPER_SCATTER_ID",
                game_info.get("SuperScatterId", self.SUPER_SCATTER_ID),
            )
        )
        self.SUPER_SCATTER_PROBABILITY = int(
            game_info.get("SuperScatterProbability", "0")
        )
        probability_fields = (
            ("SCATTER_COUNT_WEIGHTS", "ScatterCountProbability", 4),
            (
                "BASE_NO_WIN_BONUS_COUNT_WEIGHTS",
                "BaseNoWinBonusCountProbability",
                2,
            ),
            (
                "BASE_WIN_BONUS_COUNT_WEIGHTS",
                "BaseWinBonusCountProbability",
                2,
            ),
            (
                "FREE_GOLDEN_BONUS_COUNT_WEIGHTS",
                "FreeGoldenBonusCountProbability",
                2,
            ),
            (
                "FREE_NO_GOLDEN_BONUS_COUNT_WEIGHTS",
                "FreeNoGoldenBonusCountProbability",
                2,
            ),
            (
                "DROP_SPECIAL_SYMBOL_WEIGHTS",
                "DropSpecialSymbolProbability",
                3,
            ),
        )
        for attribute, key, expected_length in probability_fields:
            weights = tuple(self._parse_int_list(game_info.get(key, "")))
            self._validate_weighted_options(
                key,
                tuple(range(expected_length)),
                weights,
            )
            setattr(self, attribute, weights)
        original_symbol_ids = (
            self.FREE_SPIN_ID,
            self.WILD_ID,
            self.FEATURE_ID,
            self.BONUS_ID,
            self.COIN_ID,
            self.CLOVER_ID,
            self.POT_ID,
            self.MULTIPLIER_ID,
            self.COLLECTOR_ID,
            self.JACKPOT_ID,
            self.SUPER_SCATTER_SOURCE_ID,
        )
        if any(
            not 0 <= symbol_id < self.config.item_count
            for symbol_id in original_symbol_ids
        ):
            raise ValueError("game server symbol ID outside original symbol range")
        self.wild_id = self.WILD_ID
        if not 0 <= self.SUPER_SCATTER_ID <= self.config.item_count:
            raise ValueError("SuperScatterId outside supported transformed range")
        if self.SUPER_SCATTER_SOURCE_ID == self.SUPER_SCATTER_ID:
            raise ValueError("SuperScatterSourceId and SuperScatterId must differ")
        if not 0 <= self.SUPER_SCATTER_PROBABILITY <= self.PROBABILITY_DENOMINATOR:
            raise ValueError("SuperScatterProbability must be between 0 and 10000")

    def _load_bonus_config(self) -> None:
        if not self.bonus_config.has_section("GENERAL"):
            raise ValueError(f"{self.bonus_config_file} missing [GENERAL]")
        general = self.bonus_config["GENERAL"]

        self.BONUS_SYMBOL_TYPES = tuple(
            value.strip().lower()
            for value in general.get("BONUS_SYMBOL_TYPE", "").split(",")
            if value.strip()
        )
        self.BONUS_SYMBOL_TYPE_WEIGHTS = tuple(
            self._parse_int_list(general.get("BONUS_SYMBOL_TYPE_PROBABILITY", ""))
        )
        self.COIN_VALUES = tuple(
            self._parse_float_list(general.get("BONUS_COIN_MULTIPLE", ""))
        )
        self.COIN_VALUE_WEIGHTS = tuple(
            self._parse_int_list(general.get("BONUS_COIN_MULTIPLE_PROBABILITY", ""))
        )
        self.GREEN_CLOVER_MULTIPLIERS = tuple(
            self._parse_int_list(general.get("BONUS_CLOVER_MULTIPLE", ""))
        )
        self.GOLD_CLOVER_MULTIPLIERS = self.GREEN_CLOVER_MULTIPLIERS
        self.CLOVER_MULTIPLIER_WEIGHTS = tuple(
            self._parse_int_list(general.get("BONUS_CLOVER_MULTIPLE_PROBABILITY", ""))
        )
        jackpot_multiples = tuple(
            self._parse_int_list(general.get("BONUS_JP_MULTIPLE", ""))
        )
        self.JACKPOT_TYPE_WEIGHTS = tuple(
            self._parse_int_list(general.get("BONUS_JP_TYPE_PROBABILITY", ""))
        )
        self.JACKPOT_MULTIPLIERS = dict(
            zip(self.JACKPOT_TIERS, jackpot_multiples)
        )

        if len(jackpot_multiples) != len(self.JACKPOT_TIERS):
            raise ValueError("BONUS_JP_MULTIPLE must configure four JP tiers")
        if (
            len(self.BONUS_SYMBOL_TYPES) != len(set(self.BONUS_SYMBOL_TYPES))
            or set(self.BONUS_SYMBOL_TYPES) != set(self.ALLOWED_BONUS_TYPES)
        ):
            raise ValueError(
                "BONUS_SYMBOL_TYPE must contain coin, clover, pot and jackpot once"
            )
        self._validate_weighted_options(
            "BONUS_SYMBOL_TYPE",
            self.BONUS_SYMBOL_TYPES,
            self.BONUS_SYMBOL_TYPE_WEIGHTS,
        )
        self._validate_weighted_options(
            "BONUS_COIN_MULTIPLE",
            self.COIN_VALUES,
            self.COIN_VALUE_WEIGHTS,
        )
        self._validate_weighted_options(
            "BONUS_CLOVER_MULTIPLE",
            self.GREEN_CLOVER_MULTIPLIERS,
            self.CLOVER_MULTIPLIER_WEIGHTS,
        )
        self._validate_weighted_options(
            "BONUS_JP_MULTIPLE",
            jackpot_multiples,
            self.JACKPOT_TYPE_WEIGHTS,
        )
        if any(value <= 0 for value in self.COIN_VALUES):
            raise ValueError("BONUS_COIN_MULTIPLE values must be positive")
        if any(value <= 0 for value in self.GREEN_CLOVER_MULTIPLIERS):
            raise ValueError("BONUS_CLOVER_MULTIPLE values must be positive")
        if any(value <= 0 for value in jackpot_multiples):
            raise ValueError("BONUS_JP_MULTIPLE values must be positive")

    def convert_super_scatter_symbol(self, symbol_id: int) -> int:
        """Convert source Scatter ID 0 to display Super Scatter ID by probability."""

        if symbol_id != self.SUPER_SCATTER_SOURCE_ID:
            return symbol_id
        if random.randrange(self.PROBABILITY_DENOMINATOR) < self.SUPER_SCATTER_PROBABILITY:
            return self.SUPER_SCATTER_ID
        return symbol_id

    def apply_super_scatter_conversion(
        self,
        item_list,
    ) -> tuple[list[list[int]], list[tuple[int, int]]]:
        """Apply the configured conversion independently to each Scatter."""

        board = self._clone_board(item_list)
        converted_positions = []
        for column, values in enumerate(board):
            for row, symbol_id in enumerate(values):
                converted = self.convert_super_scatter_symbol(symbol_id)
                board[column][row] = converted
                if converted != symbol_id:
                    converted_positions.append((column, row))
        return board, converted_positions

    def get_nonwinning_symbol_positions(
        self,
        item_list,
        free_game: bool = False,
        candidate_positions: set[tuple[int, int]] | None = None,
    ) -> list[tuple[int, int]]:
        """Return replaceable base-symbol positions outside current wins."""

        board = self._clone_board(item_list)
        win_result = self.cal_item_list(
            board,
            return_detail=True,
            free_game=free_game,
            row=self.config.row_count,
            col=self.config.col_count,
        )
        winning_positions = set(win_result["win_positions"])
        allowed_positions = candidate_positions
        return [
            (column, row)
            for column, values in enumerate(board)
            for row, symbol_id in enumerate(values)
            if (allowed_positions is None or (column, row) in allowed_positions)
            and (column, row) not in winning_positions
            and (
                symbol_id == self.WILD_ID
                or symbol_id in self.PAYING_SYMBOL_IDS
            )
        ]

    def place_special_symbols(
        self,
        item_list,
        special_symbol_ids: list[int],
        free_game: bool = False,
        candidate_positions: set[tuple[int, int]] | None = None,
    ) -> tuple[list[list[int]], list[dict]]:
        """Randomly replace distinct nonwinning positions with special symbols."""

        board = self._clone_board(item_list)
        candidates = self.get_nonwinning_symbol_positions(
            board,
            free_game=free_game,
            candidate_positions=candidate_positions,
        )
        placements = []
        for symbol_id in special_symbol_ids:
            if not candidates:
                break
            candidate_index = random.randrange(len(candidates))
            column, row = candidates.pop(candidate_index)
            board[column][row] = symbol_id
            placements.append(
                {
                    "position": (column, row),
                    "symbol_id": symbol_id,
                }
            )
        return board, placements

    def choose_initial_special_symbol_ids(
        self,
        item_list,
        free_game: bool,
        golden_squares: set[tuple[int, int]] | None = None,
        remaining_spins: int | None = None,
        bonus_seen: bool = False,
    ) -> list[int]:
        """Choose initial Scatter and Bonus counts from server-configured weights."""

        scatter_count = self.weighted_random_index(self.SCATTER_COUNT_WEIGHTS)
        special_symbol_ids = [self.FREE_SPIN_ID] * scatter_count
        bonus_count = 0

        if free_game:
            bonus_weights = (
                self.FREE_GOLDEN_BONUS_COUNT_WEIGHTS
                if golden_squares
                else self.FREE_NO_GOLDEN_BONUS_COUNT_WEIGHTS
            )
            bonus_count = self.weighted_random_index(bonus_weights)
            if remaining_spins == 1 and not bonus_seen:
                bonus_count = max(bonus_count, 1)
        elif scatter_count == 0:
            win_result = self.cal_item_list(
                item_list,
                return_detail=True,
                free_game=False,
                row=self.config.row_count,
                col=self.config.col_count,
            )
            bonus_weights = (
                self.BASE_WIN_BONUS_COUNT_WEIGHTS
                if win_result["total_win"] > 0
                else self.BASE_NO_WIN_BONUS_COUNT_WEIGHTS
            )
            bonus_count = self.weighted_random_index(bonus_weights)

        special_symbol_ids.extend([self.FEATURE_ID] * bonus_count)
        return special_symbol_ids

    def choose_drop_special_symbol_id(self) -> int | None:
        """Choose no replacement, Scatter or Bonus for one dropped symbol."""

        special_type = self.weighted_random_index(
            self.DROP_SPECIAL_SYMBOL_WEIGHTS
        )
        if special_type == 1:
            return self.FREE_SPIN_ID
        if special_type == 2:
            return self.FEATURE_ID
        return None

    def ng_spin(
        self,
        index: int = 0,
        general_index: int = 1,
        return_detail: bool = False,
        max_cascades: int = 100,
        feature_outcome: dict | None = None,
    ) -> dict:
        """Spin the published base reel set and execute super cascades."""

        result = self._spin_and_evaluate(
            index=index,
            general_index=general_index,
            free_game=False,
            return_detail=return_detail,
            max_cascades=max_cascades,
            feature_outcome=feature_outcome,
        )
        self.last_ng_result = result
        return result

    def fg_spin(
        self,
        index: int = 0,
        general_index: int = 1,
        return_detail: bool = False,
        max_cascades: int = 100,
        free_mode: str = "free",
        golden_squares: set[tuple[int, int]] | None = None,
        remaining_spins: int | None = None,
        bonus_seen: bool = False,
        feature_outcome: dict | None = None,
    ) -> dict:
        """Spin free reels with explicit free-mode persistent state."""

        result = self._spin_and_evaluate(
            index=index,
            general_index=general_index,
            free_game=True,
            return_detail=return_detail,
            max_cascades=max_cascades,
            free_mode=free_mode,
            golden_squares=golden_squares,
            remaining_spins=remaining_spins,
            bonus_seen=bonus_seen,
            feature_outcome=feature_outcome,
        )
        self.last_fg_result = result
        return result

    def _spin_and_evaluate(
        self,
        index: int,
        general_index: int,
        free_game: bool,
        return_detail: bool,
        max_cascades: int,
        free_mode: str | None = None,
        golden_squares: set[tuple[int, int]] | None = None,
        remaining_spins: int | None = None,
        bonus_seen: bool = False,
        feature_outcome: dict | None = None,
    ) -> dict:
        if free_game and free_mode not in self.FREE_MODE_NAMES:
            raise ValueError(f"unknown free mode: {free_mode}")
        if remaining_spins is not None and remaining_spins <= 0:
            raise ValueError("remaining_spins must be positive")
        reel_dir = self.FREE_REEL_CONFIG_DIR if free_game else None
        reel_template = "yngg_free_rand_ex_{index}.conf" if free_game else None
        board = self.spin(
            index=index,
            general_index=general_index,
            row=self.config.row_count,
            col=self.config.col_count,
            reel_config_dir=reel_dir,
            reel_file_template=reel_template,
        )
        initial_board_injected = bool(
            feature_outcome
            and feature_outcome.get("initial_board") is not None
        )
        if initial_board_injected:
            board = self._validate_board(feature_outcome["initial_board"])
        initial_special_placements = []
        if (
            not initial_board_injected
            and self.last_spin_info.get("spin_type") in ("normal", "special")
        ):
            special_symbol_ids = self.choose_initial_special_symbol_ids(
                board,
                free_game=free_game,
                golden_squares=golden_squares,
                remaining_spins=remaining_spins,
                bonus_seen=bonus_seen,
            )
            board, initial_special_placements = self.place_special_symbols(
                board,
                special_symbol_ids,
                free_game=free_game,
            )
        board, converted_positions = self.apply_super_scatter_conversion(board)
        spin_info = self.last_spin_info.copy()
        spin_info.update(
            {
                "free_game": free_game,
                "free_mode": free_mode,
                "super_scatter_source_id": self.SUPER_SCATTER_SOURCE_ID,
                "super_scatter_probability": self.SUPER_SCATTER_PROBABILITY,
                "super_scatter_positions": converted_positions,
                "initial_special_placements": initial_special_placements,
            }
        )
        return self.evaluate_cascades(
            board,
            spin_state=self.clone_spin_state(self.last_spin_state),
            spin_info=spin_info,
            return_detail=return_detail,
            max_cascades=max_cascades,
            free_game=free_game,
            free_mode=free_mode,
            golden_squares=golden_squares,
            remaining_spins=remaining_spins,
            bonus_seen=bonus_seen,
            feature_outcome=feature_outcome,
        )

    def evaluate(self, item_list, return_detail: bool = True, free_game: bool = False) -> dict:
        """Evaluate one board without removing or refilling symbols."""

        result = self.cal_item_list(
            item_list,
            return_detail=True,
            free_game=free_game,
            row=self.config.row_count,
            col=self.config.col_count,
        )
        detail = {
            "item_list": [list(column) for column in item_list],
            "total_win": result["total_win"],
            "win_items": result["items"],
            "win_positions": result["win_positions"],
            "free_spin_count": self.count_symbol(item_list, self.FREE_SPIN_ID),
            "super_scatter_count": self.count_symbol(item_list, self.SUPER_SCATTER_ID),
            "total_scatter_count": (
                self.count_symbol(item_list, self.FREE_SPIN_ID)
                + self.count_symbol(item_list, self.SUPER_SCATTER_ID)
            ),
            "bonus_count": self.count_symbol(item_list, self.FEATURE_ID),
            "spin_info": self.last_spin_info,
        }
        if not return_detail:
            detail["win_items"] = []
            detail["win_positions"] = []
        return detail

    def cal_item_list(
        self,
        item_list,
        return_detail: bool = False,
        free_game: bool = False,
        row: int | None = None,
        col: int | None = None,
    ):
        """Pay each orthogonally connected cluster of 5+ matching symbols.

        Wilds join a cluster but cannot form a paying cluster on their own.
        The method keeps CountGame's result schema so existing simulations can
        consume yngg in the same way as model_countgame.
        """

        board, col_count, row_count = self._normalize_item_list(item_list, row=row, col=col)
        disabled = self._get_grid_disables(free_game, col_count, row_count)
        total_win = 0
        win_items: list[dict] = []

        for item_id in self.PAYING_SYMBOL_IDS:
            eligible = {
                (column, line)
                for column in range(col_count)
                for line in range(min(row_count, len(board[column])))
                if not self._is_disabled(disabled, column, line, row_count)
                and board[column][line] in (item_id, self.WILD_ID)
            }
            for positions in self._connected_components(eligible):
                symbol_count = sum(board[column][line] == item_id for column, line in positions)
                if len(positions) < self.MIN_CLUSTER_SIZE or symbol_count == 0:
                    continue
                prize = self._get_or_default(
                    self.config.item_prizes[item_id],
                    min(len(positions), 30) - 1,
                    0,
                )
                if prize <= 0:
                    continue
                win = self.base_bet * prize // self.BET_UNIT // max(self.config.prize_rate, 1)
                sorted_positions = sorted(positions)
                total_win += win
                win_items.append(
                    {
                        "item_id": item_id,
                        "count": len(positions),
                        "hit_num": len(positions),
                        "symbol_count": symbol_count,
                        "wild_count": len(positions) - symbol_count,
                        "positions": sorted_positions,
                        "prize": prize,
                        "win": win,
                    }
                )

        win_positions = sorted({position for item in win_items for position in item["positions"]})
        self.last_win_items = win_items
        self.last_win_positions = win_positions
        if return_detail:
            return {"total_win": total_win, "items": win_items, "win_positions": win_positions}
        return total_win

    def evaluate_cascades(
        self,
        item_list,
        spin_state: dict,
        spin_info: dict | None = None,
        return_detail: bool = False,
        max_cascades: int = 100,
        free_game: bool = False,
        free_mode: str | None = None,
        golden_squares: set[tuple[int, int]] | None = None,
        remaining_spins: int | None = None,
        bonus_seen: bool = False,
        feature_outcome: dict | None = None,
    ) -> dict:
        """Run cluster removal/refill until no winning cluster remains."""

        if max_cascades <= 0:
            raise ValueError("max_cascades must be positive")
        board = self._validate_board(item_list)
        initial_board = self._clone_board(board)
        state = set(golden_squares or ())
        rounds: list[dict] = []
        all_win_items: list[dict] = []
        cluster_win = 0

        for cascade_index in range(1, max_cascades + 1):
            round_result = self.cal_item_list(
                board,
                return_detail=True,
                free_game=free_game,
                row=self.config.row_count,
                col=self.config.col_count,
            )
            if round_result["total_win"] <= 0 or not round_result["win_positions"]:
                break
            state.update(round_result["win_positions"])
            next_board, drop_info = self.drop_cluster_symbols(
                board,
                round_result["items"],
                spin_state,
                free_game=free_game,
            )
            cluster_win += round_result["total_win"]
            all_win_items.extend(round_result["items"])
            rounds.append(
                {
                    "cascade_index": cascade_index,
                    "item_list": self._clone_board(board),
                    "total_win": round_result["total_win"],
                    "win_items": round_result["items"],
                    "win_positions": round_result["win_positions"],
                    "drop_info": drop_info,
                    "next_item_list": self._clone_board(next_board),
                }
            )
            board = next_board
        else:
            raise RuntimeError(f"cascade exceeded max_cascades={max_cascades}")

        forced_free_bonus_placements = []
        if (
            free_game
            and remaining_spins == 1
            and not bonus_seen
            and self.count_symbol(board, self.FEATURE_ID) == 0
        ):
            board, forced_free_bonus_placements = self.place_special_symbols(
                board,
                [self.FEATURE_ID],
                free_game=True,
            )
            if not forced_free_bonus_placements:
                raise RuntimeError(
                    "unable to place guaranteed Free Bonus on a nonwinning position"
                )

        feature_outcome_injected = feature_outcome is not None
        injected = self.resolve_feature_outcome(feature_outcome, golden_squares=state)
        had_golden_squares = bool(state)
        scatter_count = injected["scatter_count"]
        if scatter_count is None:
            scatter_count = self.count_symbol(board, self.FREE_SPIN_ID)
        super_scatter_count = injected["super_scatter_count"]
        if super_scatter_count is None:
            super_scatter_count = self.count_symbol(board, self.SUPER_SCATTER_ID)
        bonus_count = injected["bonus_count"]
        if bonus_count is None or forced_free_bonus_placements:
            bonus_count = self.count_symbol(board, self.FEATURE_ID)
        is_trigger_feature = had_golden_squares and bonus_count > 0
        feature_outcome_generated = False
        has_injected_feature_result = bool(
            feature_outcome
            and any(
                key in feature_outcome
                for key in (
                    "activated",
                    "events",
                    "feature_win",
                    "feature_win_multiple",
                    "golden_rounds",
                )
            )
        )
        if is_trigger_feature and not has_injected_feature_result:
            injected = self.resolve_feature_outcome(
                {
                    "activated": True,
                    "golden_rounds": self.generate_golden_rounds(state),
                },
                golden_squares=state,
            )
            feature_outcome_generated = True

        activated = injected["activated"]
        if activated and (not free_game or free_mode == "free"):
            state.clear()
        total_scatter_count = scatter_count + super_scatter_count
        triggered_mode = (
            self.get_triggered_free_spin_mode(scatter_count, super_scatter_count)
            if not free_game
            else None
        )
        retrigger_spins = (
            self.get_retrigger_spins(total_scatter_count)
            if free_game
            else 0
        )

        uncapped_total = cluster_win + injected["feature_win"]
        trigger_positions = sorted(
            (column, row)
            for column, values in enumerate(board)
            for row, value in enumerate(values)
            if value in (self.FREE_SPIN_ID, self.SUPER_SCATTER_ID)
        )
        result = {
            "item_list": initial_board,
            "final_item_list": board,
            "total_win": uncapped_total,
            "uncapped_total_win": uncapped_total,
            "cascade_count": len(rounds),
            "rounds": rounds if return_detail else [],
            "win_items": all_win_items if return_detail else [],
            "scatter_count": scatter_count,
            "super_scatter_count": super_scatter_count,
            "total_scatter_count": total_scatter_count,
            "bonus_count": bonus_count,
            "free_bonus_seen": bonus_seen or bonus_count > 0,
            "forced_free_bonus_placements": forced_free_bonus_placements,
            "is_trigger_feature": is_trigger_feature,
            "is_trigger_free": triggered_mode is not None,
            "free_times": triggered_mode["spins"] if triggered_mode else retrigger_spins,
            "free_mode": free_mode or (triggered_mode["name"] if triggered_mode else None),
            "retrigger_spins": retrigger_spins,
            "golden_squares": sorted(state),
            "next_free_golden_squares": trigger_positions if triggered_mode else [],
            "feature_win": injected["feature_win"],
            "feature_events": injected["events"] if return_detail else [],
            "golden_rounds": injected["golden_rounds"],
            "feature_cells": (
                injected["golden_result"]["cells"]
                if injected["golden_result"]
                else []
            ),
            "feature_outcome_injected": feature_outcome_injected,
            "feature_outcome_generated": feature_outcome_generated,
            "spin_info": spin_info or self.last_spin_info,
            "final_top_indexes": spin_state.get("top_indexes", [])[:],
        }
        self.last_spin_info = result["spin_info"]
        self.last_spin_state = spin_state
        return result

    def drop_cluster_symbols(
        self,
        item_list,
        win_items: list[dict],
        spin_state: dict,
        free_game: bool = False,
    ) -> tuple[list[list[int]], dict]:
        """Remove only winning cluster positions, then refill from above."""

        board = self._clone_board(item_list)
        winning_ids = {item["item_id"] for item in win_items}
        remove_positions = {
            tuple(position)
            for item in win_items
            for position in item["positions"]
        }
        refill_items = []
        dropped_positions: set[tuple[int, int]] = set()
        requested_special_ids = []
        for column, values in enumerate(board):
            survivors = [
                value
                for row, value in enumerate(values)
                if (column, row) not in remove_positions
            ]
            count = len(values) - len(survivors)
            top_before = spin_state["top_indexes"][column]
            new_items = self.take_symbols_above(spin_state, column, count)
            for _ in new_items:
                special_symbol_id = self.choose_drop_special_symbol_id()
                if special_symbol_id is not None:
                    requested_special_ids.append(special_symbol_id)
            board[column] = new_items + survivors
            dropped_positions.update(
                (column, row)
                for row in range(count)
            )
            refill_items.append(
                {
                    "col": column,
                    "items": new_items,
                    "top_index_before": top_before,
                    "top_index_after": spin_state["top_indexes"][column],
                }
            )
        board, special_placements = self.place_special_symbols(
            board,
            requested_special_ids,
            free_game=free_game,
            candidate_positions=dropped_positions,
        )
        converted_positions = []
        for column, row in dropped_positions:
            symbol_id = board[column][row]
            converted = self.convert_super_scatter_symbol(symbol_id)
            board[column][row] = converted
            if converted != symbol_id:
                converted_positions.append((column, row))
        return board, {
            "remove_positions": sorted(remove_positions),
            "winning_item_ids": sorted(winning_ids),
            "refill_items": refill_items,
            "special_placements": special_placements,
            "super_scatter_positions": sorted(converted_positions),
            "source_type": spin_state["source_type"],
        }

    # Backward-compatible name used by earlier yngg tests/tools.
    drop_super_cascade_symbols = drop_cluster_symbols

    def generate_golden_round(
        self,
        positions: set[tuple[int, int]],
    ) -> list[dict]:
        """Generate one reveal round by choosing type before type-specific value."""

        reveals = []
        for position in sorted(positions, key=lambda value: (value[1], value[0])):
            kind = self.BONUS_SYMBOL_TYPES[
                self.weighted_random_index(self.BONUS_SYMBOL_TYPE_WEIGHTS)
            ]
            reveal = {"position": list(position), "type": kind}
            if kind == "coin":
                value = self.COIN_VALUES[
                    self.weighted_random_index(self.COIN_VALUE_WEIGHTS)
                ]
                reveal["value"] = int(value) if value.is_integer() else value
            elif kind == "clover":
                reveal["multiplier"] = self.GREEN_CLOVER_MULTIPLIERS[
                    self.weighted_random_index(self.CLOVER_MULTIPLIER_WEIGHTS)
                ]
            elif kind == "jackpot":
                reveal["tier"] = self.JACKPOT_TIERS[
                    self.weighted_random_index(self.JACKPOT_TYPE_WEIGHTS)
                ]
            reveals.append(reveal)
        return reveals

    def generate_golden_rounds(
        self,
        golden_squares: set[tuple[int, int]],
    ) -> list[list[dict]]:
        """Generate initial reveals and pot-triggered rerolls."""

        all_positions = set(golden_squares)
        if not all_positions:
            return []
        persistent_pots: set[tuple[int, int]] = set()
        positions_to_reveal = all_positions
        rounds = []

        for _ in range(self.MAX_GOLDEN_ROUNDS):
            reveals = self.generate_golden_round(positions_to_reveal)
            rounds.append(reveals)
            new_pots = {
                tuple(reveal["position"])
                for reveal in reveals
                if reveal["type"] == "pot"
            }
            if not new_pots:
                return rounds
            persistent_pots.update(new_pots)
            positions_to_reveal = all_positions - persistent_pots
            if not positions_to_reveal:
                return rounds
        raise RuntimeError(
            f"golden feature exceeded max rounds={self.MAX_GOLDEN_ROUNDS}"
        )

    def resolve_feature_outcome(
        self,
        outcome: dict | None,
        golden_squares: set[tuple[int, int]] | None = None,
    ) -> dict:
        """Validate and settle an injected or locally generated feature result."""

        if outcome is None:
            return {
                "feature_win": 0,
                "events": [],
                "activated": False,
                "golden_rounds": [],
                "golden_result": None,
                "scatter_count": None,
                "super_scatter_count": None,
                "bonus_count": None,
            }
        feature_win = int(outcome.get("feature_win", 0))
        if "feature_win_multiple" in outcome:
            feature_win += round(float(outcome["feature_win_multiple"]) * self.base_bet)
        golden_result = None
        if "golden_rounds" in outcome:
            golden_result = self.resolve_golden_feature(
                outcome["golden_rounds"],
                golden_squares=golden_squares,
            )
            feature_win += golden_result["total_win"]
        if feature_win < 0:
            raise ValueError("feature win cannot be negative")
        events = outcome.get("events", [])
        if not isinstance(events, list):
            raise ValueError("feature events must be a list")
        if golden_result:
            events = list(events) + golden_result["events"]
        return {
            "feature_win": feature_win,
            "events": [dict(event) for event in events],
            "activated": bool(outcome.get("activated", golden_result is not None)),
            "golden_rounds": [
                [dict(reveal) for reveal in reveals]
                for reveals in outcome.get("golden_rounds", [])
            ],
            "golden_result": golden_result,
            "scatter_count": self._optional_nonnegative_int(outcome.get("scatter_count")),
            "super_scatter_count": self._optional_nonnegative_int(
                outcome.get("super_scatter_count")
            ),
            "bonus_count": self._optional_nonnegative_int(outcome.get("bonus_count")),
        }

    def resolve_golden_feature(
        self,
        rounds,
        golden_squares: set[tuple[int, int]] | None = None,
    ) -> dict:
        """Resolve deterministic golden-area reveals.

        Each round is a list of changed cells. A cell has ``position`` and
        ``type`` (coin, clover, pot, jackpot). Rounds after a pot must contain
        every regenerated non-pot cell. Clover effects run before pots; pots
        run top-to-bottom then left-to-right.
        """

        if not isinstance(rounds, list):
            raise ValueError("golden_rounds must be a list")
        allowed_positions = set(golden_squares or ())
        cells: dict[tuple[int, int], dict] = {}
        jackpot_multiple = 0.0
        event_log: list[dict] = []

        for round_index, reveals in enumerate(rounds, 1):
            if not isinstance(reveals, list):
                raise ValueError("each golden round must be a list")
            revealed_positions = set()
            for reveal in reveals:
                cell = dict(reveal)
                position = self._parse_position(cell.get("position"))
                if allowed_positions and position not in allowed_positions:
                    raise ValueError(f"golden reveal outside golden squares: {position}")
                kind = str(cell.get("type", "")).lower()
                if kind == "coin":
                    value = float(cell["value"])
                    if value not in self.COIN_VALUES:
                        raise ValueError(f"unsupported coin multiple: {value}")
                    cells[position] = {"type": "coin", "value": value}
                elif kind == "clover":
                    multiplier = int(cell["multiplier"])
                    if multiplier not in self.GREEN_CLOVER_MULTIPLIERS:
                        raise ValueError(f"unsupported clover multiplier: {multiplier}")
                    cells[position] = {"type": "clover", "multiplier": multiplier}
                elif kind == "pot":
                    cells[position] = {"type": "pot", "value": float(cell.get("value", 0))}
                elif kind == "jackpot":
                    tier = str(cell["tier"]).lower()
                    if tier not in self.JACKPOT_MULTIPLIERS:
                        raise ValueError(f"unsupported jackpot tier: {tier}")
                    cells[position] = {"type": "jackpot", "tier": tier}
                    jackpot_multiple += self.JACKPOT_MULTIPLIERS[tier]
                else:
                    raise ValueError(f"unsupported golden symbol type: {kind}")
                revealed_positions.add(position)

            clovers = sorted(
                (
                    (position, cell)
                    for position, cell in cells.items()
                    if position in revealed_positions and cell["type"] == "clover"
                ),
                key=lambda item: (item[0][1], item[0][0]),
            )
            for position, clover in clovers:
                column, row = position
                affected = []
                for target, target_cell in cells.items():
                    if (
                        target_cell["type"] in ("coin", "pot")
                        and abs(target[0] - column) <= 1
                        and abs(target[1] - row) <= 1
                    ):
                        target_cell["value"] *= clover["multiplier"]
                        affected.append(target)
                event_log.append(
                    {
                        "type": "Clover",
                        "round": round_index,
                        "position": position,
                        "multiplier": clover["multiplier"],
                        "affected": sorted(affected),
                    }
                )

            pots = sorted(
                (
                    (position, cell)
                    for position, cell in cells.items()
                    if position in revealed_positions and cell["type"] == "pot"
                ),
                key=lambda item: (item[0][1], item[0][0]),
            )
            for position, pot in pots:
                collected = sum(
                    cell.get("value", 0)
                    for target, cell in cells.items()
                    if target != position and cell["type"] in ("coin", "pot")
                )
                pot["value"] = collected
                event_log.append(
                    {
                        "type": "Collect",
                        "round": round_index,
                        "position": position,
                        "value": collected,
                    }
                )

        area_multiple = sum(
            cell.get("value", 0)
            for cell in cells.values()
            if cell["type"] in ("coin", "pot")
        )
        total_multiple = area_multiple + jackpot_multiple
        return {
            "total_multiple": total_multiple,
            "total_win": round(total_multiple * self.base_bet),
            "area_multiple": area_multiple,
            "jackpot_multiple": jackpot_multiple,
            "cells": [
                {"position": position, **cell}
                for position, cell in sorted(
                    cells.items(),
                    key=lambda item: (item[0][1], item[0][0]),
                )
            ],
            "events": event_log,
        }

    def _validate_board(self, item_list) -> list[list[int]]:
        board = [list(column) for column in item_list]
        if len(board) != self.config.col_count:
            raise ValueError(f"board must have {self.config.col_count} columns")
        if any(len(column) != self.config.row_count for column in board):
            raise ValueError(f"each board column must have {self.config.row_count} rows")
        return board

    def _parse_position(self, value) -> tuple[int, int]:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("position must be [column, row]")
        position = (int(value[0]), int(value[1]))
        if not (
            0 <= position[0] < self.config.col_count
            and 0 <= position[1] < self.config.row_count
        ):
            raise ValueError(f"position outside board: {position}")
        return position

    @staticmethod
    def _clone_board(item_list) -> list[list[int]]:
        return [list(column) for column in item_list]

    @staticmethod
    def _parse_float_list(value: str) -> list[float]:
        return [
            float(item.strip())
            for item in value.split(",")
            if item.strip()
        ]

    @staticmethod
    def _validate_weighted_options(name: str, options, weights) -> None:
        if not options:
            raise ValueError(f"{name} cannot be empty")
        if len(options) != len(weights):
            raise ValueError(f"{name} values and weights must have the same length")
        if any(int(weight) < 0 for weight in weights):
            raise ValueError(f"{name} weights cannot be negative")
        if sum(int(weight) for weight in weights) <= 0:
            raise ValueError(f"{name} weights total must be positive")

    @staticmethod
    def weighted_random_index(weights) -> int:
        total_weight = sum(max(int(weight), 0) for weight in weights)
        if total_weight <= 0:
            raise ValueError("weights total must be positive")
        hit = random.randrange(total_weight)
        current_weight = 0
        for index, weight in enumerate(weights):
            current_weight += max(int(weight), 0)
            if hit < current_weight:
                return index
        return len(weights) - 1

    @staticmethod
    def _optional_nonnegative_int(value) -> int | None:
        if value is None:
            return None
        result = int(value)
        if result < 0:
            raise ValueError("feature counts cannot be negative")
        return result

    @staticmethod
    def _connected_components(positions: set[tuple[int, int]]):
        remaining = set(positions)
        while remaining:
            start = remaining.pop()
            component = {start}
            queue = deque([start])
            while queue:
                column, row = queue.popleft()
                for neighbor in (
                    (column - 1, row),
                    (column + 1, row),
                    (column, row - 1),
                    (column, row + 1),
                ):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.add(neighbor)
                        queue.append(neighbor)
            yield component

    @staticmethod
    def count_symbol(item_list, symbol_id: int) -> int:
        return sum(value == symbol_id for column in item_list for value in column)

    def get_triggered_free_spin_mode(
        self,
        scatter_count: int,
        super_scatter_count: int = 0,
    ) -> dict | None:
        """Select normal or super free spins from the design trigger."""

        total_scatter_count = scatter_count + super_scatter_count
        if total_scatter_count >= 3 and super_scatter_count >= 1:
            return {"name": "super_free", "spins": 10}
        if total_scatter_count >= 3:
            return {"name": "free", "spins": 10}
        return None

    def get_retrigger_spins(self, scatter_count: int) -> int:
        return self.RETRIGGER_SPINS.get(scatter_count, 0)

    def jackpot_win(self, tier: str) -> int:
        """Evaluate a fixed jackpot tier; every board feature uses symbol ID 2."""

        multiplier = self.JACKPOT_MULTIPLIERS.get(tier, 0)
        return self.base_bet * multiplier
