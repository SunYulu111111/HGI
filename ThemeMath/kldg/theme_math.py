"""恐龙帝国数学入口：六列变高 Ways、边框升级、连消和免费旋转。"""

from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from itertools import product
from pathlib import Path
import random
import sys


RootDir = Path(__file__).resolve().parent.parent
if str(RootDir) not in sys.path:
    sys.path.insert(0, str(RootDir))

from slots_math import WaysGame


@dataclass(frozen=True)
class Cell:
    SymbolId: int
    FrameStage: int = 0  # 0=无框，1=银框，2=金框


class ThemeMath(WaysGame):
    """沿用 Ways 模板的配置和转轴入口，执行 kldg 专属结算。"""

    DefaultGameConfigFile = "special/kldg_game_config.conf"
    DefaultGameServerConfigFile = "special/kldg_game_server.conf"
    FreeReelConfigDir = "free_reel_config"
    ScatterId = 0
    WildId = 1
    OrdinaryIds = tuple(range(2, 13))
    FrameColumns = (1, 2, 3, 4)
    FrameRows = (1, 2, 3)
    ChanceBase = 10000
    MinimumReelHeight = 2
    MainMultiplierCap = 5
    FreeTriggerScatterCount = 4
    BaseFreeSpins = 8
    ExtraFreeSpinsPerScatter = 2

    def __init__(self, base_bet: int = 10000, **kwargs):
        project_dir = Path(kwargs.pop("project_dir", Path(__file__).resolve().parent))
        game_config_file = kwargs.pop("game_config_file", self.DefaultGameConfigFile)
        game_server_config_file = kwargs.pop("game_server_config_file", self.DefaultGameServerConfigFile)
        if base_bet <= 0:
            raise ValueError("base_bet must be positive")
        super().__init__(
            base_bet=base_bet,
            project_dir=project_dir,
            game_config_file=game_config_file,
            reel_file_template="kldg_rand_ex_{index}.conf",
            **kwargs,
        )
        if self.config.col_count != 6 or self.config.row_count != 6 or self.config.item_count != 13:
            raise ValueError("kldg requires 6 columns, maximum height 6, and 13 symbols")
        server_path = self.project_dir / game_server_config_file
        server = ConfigParser(inline_comment_prefixes=("#", ";"))
        if not server.read(server_path, encoding="utf-8-sig") or not server.has_section("Game Info"):
            raise ValueError(f"missing [Game Info]: {server_path}")
        info = server["Game Info"]
        self.ReelHeightWeights = self._parse_height_weights(info["ReelHeightWeights"])
        self.SilverFrameChance = int(info["SilverFrameChance"])
        if not 0 <= self.SilverFrameChance <= self.ChanceBase:
            raise ValueError("SilverFrameChance must be in 0..10000")
        self.SilverUpgradeSymbolWeights = self._parse_weights(
            info["SilverUpgradeSymbolWeights"], len(self.OrdinaryIds)
        )
        self.LastNgResult: dict = {}
        self.LastFgResult: dict = {}

    @staticmethod
    def _parse_weights(value: str, count: int) -> list[int]:
        weights = [int(part.strip()) for part in value.split(",")]
        if len(weights) != count or any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ValueError(f"expected {count} nonnegative weights with a positive total")
        return weights

    @classmethod
    def _parse_height_weights(cls, value: str) -> list[list[int]]:
        groups = [cls._parse_weights(part, 5) for part in value.split("|")]
        if len(groups) != 6:
            raise ValueError("ReelHeightWeights must contain six groups")
        return groups

    @staticmethod
    def _weighted_index(weights: list[int]) -> int:
        hit = random.randrange(sum(weights))
        for index, weight in enumerate(weights):
            if hit < weight:
                return index
            hit -= weight
        raise AssertionError("positive weights must select an index")

    def _initial_cell(self, symbol_id: int, col: int, row: int) -> Cell:
        if (
            col in self.FrameColumns
            and row in self.FrameRows
            and symbol_id in self.OrdinaryIds
            and random.randrange(self.ChanceBase) < self.SilverFrameChance
        ):
            return Cell(symbol_id, 1)
        return Cell(symbol_id)

    def ng_spin(
        self,
        index: int = 0,
        general_index: int = 1,
        return_detail: bool = False,
        max_cascades: int = 100,
    ) -> dict:
        result = self._spin_and_evaluate(index, general_index, False, 0, return_detail, max_cascades)
        self.LastNgResult = result
        return result

    def fg_spin(
        self,
        index: int = 0,
        general_index: int = 1,
        FreeSpinNumber: int = 1,
        return_detail: bool = False,
        max_cascades: int = 100,
    ) -> dict:
        if FreeSpinNumber <= 0:
            raise ValueError("FreeSpinNumber must be positive")
        result = self._spin_and_evaluate(
            index, general_index, True, FreeSpinNumber, return_detail, max_cascades
        )
        self.LastFgResult = result
        return result

    def _spin_and_evaluate(
        self,
        index: int,
        general_index: int,
        free_game: bool,
        FreeSpinNumber: int,
        return_detail: bool,
        max_cascades: int,
    ) -> dict:
        if max_cascades <= 0:
            raise ValueError("max_cascades must be positive")
        heights = [
            self.MinimumReelHeight + self._weighted_index(weights)
            for weights in self.ReelHeightWeights
        ]
        raw_board = self.spin(
            index=index,
            general_index=general_index,
            row=6,
            col=6,
            reel_config_dir=self.FreeReelConfigDir if free_game else None,
            reel_file_template=(
                "kldg_free_rand_ex_{index}.conf" if free_game else "kldg_rand_ex_{index}.conf"
            ),
        )
        spin_state = self.clone_spin_state(self.last_spin_state)
        board = [
            [self._initial_cell(symbol, col, row) for row, symbol in enumerate(raw_board[col][:height])]
            for col, height in enumerate(heights)
        ]
        initial_board = self._board_detail(board)
        scatter_count = self._count_scatter(board)
        total_win = 0
        cascade_count = 0
        rounds = []

        for cascade_index in range(1, max_cascades + 1):
            base_win, win_positions, win_items = self._evaluate_paths(board)
            if not win_positions:
                break
            multiplier = (
                FreeSpinNumber + cascade_index - 1
                if free_game else min(cascade_index, self.MainMultiplierCap)
            )
            round_win = base_win * multiplier
            total_win += round_win
            cascade_count += 1
            before_board = self._board_detail(board) if return_detail else None
            board, new_scatter_count = self._advance_board(board, win_positions, spin_state)
            scatter_count += new_scatter_count
            if return_detail:
                paid_items = [
                    {**item, "BaseWin": item["Win"], "Win": item["Win"] * multiplier}
                    for item in win_items
                ]
                rounds.append(
                    {
                        "CascadeIndex": cascade_index,
                        "Board": before_board,
                        "WinPositions": sorted(win_positions),
                        "WinItems": paid_items,
                        "Multiplier": multiplier,
                        "BaseWin": base_win,
                        "Win": round_win,
                        "NewScatterCount": new_scatter_count,
                        "NextBoard": self._board_detail(board),
                    }
                )
        else:
            if self._evaluate_paths(board)[1]:
                raise RuntimeError(f"cascade exceeded max_cascades={max_cascades}")

        result = {
            "Mode": "Free" if free_game else "Main",
            "BaseBet": self.base_bet,
            "ReelHeights": heights,
            "InitialBoard": initial_board,
            "FinalBoard": self._board_detail(board),
            "TotalWin": total_win,
            "CascadeCount": cascade_count,
            "ScatterCount": scatter_count,
            "FreeSpinsAwarded": (
                self.BaseFreeSpins
                + self.ExtraFreeSpinsPerScatter * (scatter_count - self.FreeTriggerScatterCount)
                if not free_game and scatter_count >= self.FreeTriggerScatterCount else 0
            ),
            "ExtraFreeSpins": scatter_count if free_game else 0,
            "FreeSpinNumber": FreeSpinNumber if free_game else 0,
        }
        if return_detail:
            result["Rounds"] = rounds
        return result

    @staticmethod
    def _board_detail(board: list[list[Cell]]) -> list[list[dict]]:
        return [
            [{"SymbolId": cell.SymbolId, "FrameStage": cell.FrameStage} for cell in column]
            for column in board
        ]

    @classmethod
    def _count_scatter(cls, board: list[list[Cell]]) -> int:
        return sum(cell.SymbolId == cls.ScatterId for column in board for cell in column)

    def cal_item_list(
        self,
        item_list,
        return_detail: bool = False,
        free_game: bool = False,
        row: int | None = None,
        col: int | None = None,
    ):
        """保留 WaysGame 入口，使用本机台的 Wild 最高奖规则算当前盘面。"""

        columns, _, _ = self._normalize_item_list(item_list, row=row, col=col)
        board = [[Cell(symbol) for symbol in column] for column in columns]
        total_win, win_positions, win_items = self._evaluate_paths(board)
        self.last_win_items = win_items
        self.last_win_positions = sorted(win_positions)
        if return_detail:
            # 这些键来自现有 WaysGame 返回约定，供旧调用者复用。
            return {
                "total_win": total_win,
                "items": win_items,
                "win_positions": sorted(win_positions),
            }
        return total_win

    def _evaluate_paths(self, board: list[list[Cell]]) -> tuple[int, set[tuple[int, int]], list[dict]]:
        """相同路径及共享 Wild 前缀的长短路径只结算最高一奖。"""

        best_by_path: dict[tuple[tuple[int, int], ...], tuple[int, int]] = {}
        for item_id in self.OrdinaryIds:
            matches = []
            for column in board:
                rows = [
                    row for row, cell in enumerate(column)
                    if cell.SymbolId in (item_id, self.WildId)
                ]
                if not rows:
                    break
                matches.append(rows)
            hit_count = len(matches)
            if hit_count < 3:
                continue
            prize = self.config.item_prizes[item_id][hit_count - 1]
            if prize <= 0:
                continue
            for row_path in product(*matches):
                path = tuple(enumerate(row_path))
                prior = best_by_path.get(path)
                if prior is None or prize > prior[0]:
                    best_by_path[path] = (prize, item_id)

        selected_paths: set[tuple[tuple[int, int], ...]] = set()
        selected_prefixes: set[tuple[tuple[int, int], ...]] = set()
        win_positions: set[tuple[int, int]] = set()
        win_items = []
        total_win = 0
        for path, (prize, item_id) in sorted(
            best_by_path.items(), key=lambda entry: (-entry[1][0], -len(entry[0]), entry[1][1])
        ):
            if path in selected_prefixes or any(
                path[:length] in selected_paths for length in range(3, len(path))
            ):
                continue
            selected_paths.add(path)
            for length in range(3, len(path) + 1):
                selected_prefixes.add(path[:length])
            win_positions.update(path)
            win = self.base_bet * prize // self.BET_UNIT // max(self.config.prize_rate, 1)
            total_win += win
            win_items.append(
                {"ItemId": item_id, "Positions": path, "HitCount": len(path), "Prize": prize, "Win": win}
            )
        return total_win, win_positions, win_items

    def _advance_board(
        self,
        board: list[list[Cell]],
        win_positions: set[tuple[int, int]],
        spin_state: dict,
    ) -> tuple[list[list[Cell]], int]:
        next_board = []
        new_scatter_count = 0
        for col, column in enumerate(board):
            survivors = []
            for row, cell in enumerate(column):
                if (col, row) not in win_positions:
                    survivors.append(cell)
                elif cell.FrameStage == 1:
                    symbol = self.OrdinaryIds[self._weighted_index(self.SilverUpgradeSymbolWeights)]
                    survivors.append(Cell(symbol, 2))
                elif cell.FrameStage == 2:
                    survivors.append(Cell(self.WildId))
            need_count = len(column) - len(survivors)
            symbols = self.take_symbols_above(spin_state, col, need_count)
            new_scatter_count += sum(symbol == self.ScatterId for symbol in symbols)
            new_cells = [self._initial_cell(symbol, col, row) for row, symbol in enumerate(symbols)]
            next_board.append(new_cells + survivors)
        return next_board, new_scatter_count

