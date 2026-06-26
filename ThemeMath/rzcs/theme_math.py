"""Minimal line-game theme entry.

This model file intentionally keeps theme-specific feature logic out of the
theme layer. Line evaluation is delegated to slots_math.LinesGame.
"""

from pathlib import Path
import random
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from slots_math import LinesGame


class ThemeMath(LinesGame):
    """Thin wrapper for a fixed-line game model."""

    FREE_REEL_CONFIG_DIR = "free_reel_config"
    PROBABILITY_DENOMINATOR = 10000

    def __init__(self, base_bet: int = 10000, **kwargs):
        project_dir = kwargs.pop("project_dir", Path(__file__).resolve().parent)
        self.game_server_config_file = kwargs.pop("game_server_config_file", "game_server.conf")
        game_config_file = kwargs.get("game_config_file", self.DEFAULT_GAME_CONFIG_FILE)
        super().__init__(base_bet=base_bet, project_dir=project_dir, **kwargs)
        self.game_config_file = game_config_file
        self.game_server_config = self._read_config_file(self.project_dir / self.game_server_config_file)
        self.scatter_id, self.scatter_cols, self.scatter_multiples = self._load_win_free_config()
        self.random_win_multiples, self.random_win_multiple_probability = self._load_random_win_config()
        (
            self.special_type_need_bet,
            self.grid_disables_by_type,
            self.grid_disables_free_by_type,
        ) = self._load_type_grid_config()
        self.server_config_index = 0
        (
            self.win_jp_probability,
            self.win_jp_multiples,
            self.win_jp_type_probability,
            self.win_jp_double_probability,
        ) = self._load_jp_config(self.server_config_index)
        (
            self.free_multiples,
            self.free_multiple_probability,
            self.free_multiple_trigger_probability,
            self.super_free_multiples,
            self.super_free_multiple_probability,
            self.super_free_multiple_trigger_probability,
        ) = self._load_free_multiplier_config(self.server_config_index)
        self.type_index = self.get_type_index()
        self.last_ng_result: dict = {}
        self.last_fg_result: dict = {}

    def ng_spin(
        self,
        index: int,
        general_index: int | None = None,
        return_detail: bool = False,
    ) -> dict:
        general_index = self.get_base_general_index()
        return self._spin_and_evaluate(
            index=index,
            general_index=general_index,
            reel_config_dir=None,
            free_game=False,
            return_detail=return_detail,
        )

    def fg_spin(
        self,
        index: int,
        general_index: int | None = None,
        return_detail: bool = False,
        free_mode: str = "free",
    ) -> dict:
        general_index = self.get_free_general_index(free_mode)
        result = self._spin_and_evaluate(
            index=index,
            general_index=general_index,
            reel_config_dir=self.FREE_REEL_CONFIG_DIR,
            free_game=True,
            free_mode=free_mode,
            return_detail=return_detail,
        )
        self.last_fg_result = result
        return result

    def _spin_and_evaluate(
        self,
        index: int,
        general_index: int,
        reel_config_dir,
        free_game: bool,
        return_detail: bool,
        free_mode: str = "free",
    ) -> dict:
        self.apply_index_server_config(index)
        self.type_index = self.get_type_index()
        item_list = self.spin(
            index=index,
            general_index=general_index,
            row=self.config.row_count,
            col=self.config.col_count,
            reel_config_dir=reel_config_dir,
        )
        item_list = self.apply_type_grid_disables(item_list, free_game=free_game)
        self.last_spin_info["server_config_index"] = self.server_config_index
        self.last_spin_info["type_index"] = self.type_index
        self.last_spin_info["grid_disable_index"] = int(self.type_index)
        self.last_spin_info["free_mode"] = free_mode if free_game else None
        self.last_spin_info["is_super"] = int(self.is_super_free_mode(free_mode)) if free_game else 0
        return self.evaluate(
            item_list=item_list,
            row=self.config.row_count,
            col=self.config.col_count,
            return_detail=return_detail,
            free_game=free_game,
            free_mode=free_mode,
        )

    def evaluate(
        self,
        item_list,
        row: int | None = None,
        col: int | None = None,
        return_detail: bool = True,
        free_game: bool = False,
        free_mode: str = "free",
    ) -> dict:
        win_result = self.cal_item_list(
            item_list,
            return_detail=True,
            free_game=free_game,
            row=row,
            col=col,
        )
        win_free_info = self.get_win_free_info(item_list, row=row, col=col, free_game=free_game)
        win_jp_info = self.get_win_jp_info(
            item_list,
            win_free_info=win_free_info,
            row=row,
            col=col,
            free_game=free_game,
        )
        line_win = win_result["total_win"]
        jp_win = win_jp_info["win"]
        raw_total_win = line_win + jp_win
        win_multiplier_index, win_multiplier = self.choose_free_win_multiplier(free_mode) if free_game else (None, 1)
        total_win = raw_total_win * win_multiplier
        win_items = win_result["items"] if return_detail else []
        if win_multiplier != 1:
            win_items = self.apply_win_multiplier(win_items, win_multiplier)
        result = {
            "item_list": item_list,
            "total_win": total_win,
            "raw_total_win": raw_total_win,
            "line_win": line_win * win_multiplier,
            "raw_line_win": line_win,
            "win_multiplier": win_multiplier,
            "win_multiplier_index": win_multiplier_index,
            "free_mode": free_mode if free_game else None,
            "win_items": win_items,
            "win_positions": win_result["win_positions"],
            "win_free": win_free_info["win_free"],
            "free_times": win_free_info["free_times"],
            "win_free_info": win_free_info,
            "win_jp": win_jp_info["win_jp"],
            "jp_win": jp_win * win_multiplier,
            "raw_jp_win": jp_win,
            "win_jp_info": win_jp_info,
            "spin_info": self.last_spin_info,
            "free_game": free_game,
            "type_index": self.type_index,
        }
        self.last_ng_result = result
        return result

    @staticmethod
    def get_base_symbol_id(symbol_id: int | None) -> int | None:
        """Return the configured rzcs symbol id used for calculation."""

        if symbol_id is None:
            return None
        return symbol_id

    def _get_line_cell(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        col: int,
        row: int,
        row_count: int,
    ) -> int | None:
        cell_item = super()._get_line_cell(board_cols, grid_disables, col, row, row_count)
        return self.get_base_symbol_id(cell_item)

    def check_win_free(
        self,
        item_list,
        row: int | None = None,
        col: int | None = None,
        free_game: bool = False,
    ) -> bool:
        return self.get_win_free_info(item_list, row=row, col=col, free_game=free_game)["win_free"]

    def get_win_free_info(
        self,
        item_list,
        row: int | None = None,
        col: int | None = None,
        free_game: bool = False,
    ) -> dict:
        """Check scatter/wild free trigger on paylines from left to right."""

        board_cols, col_count, row_count = self._normalize_item_list(item_list, row=row, col=col)
        grid_disables = self._get_grid_disables(free_game, col_count, row_count)
        triggers = self._find_free_triggers(board_cols, grid_disables, row_count)
        if not triggers:
            return {
                "win_free": False,
                "free_times": 0,
                "trigger_count": 0,
                "trigger_line_index": None,
                "trigger_positions": [],
                "trigger_symbols": [],
                "triggers": [],
                "trigger_line_count": 0,
                "has_wild": False,
                "need_choice": False,
                "choices": [],
            }

        free_times = sum(trigger["free_times"] for trigger in triggers)
        max_trigger = max(triggers, key=lambda trigger: trigger["trigger_count"])
        has_wild = any(self.wild_id in trigger["trigger_symbols"] for trigger in triggers)
        need_choice = (not free_game) and len(triggers) > 1 and free_times > 0
        return {
            "win_free": free_times > 0,
            "free_times": free_times,
            "trigger_count": max_trigger["trigger_count"],
            "trigger_line_index": max_trigger["trigger_line_index"],
            "trigger_positions": [trigger["trigger_positions"] for trigger in triggers],
            "trigger_symbols": [trigger["trigger_symbols"] for trigger in triggers],
            "triggers": triggers,
            "trigger_line_count": len(triggers),
            "has_wild": has_wild,
            "need_choice": need_choice,
            "choices": self.build_free_trigger_choices(free_times, need_choice),
        }

    def _find_free_triggers(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        row_count: int,
    ) -> list[dict]:
        triggers = []
        for line_index, line_rule in enumerate(self.config.line_rules):
            trigger_symbols = []
            trigger_positions = []
            for col_index, row_index in line_rule:
                if col_index != len(trigger_symbols):
                    break
                cell_item = self._get_line_cell(board_cols, grid_disables, col_index, row_index, row_count)
                if cell_item not in (self.scatter_id, self.wild_id):
                    break
                trigger_symbols.append(cell_item)
                trigger_positions.append((col_index, row_index))

            trigger_count = len(trigger_symbols)
            free_times = self._get_or_default(self.scatter_multiples, trigger_count, 0)
            if free_times <= 0:
                continue
            triggers.append(
                {
                    "trigger_count": trigger_count,
                    "trigger_line_index": line_index,
                    "trigger_positions": trigger_positions,
                    "trigger_symbols": trigger_symbols,
                    "free_times": free_times,
                }
            )
        return triggers

    def build_free_trigger_choices(self, free_times: int, need_choice: bool) -> list[dict]:
        if free_times <= 0:
            return []

        free_choice = {"type": "free", "free_times": free_times}
        if not need_choice:
            return [free_choice]

        return [
            free_choice,
            {"type": "super_free", "free_times": free_times // 4},
            {
                "type": "random_win",
                "min_multiple": free_times,
                "max_multiple": free_times * 5,
                "multiple_options": self.random_win_multiples,
                "multiple_weights": self.random_win_multiple_probability,
            },
        ]

    def resolve_free_trigger_choice(self, win_free_info: dict, choice_type: str = "free") -> dict:
        """Resolve a player choice produced by build_free_trigger_choices()."""

        free_times = int(win_free_info.get("free_times", 0))
        if free_times <= 0:
            return {"type": choice_type, "win_free": False, "is_super": 0}
        if choice_type == "free":
            return {"type": "free", "win_free": True, "free_times": free_times, "free_mode": "free", "is_super": 0}
        if choice_type in ("super_free", "super_wild"):
            return {
                "type": "super_free",
                "win_free": True,
                "free_times": free_times // 4,
                "free_mode": "super_free",
                "is_super": 1,
            }
        if choice_type == "random_win":
            multiple_index, random_win_factor, multiple = self.choose_random_win_multiple(free_times)
            return {
                "type": "random_win",
                "win_free": False,
                "is_super": 0,
                "multiple_index": multiple_index,
                "random_win_factor": random_win_factor,
                "multiple": multiple,
                "win": int(multiple * self.base_bet),
            }
        raise ValueError(f"unknown free trigger choice: {choice_type}")

    def choose_random_win_multiple(self, free_times: int) -> tuple[int, float, float]:
        multiple_index = self.weighted_random_index(self.random_win_multiple_probability)
        factor = self._get_or_default(self.random_win_multiples, multiple_index, 1)
        return multiple_index, factor, free_times * factor

    def choose_free_win_multiplier(self, free_mode: str) -> tuple[int | None, int]:
        if free_mode == "super_free":
            trigger_probability = self._get_or_default(
                self.super_free_multiple_trigger_probability,
                int(self.type_index),
                self.PROBABILITY_DENOMINATOR,
            )
            if not self.roll_probability(trigger_probability):
                return None, 1
            multiplier_index = self.weighted_random_index(self.super_free_multiple_probability)
            return multiplier_index, self._get_or_default(self.super_free_multiples, multiplier_index, 1)
        trigger_probability = self._get_or_default(
            self.free_multiple_trigger_probability,
            int(self.type_index),
            self.PROBABILITY_DENOMINATOR,
        )
        if not self.roll_probability(trigger_probability):
            return None, 1
        multiplier_index = self.weighted_random_index(self.free_multiple_probability)
        return multiplier_index, self._get_or_default(self.free_multiples, multiplier_index, 1)

    @staticmethod
    def apply_win_multiplier(win_items: list[dict], win_multiplier: int) -> list[dict]:
        multiplied_items = []
        for win_item in win_items:
            item = win_item.copy()
            item["raw_win"] = item["win"]
            item["win_multiplier"] = win_multiplier
            item["win"] = item["win"] * win_multiplier
            multiplied_items.append(item)
        return multiplied_items

    def get_win_jp_info(
        self,
        item_list,
        win_free_info: dict,
        row: int | None = None,
        col: int | None = None,
        free_game: bool = False,
    ) -> dict:
        """Evaluate JP entry after free-trigger logic has failed."""

        if free_game or win_free_info.get("win_free"):
            return self._empty_jp_info()
        board_cols, col_count, row_count = self._normalize_item_list(item_list, row=row, col=col)
        grid_disables = self._get_grid_disables(free_game, col_count, row_count)
        if not self.has_active_wild(board_cols, grid_disables, row_count):
            return self._empty_jp_info()
        if not self.roll_probability(self.win_jp_probability):
            return self._empty_jp_info()

        jp_type_index = self.weighted_random_index(self.win_jp_type_probability)
        base_multiple = self._get_or_default(self.win_jp_multiples, jp_type_index, 0)
        double_probability = self._get_or_default(self.win_jp_double_probability, jp_type_index, 0)
        is_double = self.roll_probability(double_probability)
        multiple = base_multiple * 2 if is_double else base_multiple
        win = self.base_bet * multiple
        return {
            "win_jp": win > 0,
            "jp_type_index": jp_type_index,
            "base_multiple": base_multiple,
            "double_probability": double_probability,
            "is_double": is_double,
            "multiple": multiple,
            "win": win,
        }

    def has_active_wild(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        row_count: int,
    ) -> bool:
        for col_index, col_items in enumerate(board_cols):
            for row_index in range(min(row_count, len(col_items))):
                if self._is_disabled(grid_disables, col_index, row_index, row_count):
                    continue
                if self.get_base_symbol_id(col_items[row_index]) == self.wild_id:
                    return True
        return False

    @staticmethod
    def _empty_jp_info() -> dict:
        return {
            "win_jp": False,
            "jp_type_index": None,
            "base_multiple": 0,
            "double_probability": 0,
            "is_double": False,
            "multiple": 0,
            "win": 0,
        }

    @staticmethod
    def weighted_random_index(weights: list[int]) -> int:
        total_weight = sum(max(int(weight), 0) for weight in weights)
        if total_weight <= 0:
            return 0
        random_value = random.randint(1, total_weight)
        accumulated = 0
        for index, weight in enumerate(weights):
            accumulated += max(int(weight), 0)
            if random_value <= accumulated:
                return index
        return len(weights) - 1

    @classmethod
    def roll_probability(cls, probability: int) -> bool:
        """Roll a probability expressed in ten-thousandths."""

        probability = max(0, min(int(probability), cls.PROBABILITY_DENOMINATOR))
        return probability > 0 and random.randint(1, cls.PROBABILITY_DENOMINATOR) <= probability

    def _load_win_free_config(self) -> tuple[int, list[int], list[int]]:
        parser = self._read_config_file(self.project_dir / self.game_config_file)
        main = parser["MAIN"]
        scatter_ids = self._parse_int_list(main.get("SCATTER_ID", "0"))
        return (
            self.get_base_symbol_id(scatter_ids[0]) if scatter_ids else 0,
            self._parse_int_list(main.get("SCATTER_COLS", "")),
            self._parse_int_list(main.get("SCATTER_MULTIPLES", "")),
        )

    def _load_random_win_config(self) -> tuple[list[float], list[int]]:
        parser = self._read_config_file(self.project_dir / self.game_config_file)
        main = parser["MAIN"]
        multiples = self._parse_float_list(
            main.get("RANDOM_WIN_MULTIPLE", "1,1.5,2,2.5,3,3.5,4,4.5,5")
        )
        probabilities = self._parse_int_list(
            main.get("RANDOM_WIN_MULTIPLE_PROBABILITY", "1,1,1,1,1,1,1,1,1")
        )
        return multiples or [1], probabilities or [1]

    @staticmethod
    def _parse_float_list(value: str) -> list[float]:
        return [float(item.strip()) for item in value.split(",") if item.strip()]

    def _load_jp_config(self, index: int | None = None) -> tuple[int, list[int], list[int], list[int]]:
        main = self._get_runtime_config_section(index)
        return (
            int(main.get("WIN_JP_PROBABILITY", "0")),
            self._parse_int_list(main.get("WIN_JP_MULTIPLE", "")),
            self._parse_int_list(main.get("WIN_JP_TYPE_PROBABILITY", "")),
            self._parse_int_list(main.get("WIN_JP_DOUBLE_PROBABILITY", "0,0,0,0")),
        )

    def _load_free_multiplier_config(
        self,
        index: int | None = None,
    ) -> tuple[list[int], list[int], list[int], list[int], list[int], list[int]]:
        main = self._get_runtime_config_section(index)
        return (
            self._parse_int_list(main.get("FREE_MULTIPLE", "2")),
            self._parse_int_list(main.get("FREE_MULTIPLE_PROBABILITY", "100")),
            self._parse_int_list(
                main.get("FREE_MULTIPLE_TRIGGER_PROBABILITY", "10000,5000")
            ),
            self._parse_int_list(main.get("SUPER_FREE_MULTIPLE", "")),
            self._parse_int_list(main.get("SUPER_FREE_MULTIPLE_PROBABILITY", "")),
            self._parse_int_list(
                main.get("SUPER_FREE_MULTIPLE_TRIGGER_PROBABILITY", "10000,5000")
            ),
        )

    def apply_index_server_config(self, index: int) -> None:
        """Apply game_server.conf values selected by the player's INDEX."""

        self.server_config_index = self._resolve_server_config_index(index)
        (
            self.win_jp_probability,
            self.win_jp_multiples,
            self.win_jp_type_probability,
            self.win_jp_double_probability,
        ) = self._load_jp_config(index)
        (
            self.free_multiples,
            self.free_multiple_probability,
            self.free_multiple_trigger_probability,
            self.super_free_multiples,
            self.super_free_multiple_probability,
            self.super_free_multiple_trigger_probability,
        ) = self._load_free_multiplier_config(index)

    def _resolve_server_config_index(self, index: int) -> int:
        for section_name in (str(index), "0"):
            if self.game_server_config.has_section(section_name):
                return int(section_name)
        return index

    def _get_runtime_config_section(self, index: int | None = None):
        section_names = (str(index), "0") if index is not None else ("0",)
        for section_name in section_names:
            if self.game_server_config.has_section(section_name):
                return self.game_server_config[section_name]

        game_config = self._read_config_file(self.project_dir / self.game_config_file)
        return game_config["MAIN"]

    def _load_type_grid_config(self) -> tuple[int, dict[int, list[int]], dict[int, list[int]]]:
        parser = self._read_config_file(self.project_dir / self.game_config_file)
        main = parser["MAIN"]
        special_type_need_bet = int(main.get("SPECIAL_TYPE_NEED_BET", "0"))
        return (
            special_type_need_bet,
            self._load_indexed_grid_disables(main, "GRID_DISABLES"),
            self._load_indexed_grid_disables(main, "GRID_DISABLES_FREE"),
        )

    def _load_indexed_grid_disables(self, main, key_prefix: str) -> dict[int, list[int]]:
        grid_disables: dict[int, list[int]] = {}
        for index in (0, 1):
            value = main.get(f"{key_prefix}_{index}", "")
            if value:
                grid_disables[index] = self._parse_int_list(value)

        fallback = main.get(key_prefix, "")
        if fallback:
            grid_disables.setdefault(0, self._parse_int_list(fallback))
        return grid_disables

    def is_high_bet(self) -> bool:
        return self.base_bet >= self.special_type_need_bet

    def get_type_index(self) -> int:
        """Return whether current bet should use the special grid shape."""

        return int(self.is_high_bet())

    def get_base_general_index(self) -> int:
        return 1 if self.is_high_bet() else 2

    def get_free_general_index(self, free_mode: str = "free") -> int:
        is_super = self.is_super_free_mode(free_mode)
        if self.is_high_bet():
            return 4 if is_super else 2
        return 3 if is_super else 1

    @staticmethod
    def is_super_free_mode(free_mode: str) -> bool:
        return free_mode in ("super_free", "super_wild")

    def apply_type_grid_disables(self, item_list, free_game: bool = False):
        """Keep the 5x6 board shape and blank cells disabled by current type_index."""

        board_cols, col_count, row_count = self._normalize_item_list(
            item_list,
            row=self.config.row_count,
            col=self.config.col_count,
        )
        board = self._clone_board(board_cols)
        grid_disables = self._get_grid_disables(free_game, col_count, row_count)
        for col_index in range(col_count):
            for row_index in range(min(row_count, len(board[col_index]))):
                if self._is_disabled(grid_disables, col_index, row_index, row_count):
                    board[col_index][row_index] = None
        return board

    def _get_grid_disables(self, free_game: bool, col_count: int, row_count: int) -> list[int]:
        if col_count != self.config.col_count or row_count != self.config.row_count:
            return [0] * (col_count * row_count)

        grid_disables_by_type = self.grid_disables_free_by_type if free_game else self.grid_disables_by_type
        grid_disables = grid_disables_by_type.get(int(self.type_index)) or grid_disables_by_type.get(0)
        if grid_disables:
            return grid_disables
        return super()._get_grid_disables(free_game, col_count, row_count)

    @staticmethod
    def _clone_board(item_list):
        return [list(col_items) for col_items in item_list]
