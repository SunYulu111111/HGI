"""恐龙世界数学入口：六列变高 Ways、边框升级、连消和免费旋转。"""

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
    Height: int = 1  # 高图标占据的物理格子数；Ways 仍按一个图标计算


class ThemeMath(WaysGame):
    """沿用 Ways 模板的配置和转轴入口，执行 klsj 专属结算。"""

    DefaultGameConfigFile = "special/klsj_game_config.conf"
    DefaultGameServerConfigFile = "special/klsj_game_server.conf"
    FreeReelConfigDir = "free_reel_config"
    ScatterId = 0
    WildId = 1
    OrdinaryIds = tuple(range(2, 13))
    FrameColumns = (1, 2, 3, 4)
    SilverFrameHeights = (2, 3, 4)
    ChanceBase = 10000
    MinimumReelHeight = 2
    MainMultiplierCap = 5
    FreeSpinMultiplierIncrementCap = 4
    FreeTriggerScatterCount = 4
    BaseFreeSpins = 8
    ExtraFreeSpinsPerScatter = 2
    FreeExtraSpinsPerScatter = 1

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
            reel_file_template="klsj_rand_ex_{index}.conf",
            **kwargs,
        )
        if self.config.col_count != 6 or self.config.row_count != 6 or self.config.item_count != 13:
            raise ValueError("klsj requires 6 columns, maximum height 6, and 13 symbols")
        self._validate_game_protocol(self.project_dir / game_config_file)
        server_path = self.project_dir / game_server_config_file
        server = ConfigParser(inline_comment_prefixes=("#", ";"))
        server.optionxform = str
        if not server.read(server_path, encoding="utf-8-sig") or not server.has_section("Game Info"):
            raise ValueError(f"missing [Game Info]: {server_path}")
        info = server["Game Info"]
        self.ReelHeightWeights = self._parse_height_weights(info)
        # yjzr 固定布局顺序；服务器配置仅存放各列的逗号分隔权重。
        self.MainHeightPatterns = self._canonical_patterns(6)
        self.FreeHeightPatterns = self._canonical_patterns(6)
        self._validate_layout_keys(info)
        self.MainHeightWeights = self._parse_column_weights(info, "base_height_weight")
        self.FreeHeightWeights = self._parse_column_weights(info, "free_height_weight")
        self.MainEliminationHeightWeights = self._parse_elimination_column_weights(
            info, "base_elim_height_weight"
        )
        self.FreeEliminationHeightWeights = self._parse_elimination_column_weights(
            info, "free_elim_height_weight"
        )
        self.SilverFrameChance = int(info["SilverFrameChance"])
        if not 0 <= self.SilverFrameChance <= self.ChanceBase:
            raise ValueError("SilverFrameChance must be in 0..10000")
        self.SilverUpgradeSymbolWeights = self._parse_weights(
            info["SilverUpgradeSymbolWeights"], len(self.OrdinaryIds)
        )
        self.MainMultiplierCap = self._parse_control_int(
            info, "MainMultiplierCap", self.MainMultiplierCap, minimum=1
        )
        self.FreeSpinMultiplierIncrementCap = self._parse_control_int(
            info, "FreeSpinMultiplierIncrementCap", self.FreeSpinMultiplierIncrementCap, minimum=0
        )
        self.FreeTriggerScatterCount = self._parse_control_int(
            info, "FreeTriggerScatterCount", self.FreeTriggerScatterCount, minimum=1
        )
        self.BaseFreeSpins = self._parse_control_int(
            info, "BaseFreeSpins", self.BaseFreeSpins, minimum=0
        )
        self.MainExtraFreeSpinsPerScatter = self._parse_control_int(
            info, "MainExtraFreeSpinsPerScatter", self.ExtraFreeSpinsPerScatter, minimum=0
        )
        # Keep the existing attribute as a compatibility alias for callers that read it.
        self.ExtraFreeSpinsPerScatter = self.MainExtraFreeSpinsPerScatter
        self.FreeExtraSpinsPerScatter = self._parse_control_int(
            info, "FreeExtraSpinsPerScatter", self.FreeExtraSpinsPerScatter, minimum=0
        )
        self.BaseMaxEliTimes = self._parse_control_int(
            info, "BaseMaxEliTimes", None, minimum=1
        )
        self.FreeMaxEliTimes = self._parse_control_int(
            info, "Free_Max_EliTimes", None, minimum=1
        )
        self.ValidatedReelFiles: set[Path] = set()
        self.NextFreeStartMultiplier = 1
        self._CurrentFreeGame = False
        self.LastNgResult: dict = {}
        self.LastFgResult: dict = {}

    def _validate_game_protocol(self, ConfigPath: Path) -> None:
        """读取 yjzr 同名开关，拒绝当前 klsj 结算器不支持的固定屏蔽/连线模式。"""
        Parser = ConfigParser(inline_comment_prefixes=("#", ";"))
        Parser.optionxform = str
        Parser.read(ConfigPath, encoding="utf-8-sig")
        Main = Parser["MAIN"]
        for Key, Count in (
            ("BOTH_SIDES", self.config.item_count),
            ("FULL_WILD_LINE", 1),
            ("GRID_DISABLES", self.config.col_count * self.config.row_count),
            ("GRID_DISABLES_FREE", self.config.col_count * self.config.row_count),
        ):
            if Key not in Main:
                raise ValueError(f"missing yjzr game field: {Key}")
            try:
                Values = [int(Part.strip()) for Part in Main[Key].split(",")]
            except ValueError as Exc:
                raise ValueError(f"{Key} must contain {Count} integer zero values") from Exc
            if len(Values) != Count or any(Value != 0 for Value in Values):
                raise ValueError(f"{Key} must contain {Count} zero values for klsj Ways")
        if self.config.line_mode != 1:
            raise ValueError("klsj requires LINE_MODE=1")

    def _load_reel_config(
        self,
        index: int,
        general_index: int,
        reel_config_dir: str | Path | None = None,
        reel_file_template: str | None = None,
    ) -> dict:
        Config = super()._load_reel_config(
            index, general_index, reel_config_dir, reel_file_template
        )
        ConfigPath = Path(Config["reel_config_path"])
        if ConfigPath not in self.ValidatedReelFiles:
            self._validate_reel_file(ConfigPath)
            self.ValidatedReelFiles.add(ConfigPath)
        return Config

    def _validate_reel_file(self, ConfigPath: Path) -> None:
        """所有轴段和预设结果均校验，未启用的特殊／固定／零奖盘也不例外。"""
        Parser = self._read_config_file(ConfigPath)
        for SectionName in Parser.sections():
            if not SectionName.startswith("GENERAL_"):
                continue
            Section = Parser[SectionName]
            for Field, Value in Section.items():
                RollPrefix = next((Prefix for Prefix in ("NORMAL_ROLL_", "SP_ROLL_")
                                   if Field.startswith(Prefix)), None)
                ResultPrefix = next((Prefix for Prefix in ("FIX_RESULT_", "ZERO_RESULT_")
                                     if Field.startswith(Prefix)), None)
                if RollPrefix is None and ResultPrefix is None:
                    continue
                Prefix = RollPrefix if RollPrefix is not None else ResultPrefix
                Suffix = Field[len(Prefix):]
                if not Suffix.isdigit() or int(Suffix) < 1:
                    raise ValueError(f"{ConfigPath.name} [{SectionName}] invalid field: {Field}")
                Symbols = self._parse_int_list(Value)
                if not Symbols or any(Symbol < 0 or Symbol >= self.config.item_count
                                      for Symbol in Symbols):
                    raise ValueError(f"{ConfigPath.name} [{SectionName}] {Field}: invalid symbol IDs")
                if RollPrefix is not None:
                    Column = int(Suffix) - 1
                    if Column >= self.config.col_count:
                        raise ValueError(f"{ConfigPath.name} [{SectionName}] invalid column: {Field}")
                    Columns = [(Column, Symbols)]
                else:
                    ExpectedCount = self.config.col_count * self.config.row_count
                    if len(Symbols) != ExpectedCount:
                        raise ValueError(f"{ConfigPath.name} [{SectionName}] {Field}: "
                                         f"expected {ExpectedCount} symbols")
                    Columns = [(Column, Symbols[Column * self.config.row_count:
                                                (Column + 1) * self.config.row_count])
                               for Column in range(self.config.col_count)]
                for Column, ColumnSymbols in Columns:
                    if Column not in self.FrameColumns and self.WildId in ColumnSymbols:
                        raise ValueError(f"{ConfigPath.name} [{SectionName}] {Field}: "
                                         f"Wild is only allowed in columns 2..5 (column {Column + 1})")

    @staticmethod
    def _parse_control_int(info, key: str, default: int | None, minimum: int) -> int:
        value_text = (info[key] if default is None else info.get(key, str(default))).strip()
        try:
            value = int(value_text)
        except ValueError as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if value < minimum:
            raise ValueError(f"{key} must be >= {minimum}")
        return value

    @staticmethod
    def _parse_weights(value: str, count: int) -> list[int]:
        weights = [int(part.strip()) for part in value.split(",")]
        if len(weights) != count or any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ValueError(f"expected {count} nonnegative weights with a positive total")
        return weights

    @classmethod
    def _parse_height_weights(cls, info) -> list[list[int]]:
        if "ReelHeightWeights" in info:
            raise ValueError("use per-column ReelHeightWeights1..6 fields")
        groups = []
        for column in range(1, 7):
            key = f"ReelHeightWeights{column}"
            if key not in info:
                raise ValueError(f"missing physical height field: {key}")
            try:
                groups.append(cls._parse_weights(info[key], 5))
            except ValueError as exc:
                raise ValueError(f"{key}: {exc}") from exc
        return groups

    @classmethod
    def _canonical_patterns(cls, total_height: int) -> list[tuple[int, ...]]:
        """Return the reference theme's high-symbol partitions for a given height."""

        patterns = []

        def build(remaining: int, current: list[int], minimum: int):
            if remaining == 0:
                patterns.append(tuple(current))
                return
            for height in range(minimum, min(4, remaining) + 1):
                build(remaining - height, current + [height], height)

        build(total_height, [], 1)
        return patterns

    @staticmethod
    def _validate_layout_keys(info) -> None:
        """拒绝旧布局字段和错写的索引，避免配置被静默忽略。"""
        expected = {"BaseMaxEliTimes", "Free_Max_EliTimes"}
        for mode in ("base", "free"):
            for column in range(1, 7):
                expected.add(f"{mode}_height_weight_{column}")
                for height in range(2, 7):
                    expected.add(f"{mode}_elim_height_weight_{column}_{height}")
        for key in info:
            legacy = key.startswith((
                "MainHeight", "FreeHeight", "MainEliminationHeight", "FreeEliminationHeight"
            )) or key in ("MainMaxEliminationTimes", "FreeMaxEliminationTimes")
            indexed = key.startswith((
                "base_height_weight", "free_height_weight",
                "base_elim_height_weight", "free_elim_height_weight",
            ))
            if legacy or (indexed and key not in expected):
                raise ValueError(f"unsupported layout/control field: {key}; use yjzr field format")
        missing = sorted(expected - set(info))
        if missing:
            raise ValueError(f"missing yjzr layout/control fields: {', '.join(missing)}")

    @classmethod
    def _read_layout_weights(cls, info, key: str, total_height: int) -> list[int]:
        try:
            return cls._parse_weights(info[key], len(cls._canonical_patterns(total_height)))
        except ValueError as exc:
            raise ValueError(f"{key}: {exc}") from exc

    @classmethod
    def _parse_column_weights(cls, info, prefix: str) -> list[list[int]]:
        return [cls._read_layout_weights(info, f"{prefix}_{column}", 6)
                for column in range(1, 7)]

    @classmethod
    def _parse_elimination_column_weights(
        cls, info, prefix: str
    ) -> list[dict[int, list[int]]]:
        return [
            {1: [1], **{
                height: cls._read_layout_weights(info, f"{prefix}_{column}_{height}", height)
                for height in range(2, 7)
            }}
            for column in range(1, 7)
        ]

    @staticmethod
    def _weighted_index(weights: list[int]) -> int:
        hit = random.randrange(sum(weights))
        for index, weight in enumerate(weights):
            if hit < weight:
                return index
            hit -= weight
        raise AssertionError("positive weights must select an index")

    def _initial_cell(
        self,
        symbol_id: int,
        col: int,
        height: int = 1,
    ) -> Cell:
        """校验新图标后，按 symbol 自身高度判定银框资格。"""
        if symbol_id < 0 or symbol_id >= self.config.item_count:
            raise ValueError("symbol ID must be in 0..12")
        if not 1 <= height <= 4:
            raise ValueError("symbol height must be in 1..4")
        if symbol_id == self.ScatterId and height > 2:
            raise ValueError("Scatter height must be in 1..2")
        if symbol_id == self.WildId and col not in self.FrameColumns:
            raise ValueError("Wild is only allowed in columns 2..5")
        if (
            col in self.FrameColumns
            and height in self.SilverFrameHeights
            and symbol_id in self.OrdinaryIds
            and random.randrange(self.ChanceBase) < self.SilverFrameChance
        ):
            return Cell(symbol_id, 1, height)
        return Cell(symbol_id, 0, height)

    def _select_layout(
        self, total_height: int, col: int, free_game: bool, initial: bool
    ) -> tuple[int, ...]:
        if total_height <= 0:
            return ()
        if initial and total_height == 6:
            patterns = self.FreeHeightPatterns if free_game else self.MainHeightPatterns
            weights = (self.FreeHeightWeights if free_game else self.MainHeightWeights)[col]
        else:
            patterns = self._canonical_patterns(total_height)
            weights = (
                self.FreeEliminationHeightWeights if free_game else self.MainEliminationHeightWeights
            )[col][total_height]
        layout = list(patterns[self._weighted_index(weights)])
        random.shuffle(layout)
        return tuple(layout)

    def _build_column(
        self,
        Symbols: list[int],
        Layout: tuple[int, ...],
        Col: int,
        FreeGame: bool,
        SpinState: dict | None = None,
    ) -> list[Cell]:
        """局部拆分高 Scatter，保留原配对图标和列高；额外空缺置于 Scatter 上方。"""
        OriginalCount = len(Layout)
        if len(Symbols) < OriginalCount:
            raise ValueError("not enough symbols for column layout")
        OriginalSymbols = Symbols[:OriginalCount]
        ExtraLayouts = []
        for Symbol, Height in zip(OriginalSymbols, Layout):
            ExtraLayout = ()
            if Symbol == self.ScatterId and Height > 2:
                ExtraLayout = self._select_layout(Height - 2, Col, FreeGame, initial=False)
                if sum(ExtraLayout) != Height - 2 or any(Size not in (1, 2) for Size in ExtraLayout):
                    raise ValueError("Scatter remainder layout must preserve physical height")
            ExtraLayouts.append(ExtraLayout)
        ExtraCount = sum(len(ExtraLayout) for ExtraLayout in ExtraLayouts)
        if SpinState is None:
            # 初盘保留前 N 个原配对符号，额外槽位使用窗口中尚未配对的缓冲。
            ExtraSymbols = Symbols[OriginalCount:OriginalCount + ExtraCount]
        else:
            # 预览后的实际读取只进行一次。前段是较高的新增符号，后段保留原配对。
            DrawnSymbols = self.take_symbols_above(SpinState, Col, OriginalCount + ExtraCount)
            if DrawnSymbols[ExtraCount:] != OriginalSymbols:
                raise ValueError("refill preview does not match reel state")
            ExtraSymbols = DrawnSymbols[:ExtraCount]
        if len(ExtraSymbols) != ExtraCount:
            raise ValueError("not enough buffered symbols for Scatter remainder")
        Cells = []
        ExtraIndex = 0
        for Symbol, Height, ExtraLayout in zip(OriginalSymbols, Layout, ExtraLayouts):
            for ExtraHeight in ExtraLayout:
                Cells.append(self._initial_cell(ExtraSymbols[ExtraIndex], Col, ExtraHeight))
                ExtraIndex += 1
            CellHeight = 2 if ExtraLayout else Height
            Cells.append(self._initial_cell(Symbol, Col, CellHeight))
        if sum(CellItem.Height for CellItem in Cells) != sum(Layout):
            raise AssertionError("column generation changed physical height")
        return Cells

    def ng_spin(
        self,
        index: int = 0,
        general_index: int = 1,
        return_detail: bool = False,
        max_cascades: int = 100,
    ) -> dict:
        # 一手新的付费游戏开始新的免费整轮，首手免费起始倍数为 1。
        self.NextFreeStartMultiplier = 1
        result = self._spin_and_evaluate(index, general_index, False, 0, 0, return_detail, max_cascades)
        self.LastNgResult = result
        return result

    def fg_spin(
        self,
        index: int = 0,
        general_index: int = 1,
        FreeSpinNumber: int = 1,
        return_detail: bool = False,
        max_cascades: int = 100,
        FreeStartMultiplier: int | None = None,
    ) -> dict:
        if FreeSpinNumber <= 0:
            raise ValueError("FreeSpinNumber must be positive")
        if FreeStartMultiplier is None:
            FreeStartMultiplier = self.NextFreeStartMultiplier
        if FreeStartMultiplier <= 0:
            raise ValueError("FreeStartMultiplier must be positive")
        result = self._spin_and_evaluate(
            index, general_index, True, FreeSpinNumber, FreeStartMultiplier,
            return_detail, max_cascades,
        )
        self.NextFreeStartMultiplier = result["FreeEndMultiplier"] + 1
        self.LastFgResult = result
        return result

    def _spin_and_evaluate(
        self,
        index: int,
        general_index: int,
        free_game: bool,
        FreeSpinNumber: int,
        FreeStartMultiplier: int,
        return_detail: bool,
        max_cascades: int,
    ) -> dict:
        if max_cascades <= 0:
            raise ValueError("max_cascades must be positive")
        max_cascades = min(
            max_cascades,
            self.FreeMaxEliTimes if free_game else self.BaseMaxEliTimes,
        )
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
                "klsj_free_rand_ex_{index}.conf" if free_game else "klsj_rand_ex_{index}.conf"
            ),
        )
        spin_state = self.clone_spin_state(self.last_spin_state)
        self._CurrentFreeGame = free_game
        layouts = [
            self._select_layout(height, col, free_game, initial=True)
            for col, height in enumerate(heights)
        ]
        board = [
            self._build_column(raw_board[col], layout, col, free_game)
            for col, layout in enumerate(layouts)
        ]
        # Scatter 拆分后的实际布局是结果协议的来源。
        layouts = [tuple(cell.Height for cell in column) for column in board]
        initial_board = self._board_detail(board)
        scatter_count = self._count_scatter(board)
        total_win = 0
        cascade_count = 0
        rounds = []
        FreeEndMultiplier = FreeStartMultiplier if free_game else 0

        for cascade_index in range(1, max_cascades + 1):
            base_win, win_positions, win_items = self._evaluate_paths(board)
            if not win_positions:
                break
            multiplier = (
                FreeStartMultiplier + min(cascade_index - 1, self.FreeSpinMultiplierIncrementCap)
                if free_game else min(cascade_index, self.MainMultiplierCap)
            )
            if free_game:
                FreeEndMultiplier = multiplier
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
            "ReelLayouts": [list(layout) for layout in layouts],
            "ReelCellCounts": [len(layout) for layout in layouts],
            "InitialBoard": initial_board,
            "FinalBoard": self._board_detail(board),
            "TotalWin": total_win,
            "CascadeCount": cascade_count,
            "ScatterCount": scatter_count,
            "FreeSpinsAwarded": (
                self.BaseFreeSpins
                + self.MainExtraFreeSpinsPerScatter * (scatter_count - self.FreeTriggerScatterCount)
                if not free_game and scatter_count >= self.FreeTriggerScatterCount else 0
            ),
            "ExtraFreeSpins": (
                scatter_count * self.FreeExtraSpinsPerScatter if free_game else 0
            ),
            "FreeSpinNumber": FreeSpinNumber if free_game else 0,
            "FreeStartMultiplier": FreeStartMultiplier if free_game else 0,
            "FreeEndMultiplier": FreeEndMultiplier,
        }
        if return_detail:
            result["Rounds"] = rounds
        return result

    @staticmethod
    def _board_detail(board: list[list[Cell]]) -> list[list[dict]]:
        return [
            [
                {"SymbolId": cell.SymbolId, "FrameStage": cell.FrameStage, "Height": cell.Height}
                for cell in column
            ]
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
        free_game = getattr(self, "_CurrentFreeGame", False)
        for col, column in enumerate(board):
            survivors = []
            removed_height = 0
            for row, cell in enumerate(column):
                if (col, row) not in win_positions:
                    survivors.append(cell)
                elif cell.FrameStage == 1:
                    symbol = self.OrdinaryIds[self._weighted_index(self.SilverUpgradeSymbolWeights)]
                    survivors.append(Cell(symbol, 2, cell.Height))
                elif cell.FrameStage == 2:
                    survivors.append(self._initial_cell(self.WildId, col, cell.Height))
                else:
                    removed_height += cell.Height
            refill_layout = self._select_layout(removed_height, col, free_game, initial=False)
            PreviewState = {**spin_state, "top_indexes": spin_state["top_indexes"][:]}
            Symbols = self.take_symbols_above(PreviewState, col, len(refill_layout))
            new_cells = self._build_column(Symbols, refill_layout, col, free_game, spin_state)
            new_scatter_count += self._count_scatter([new_cells])
            next_board.append(new_cells + survivors)
        return next_board, new_scatter_count

