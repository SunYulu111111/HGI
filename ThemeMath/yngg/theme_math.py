"""Si Botak Desa (yngg) math using the count-game project format."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from slots_math import CountGame


class ThemeMath(CountGame):
    """6x5 cluster-pay implementation of the Indonesian design specification."""

    DEFAULT_GAME_CONFIG_FILE = str(Path("special") / "game_config.conf")
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

    COIN_VALUES = (0.2, 0.5, 1, 2, 3, 4, 5, 10, 15, 20, 25, 50, 100, 250, 500)
    GREEN_CLOVER_MULTIPLIERS = (2, 3, 4, 5, 10, 20)
    GOLD_CLOVER_MULTIPLIERS = GREEN_CLOVER_MULTIPLIERS
    JACKPOT_MULTIPLIERS = {
        "mini": 10,
        "minor": 25,
        "major": 100,
        "grand": 5_000,
    }
    RETRIGGER_SPINS = {2: 2, 3: 4}
    FREE_MODE_NAMES = {"free", "super_free"}

    def __init__(self, base_bet: int = 100_000, **kwargs):
        kwargs.setdefault("project_dir", Path(__file__).resolve().parent)
        kwargs.setdefault("game_config_file", self.DEFAULT_GAME_CONFIG_FILE)
        super().__init__(base_bet=base_bet, **kwargs)
        self.last_ng_result: dict = {}
        self.last_fg_result: dict = {}

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
        feature_outcome: dict | None = None,
    ) -> dict:
        if free_game and free_mode not in self.FREE_MODE_NAMES:
            raise ValueError(f"unknown free mode: {free_mode}")
        reel_dir = self.FREE_REEL_CONFIG_DIR if free_game else None
        reel_template = "free_rand_ex_{index}.conf" if free_game else None
        board = self.spin(
            index=index,
            general_index=general_index,
            row=self.config.row_count,
            col=self.config.col_count,
            reel_config_dir=reel_dir,
            reel_file_template=reel_template,
        )
        if feature_outcome and feature_outcome.get("initial_board") is not None:
            board = self._validate_board(feature_outcome["initial_board"])
        spin_info = self.last_spin_info.copy()
        spin_info.update({"free_game": free_game, "free_mode": free_mode})
        return self.evaluate_cascades(
            board,
            spin_state=self.clone_spin_state(self.last_spin_state),
            spin_info=spin_info,
            return_detail=return_detail,
            max_cascades=max_cascades,
            free_game=free_game,
            free_mode=free_mode,
            golden_squares=golden_squares,
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

        injected = self.resolve_feature_outcome(feature_outcome, golden_squares=state)
        activated = injected["activated"]
        had_golden_squares = bool(state)
        if activated and (not free_game or free_mode == "free"):
            state.clear()
        scatter_count = injected["scatter_count"]
        if scatter_count is None:
            scatter_count = self.count_symbol(initial_board, self.FREE_SPIN_ID)
        super_scatter_count = injected["super_scatter_count"]
        if super_scatter_count is None:
            super_scatter_count = self.count_symbol(initial_board, self.SUPER_SCATTER_ID)
        bonus_count = injected["bonus_count"]
        if bonus_count is None:
            bonus_count = self.count_symbol(board, self.FEATURE_ID)
        triggered_mode = (
            self.get_triggered_free_spin_mode(scatter_count, super_scatter_count)
            if not free_game
            else None
        )
        retrigger_spins = self.get_retrigger_spins(scatter_count) if free_game else 0

        uncapped_total = cluster_win + injected["feature_win"]
        trigger_positions = sorted(
            (column, row)
            for column, values in enumerate(initial_board)
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
            "bonus_count": bonus_count,
            "is_trigger_feature": had_golden_squares and bonus_count > 0,
            "is_trigger_free": triggered_mode is not None,
            "free_times": triggered_mode["spins"] if triggered_mode else retrigger_spins,
            "free_mode": free_mode or (triggered_mode["name"] if triggered_mode else None),
            "retrigger_spins": retrigger_spins,
            "golden_squares": sorted(state),
            "next_free_golden_squares": trigger_positions if triggered_mode else [],
            "feature_win": injected["feature_win"],
            "feature_events": injected["events"] if return_detail else [],
            "feature_outcome_injected": feature_outcome is not None,
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
        for column, values in enumerate(board):
            survivors = [
                value
                for row, value in enumerate(values)
                if (column, row) not in remove_positions
            ]
            count = len(values) - len(survivors)
            top_before = spin_state["top_indexes"][column]
            new_items = self.take_symbols_above(spin_state, column, count)
            board[column] = new_items + survivors
            refill_items.append(
                {
                    "col": column,
                    "items": new_items,
                    "top_index_before": top_before,
                    "top_index_after": spin_state["top_indexes"][column],
                }
            )
        return board, {
            "remove_positions": sorted(remove_positions),
            "winning_item_ids": sorted(winning_ids),
            "refill_items": refill_items,
            "source_type": spin_state["source_type"],
        }

    # Backward-compatible name used by earlier yngg tests/tools.
    drop_super_cascade_symbols = drop_cluster_symbols

    def resolve_feature_outcome(
        self,
        outcome: dict | None,
        golden_squares: set[tuple[int, int]] | None = None,
    ) -> dict:
        """Validate an authoritative/injected server feature result."""

        if outcome is None:
            return {
                "feature_win": 0,
                "events": [],
                "activated": False,
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
        """Resolve deterministic golden-area reveals from authoritative rounds.

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

        if scatter_count >= 2 and super_scatter_count >= 1:
            return {"name": "super_free", "spins": 10}
        if scatter_count >= 3:
            return {"name": "free", "spins": 10}
        return None

    def get_retrigger_spins(self, scatter_count: int) -> int:
        return self.RETRIGGER_SPINS.get(scatter_count, 0)

    def jackpot_win(self, tier: str) -> int:
        """Evaluate a fixed jackpot tier; every board feature uses symbol ID 2."""

        multiplier = self.JACKPOT_MULTIPLIERS.get(tier, 0)
        return self.base_bet * multiplier
