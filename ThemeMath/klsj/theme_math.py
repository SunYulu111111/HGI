"""恐龙世界数值结算：六列变高 Ways、框转换、连消和免费游戏。"""

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
    SymbolId: int  # 0=Scatter，1=Wild，2～12=普通图标
    FrameStage: int = 0  # 0=无框，1=银框，2=金框
    Height: int = 1  # 物理占格数；每个图标只计一个 Ways 物件


class ThemeMath(WaysGame):
    """读取盘面、轴带和权重，结算主游戏及免费游戏。"""

    DefaultGameConfigFile = "special/klsj_game_config.conf"
    DefaultGameServerConfigFile = "special/klsj_game_server.conf"
    FreeReelConfigDir = "free_reel_config"
    ScatterId = 0
    WildId = 1
    OrdinaryIds = tuple(range(2, 13))
    FrameColumns = (1, 2, 3, 4)  # 列索引从 0 开始，对应第 2～5 列
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
        # 各列权重与固定顺序的图标高度拆分一一对应。
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
            info, "MainExtraFreeSpinsPerScatter", self.ExtraFreeSpinsPerScatter, minimum=1
        )
        self.ExtraFreeSpinsPerScatter = self.MainExtraFreeSpinsPerScatter
        self.FreeExtraSpinsPerScatter = self._parse_control_int(
            info, "FreeExtraSpinsPerScatter", self.FreeExtraSpinsPerScatter, minimum=0
        )
        if self.FreeExtraSpinsPerScatter != 1:
            raise ValueError("FreeExtraSpinsPerScatter must be 1: each new Scatter adds one free spin")
        self.FreeMaxTimes = self._parse_control_int(
            info, "Free_Max_Times", None, minimum=1
        )
        if self.BaseFreeSpins > self.FreeMaxTimes:
            raise ValueError("BaseFreeSpins must not exceed Free_Max_Times")
        self.BaseMaxEliTimes = self._parse_control_int(
            info, "BaseMaxEliTimes", None, minimum=1
        )
        self.FreeMaxEliTimes = self._parse_control_int(
            info, "Free_Max_EliTimes", None, minimum=1
        )
        self.ValidatedReelFiles: set[Path] = set()
        self.NextFreeStartMultiplier = 1
        self.NextFreeSpinNumber = 1
        self._CurrentFreeGame = False
        self.LastNgResult: dict = {}
        self.LastFgResult: dict = {}

    def _validate_game_protocol(self, ConfigPath: Path) -> None:
        """校验左起 Ways 开关及全有效的固定盘面容器。"""
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
        """校验所有轴段和预设盘面的图标 ID、列数及 Wild 列限制。"""
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
        """按固定顺序列出总高度的拆分，每个图标高度为 1～4。"""

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
        """校验布局字段、列号、高度索引及必填控制参数。"""
        expected = {"BaseMaxEliTimes", "Free_Max_EliTimes", "Free_Max_Times"}
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
        """校验图标 ID、尺寸和 Wild 列，再为符合条件的新普通图标抽取银框。"""
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

    def _scatter_generation_budget(
        self, FreeGame: bool, FreeSpinNumber: int, FreeSpinsRemaining: int,
    ) -> int:
        """将可追加次数换算为本手初盘和全部补牌共享的新 Scatter 额度。"""
        if FreeGame:
            return self.FreeMaxTimes - FreeSpinNumber - FreeSpinsRemaining
        return self.FreeTriggerScatterCount + (
            self.FreeMaxTimes - self.BaseFreeSpins
        ) // self.MainExtraFreeSpinsPerScatter

    def _limit_new_scatter(
        self, SymbolId: int, Col: int, ScatterGeneration: dict | None,
    ) -> int:
        if SymbolId != self.ScatterId or ScatterGeneration is None:
            return SymbolId
        Budget = ScatterGeneration["ScatterBudget"]
        if Budget > 0:
            ScatterGeneration["ScatterBudget"] -= 1
            return SymbolId
        Pool = ScatterGeneration["OrdinaryPools"][Col]
        if not Pool:
            raise ValueError(f"column {Col + 1} has no ordinary symbols for Scatter replacement")
        # 重复项保留原轴频次；替换不额外读取轴带或推进停轴。
        return random.choice(Pool)

    def _build_column(
        self,
        Symbols: list[int],
        Layout: tuple[int, ...],
        Col: int,
        FreeGame: bool,
        SpinState: dict | None = None,
        ScatterGeneration: dict | None = None,
    ) -> list[Cell]:
        """先限制新 Scatter 生成，再将准入的高 Scatter 设为 2 格并补足空缺。"""
        OriginalCount = len(Layout)
        if len(Symbols) < OriginalCount:
            raise ValueError("not enough symbols for column layout")
        if ScatterGeneration is None and SpinState is not None:
            ScatterGeneration = SpinState.get("ScatterGeneration")
        RawOriginalSymbols = Symbols[:OriginalCount]
        # 原配对图标先取得额度；被替换的高图标保留高度，不再按 Scatter 拆分。
        OriginalSymbols = [
            self._limit_new_scatter(Symbol, Col, ScatterGeneration)
            for Symbol in RawOriginalSymbols
        ]
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
            # 前 N 个符号参与布局，剩余缓冲用于补足 Scatter 上方空缺。
            ExtraSymbols = Symbols[OriginalCount:OriginalCount + ExtraCount]
        else:
            # 一次读取全部补牌：前段填额外空缺，后段对应布局中的图标。
            DrawnSymbols = self.take_symbols_above(SpinState, Col, OriginalCount + ExtraCount)
            if DrawnSymbols[ExtraCount:] != RawOriginalSymbols:
                raise ValueError("refill preview does not match reel state")
            ExtraSymbols = DrawnSymbols[:ExtraCount]
        if len(ExtraSymbols) != ExtraCount:
            raise ValueError("not enough buffered symbols for Scatter remainder")
        Cells = []
        ExtraIndex = 0
        for Symbol, Height, ExtraLayout in zip(OriginalSymbols, Layout, ExtraLayouts):
            for ExtraHeight in ExtraLayout:
                ExtraSymbol = self._limit_new_scatter(
                    ExtraSymbols[ExtraIndex], Col, ScatterGeneration
                )
                Cells.append(self._initial_cell(ExtraSymbol, Col, ExtraHeight))
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
        # 新付费手触发的免费游戏从 x1 开始。
        self.NextFreeStartMultiplier = 1
        self.NextFreeSpinNumber = 1
        result = self._spin_and_evaluate(index, general_index, False, 0, 0, return_detail, max_cascades)
        self.LastNgResult = result
        return result

    def fg_spin(
        self,
        index: int = 0,
        general_index: int = 1,
        FreeSpinNumber: int | None = None,
        return_detail: bool = False,
        max_cascades: int = 100,
        FreeStartMultiplier: int | None = None,
        FreeSpinsRemaining: int = 0,
    ) -> dict:
        """免费起始倍数继承上一手终倍加 1；待玩次数为扣除本手后的次数。"""
        if FreeSpinNumber is None:
            FreeSpinNumber = self.NextFreeSpinNumber
        if not isinstance(FreeSpinNumber, int) or not 1 <= FreeSpinNumber <= self.FreeMaxTimes:
            raise ValueError(f"FreeSpinNumber must be in 1..{self.FreeMaxTimes}")
        if not isinstance(FreeSpinsRemaining, int) or FreeSpinsRemaining < 0:
            raise ValueError("FreeSpinsRemaining must be a nonnegative integer")
        if FreeSpinNumber + FreeSpinsRemaining > self.FreeMaxTimes:
            raise ValueError("FreeSpinNumber + FreeSpinsRemaining exceeds Free_Max_Times")
        if FreeStartMultiplier is None:
            FreeStartMultiplier = self.NextFreeStartMultiplier
        if FreeStartMultiplier <= 0:
            raise ValueError("FreeStartMultiplier must be positive")
        result = self._spin_and_evaluate(
            index, general_index, True, FreeSpinNumber, FreeStartMultiplier,
            return_detail, max_cascades, FreeSpinsRemaining,
        )
        # 下一手继承本手最终结算倍数，再加 1。
        self.NextFreeStartMultiplier = result["FreeEndMultiplier"] + 1
        self.NextFreeSpinNumber = FreeSpinNumber + 1
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
        FreeSpinsRemaining: int = 0,
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
        spin_state["ScatterGeneration"] = {
            "ScatterBudget": self._scatter_generation_budget(
                free_game, FreeSpinNumber, FreeSpinsRemaining
            ),
            "OrdinaryPools": [
                [Symbol for Symbol in Column if Symbol in self.OrdinaryIds]
                for Column in spin_state["columns"]
            ],
        }
        self._CurrentFreeGame = free_game
        layouts = [
            self._select_layout(height, col, free_game, initial=True)
            for col, height in enumerate(heights)
        ]
        board = [
            self._build_column(
                raw_board[col], layout, col, free_game,
                ScatterGeneration=spin_state["ScatterGeneration"],
            )
            for col, layout in enumerate(layouts)
        ]
        # 输出实际图标高度和数量，包含 Scatter 上方补入的图标。
        layouts = [tuple(cell.Height for cell in column) for column in board]
        initial_board = self._board_detail(board)
        scatter_count = self._count_scatter(board)
        total_win = 0
        cascade_count = 0
        rounds = []
        # 无中奖时，免费结束倍数等于本手起始倍数。
        FreeEndMultiplier = FreeStartMultiplier if free_game else 0

        for cascade_index in range(1, max_cascades + 1):
            base_win, win_positions, win_items = self._evaluate_paths(board)
            if not win_positions:
                break
            # 手内增量达到上限后仍按该倍数结算后续中奖。
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
                scatter_count if free_game else 0
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
        """计算当前盘面奖励，同一路径只结算最高奖项。"""

        columns, _, _ = self._normalize_item_list(item_list, row=row, col=col)
        board = [[Cell(symbol) for symbol in column] for column in columns]
        total_win, win_positions, win_items = self._evaluate_paths(board)
        self.last_win_items = win_items
        self.last_win_positions = sorted(win_positions)
        if return_detail:
            return {
                "total_win": total_win,
                "items": win_items,
                "win_positions": sorted(win_positions),
            }
        return total_win

    def _evaluate_paths(self, board: list[list[Cell]]) -> tuple[int, set[tuple[int, int]], list[dict]]:
        """计算有效路径奖励，共享 Wild 前缀不重复派奖。"""

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
        new_scatter_count = 0  # 只累计本轮新补入的物理 Scatter
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

